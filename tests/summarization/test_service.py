"""Caching, the word limit and the fallback, exercised with a fake LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from ehr_platform.fhir.mapper import build_bundles
from ehr_platform.fhir.reader import PatientRecord
from ehr_platform.fhir.validation import validate_bundles
from ehr_platform.ingestion.models import AuditEntry, Severity
from ehr_platform.storage import Store, StoredBundle
from ehr_platform.summarization.generators import GenerationError, RuleBasedGenerator
from ehr_platform.summarization.models import WORD_LIMIT, MediaRecord, SummaryContent
from ehr_platform.summarization.service import Summarizer
from tests.factories import make_ingestion_result, make_record


def content(words: int = 10) -> SummaryContent:
    return SummaryContent(
        chief_concern=" ".join(["word"] * words),
        key_diagnoses=["NSTEMI"],
        recent_media_records=[MediaRecord(date="2025-01-02", type="Troponin", finding="High")],
        flagged_anomalies=[],
        confidence="high",
    )


class FakeLLM:
    """Returns queued replies and records how it was called."""

    kind = "llm"
    model = "fake-model"

    def __init__(self, *replies: SummaryContent | Exception) -> None:
        self.replies = list(replies)
        self.instructions: list[str | None] = []

    def generate(
        self, patient: PatientRecord, patient_text: str, extra_instruction: str | None = None
    ) -> SummaryContent:
        self.instructions.append(extra_instruction)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "ehr.db")


def save(store: Store, **record_overrides: object) -> StoredBundle:
    result = make_ingestion_result()
    if record_overrides:
        result.records[0] = make_record(**record_overrides)
    bundles = build_bundles(result)
    store.save_ingestion(result)
    store.save_bundles(bundles, validate_bundles(bundles).bundles)
    return store.list_bundles()[0]


def test_summary_carries_provenance_and_disclaimer(store: Store) -> None:
    summary = Summarizer(store, FakeLLM(content()), RuleBasedGenerator()).summarize(save(store))

    assert summary.mrn == "MRN-000001"
    assert (summary.generator, summary.model, summary.prompt_version) == ("llm", "fake-model", "v1")
    assert "AI-generated" in summary.disclaimer
    assert "not a clinical decision" in summary.disclaimer


def test_second_run_is_served_from_the_cache(store: Store) -> None:
    llm = FakeLLM(content())
    summarizer = Summarizer(store, llm, RuleBasedGenerator())
    stored = save(store)

    first = summarizer.summarize(stored)
    second = summarizer.summarize(stored)

    assert first == second
    assert len(llm.instructions) == 1
    assert (summarizer.cache_hits, summarizer.cache_misses) == (1, 1)


def test_changed_record_invalidates_the_cache(store: Store) -> None:
    llm = FakeLLM(content())
    summarizer = Summarizer(store, llm, RuleBasedGenerator())

    before = summarizer.summarize(save(store))
    after = summarizer.summarize(save(store, text="Troponin I 12 ng/L, normal."))

    assert before.record_hash != after.record_hash
    assert len(llm.instructions) == 2


def test_refresh_bypasses_the_cache(store: Store) -> None:
    llm = FakeLLM(content())
    summarizer = Summarizer(store, llm, RuleBasedGenerator())
    stored = save(store)

    summarizer.summarize(stored)
    summarizer.summarize(stored, refresh=True)

    assert len(llm.instructions) == 2


def test_overlong_summary_is_retried_with_a_stricter_instruction(store: Store) -> None:
    llm = FakeLLM(content(words=WORD_LIMIT + 50), content(words=40))

    summary = Summarizer(store, llm, RuleBasedGenerator()).summarize(save(store))

    assert summary.word_count() < WORD_LIMIT
    assert llm.instructions[0] is None
    assert f"under {WORD_LIMIT} words" in (llm.instructions[1] or "")


def test_summary_that_stays_overlong_falls_back_instead_of_being_stored(store: Store) -> None:
    llm = FakeLLM(content(words=WORD_LIMIT + 50))

    summary = Summarizer(store, llm, RuleBasedGenerator()).summarize(save(store))

    assert summary.generator == "rule_based"
    assert summary.word_count() < WORD_LIMIT


def test_llm_failure_falls_back_to_a_labelled_rule_based_summary(store: Store) -> None:
    llm = FakeLLM(GenerationError("rate limited"))

    summary = Summarizer(store, llm, RuleBasedGenerator()).summarize(save(store))

    assert summary.generator == "rule_based"
    assert summary.confidence == "low"
    assert "without a language model" in summary.disclaimer
    assert summary.key_diagnoses == ["NSTEMI"]  # copied from "Diagnosis: NSTEMI."


def test_rule_based_placeholder_is_replaced_once_an_llm_is_configured(store: Store) -> None:
    stored = save(store)
    fallback = RuleBasedGenerator()
    Summarizer(store, fallback, fallback).summarize(stored)

    summary = Summarizer(store, FakeLLM(content()), fallback).summarize(stored)

    assert summary.generator == "llm"


def test_cached_llm_summary_is_reused_when_no_llm_is_configured(store: Store) -> None:
    stored = save(store)
    fallback = RuleBasedGenerator()
    Summarizer(store, FakeLLM(content()), fallback).summarize(stored)

    summary = Summarizer(store, fallback, fallback).summarize(stored)

    assert summary.generator == "llm"


def test_data_quality_warnings_reach_the_model(store: Store) -> None:
    class Capturing(FakeLLM):
        seen = ""

        def generate(
            self, patient: PatientRecord, patient_text: str, extra_instruction: str | None = None
        ) -> SummaryContent:
            self.seen = patient_text
            return super().generate(patient, patient_text, extra_instruction)

    result = make_ingestion_result()
    result.patients[0].audit.append(
        AuditEntry(
            entity_id="MRN-000001",
            field="birth_date",
            old_value="a",
            new_value="b",
            rule="demographics.conflict_resolved",
            severity=Severity.CONFLICT,
            message="Sources disagree on birth_date",
        )
    )
    bundles = build_bundles(result)
    store.save_ingestion(result)
    store.save_bundles(bundles, validate_bundles(bundles).bundles)
    llm = Capturing(content())

    Summarizer(store, llm, RuleBasedGenerator()).summarize(store.list_bundles()[0])

    assert "- Sources disagree on birth_date" in llm.seen
    assert "[flagged ABNORMAL]" in llm.seen
