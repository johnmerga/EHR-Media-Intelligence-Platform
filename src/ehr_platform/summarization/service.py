"""Summarize patients, using the cache whenever the input has not changed."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from ehr_platform.fhir.reader import PatientRecord, read_bundle
from ehr_platform.ingestion.models import Severity
from ehr_platform.storage import Store, StoredBundle
from ehr_platform.summarization.generators import GenerationError, SummaryGenerator
from ehr_platform.summarization.models import (
    DISCLAIMERS,
    WORD_LIMIT,
    ClinicalSummary,
    SummaryContent,
)
from ehr_platform.summarization.prompt import (
    PROMPT_VERSION,
    STRICTER_INSTRUCTION,
    render_patient,
)

logger = logging.getLogger(__name__)


def record_hash(patient_text: str) -> str:
    """Hash of everything the model sees, plus the prompt version.

    Together with the patient ID this is the cache key: a summary is reused
    until a record, a data-quality warning or the prompt changes.
    """
    return hashlib.sha256(f"{PROMPT_VERSION}\n{patient_text}".encode()).hexdigest()


class Summarizer:
    def __init__(
        self, store: Store, generator: SummaryGenerator, fallback: SummaryGenerator
    ) -> None:
        self._store = store
        self._generator = generator
        self._fallback = fallback
        self.cache_hits = 0
        self.cache_misses = 0

    def data_quality_notes(self, mrn: str) -> list[str]:
        """Cleaning decisions a clinician should know about before trusting the record."""
        notable = (Severity.WARNING, Severity.CONFLICT)
        entries = self._store.audit_for_patient(mrn)
        return list(dict.fromkeys(e.message for e in entries if e.severity in notable))

    def summarize(self, stored: StoredBundle, *, refresh: bool = False) -> ClinicalSummary:
        patient = read_bundle(stored.bundle)
        patient_text = render_patient(patient, self.data_quality_notes(patient.mrn))
        key = record_hash(patient_text)

        cached = None if refresh else self._cached(patient.patient_id, key)
        if cached is not None:
            self.cache_hits += 1
            return cached

        self.cache_misses += 1
        summary = self._generate(patient, patient_text, key)
        self._store.put_summary(patient.patient_id, key, summary.model_dump_json())
        return summary

    def _cached(self, patient_id: str, key: str) -> ClinicalSummary | None:
        payload = self._store.get_summary(patient_id, key)
        if payload is None:
            return None
        summary = ClinicalSummary.model_validate_json(payload)
        # A rule-based placeholder must not block the LLM once one is configured.
        if summary.generator == "rule_based" and self._generator.kind == "llm":
            return None
        return summary

    def _generate(self, patient: PatientRecord, patient_text: str, key: str) -> ClinicalSummary:
        generator = self._generator
        try:
            content = self._within_word_limit(generator, patient, patient_text)
        except GenerationError as error:
            if generator is self._fallback:
                raise
            logger.warning("%s: %s; using the rule-based fallback", patient.mrn, error)
            generator = self._fallback
            content = self._within_word_limit(generator, patient, patient_text)

        return ClinicalSummary(
            **content.model_dump(),
            patient_id=patient.patient_id,
            mrn=patient.mrn,
            record_hash=key,
            generator=generator.kind,  # type: ignore[arg-type]
            model=generator.model,
            prompt_version=PROMPT_VERSION,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            disclaimer=DISCLAIMERS[generator.kind],
        )

    @staticmethod
    def _within_word_limit(
        generator: SummaryGenerator, patient: PatientRecord, patient_text: str
    ) -> SummaryContent:
        """Generate, retrying once with a stricter instruction if the limit is exceeded."""
        content = generator.generate(patient, patient_text)
        if content.word_count() < WORD_LIMIT:
            return content

        logger.info("%s: summary has %d words; retrying", patient.mrn, content.word_count())
        instruction = STRICTER_INSTRUCTION.format(words=content.word_count(), limit=WORD_LIMIT)
        content = generator.generate(patient, patient_text, instruction)
        if content.word_count() >= WORD_LIMIT:
            raise GenerationError(
                f"summary still has {content.word_count()} words after a retry (limit {WORD_LIMIT})"
            )
        return content
