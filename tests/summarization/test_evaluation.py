"""The evaluation catches the summary failure modes it claims to catch."""

from __future__ import annotations

from typing import Any

from ehr_platform.fhir.mapper import build_bundles
from ehr_platform.fhir.reader import PatientRecord, read_bundle
from ehr_platform.summarization.evaluation import EvaluationReport, evaluate_summary
from ehr_platform.summarization.models import WORD_LIMIT, ClinicalSummary, MediaRecord
from ehr_platform.summarization.prompt import render_patient
from tests.factories import make_ingestion_result


def patient() -> PatientRecord:
    return read_bundle(build_bundles(make_ingestion_result())["MRN-000001"])


def summary(**overrides: Any) -> ClinicalSummary:
    fields: dict[str, Any] = {
        "chief_concern": "Admitted with chest pain.",
        "key_diagnoses": ["NSTEMI"],
        "recent_media_records": [
            MediaRecord(date="2025-01-02", type="Troponin I", finding="842 ng/L, elevated")
        ],
        "flagged_anomalies": ["Troponin I markedly elevated"],
        "confidence": "high",
        "patient_id": "p",
        "mrn": "MRN-000001",
        "record_hash": "h",
        "generator": "llm",
        "model": "fake",
        "prompt_version": "v1",
        "generated_at": "2025-07-01T00:00:00+00:00",
        "disclaimer": "AI-generated; not a clinical decision.",
    }
    return ClinicalSummary(**(fields | overrides))


def evaluate(candidate: ClinicalSummary, planted: list[str] | None = None) -> Any:
    record = patient()
    return evaluate_summary(candidate, record, render_patient(record, []), planted)


def test_faithful_summary_passes() -> None:
    evaluation = evaluate(summary(), planted=["troponin"])

    assert evaluation.passed
    assert evaluation.groundedness == 1.0
    assert evaluation.missed_anomalies == []


def test_summary_over_the_word_limit_fails() -> None:
    evaluation = evaluate(summary(chief_concern=" ".join(["pain"] * WORD_LIMIT)))

    assert not evaluation.within_word_limit
    assert not evaluation.passed


def test_date_that_matches_no_record_fails() -> None:
    wrong_date = [MediaRecord(date="2024-12-25", type="Troponin I", finding="elevated")]

    evaluation = evaluate(summary(recent_media_records=wrong_date))

    assert evaluation.invalid_media_dates == ["2024-12-25"]
    assert not evaluation.passed


def test_number_that_is_not_in_the_records_fails() -> None:
    evaluation = evaluate(summary(flagged_anomalies=["Troponin I 9,999 ng/L"]))

    assert evaluation.unsupported_numbers == ["9999"]
    assert not evaluation.passed


def test_terms_absent_from_the_records_lower_groundedness() -> None:
    evaluation = evaluate(summary(key_diagnoses=["NSTEMI", "Pulmonary embolism"]))

    assert evaluation.ungrounded_terms == ["embolism", "pulmonary"]
    assert evaluation.groundedness < 1.0
    assert evaluation.passed  # a metric to review, not a hard failure


def test_missed_planted_anomaly_is_reported() -> None:
    evaluation = evaluate(summary(), planted=["troponin", "potassium"])

    assert evaluation.missed_anomalies == ["potassium"]


def test_report_aggregates_results() -> None:
    good = evaluate(summary(), planted=["troponin"])
    bad = evaluate(summary(flagged_anomalies=["Troponin I 9,999 ng/L"]), planted=["potassium"])

    report = EvaluationReport.from_evaluations([good, bad])

    assert (report.summary_count, report.passed_count) == (2, 1)
    assert report.failures == ["MRN-000001"]
    assert report.planted_anomaly_recall == 0.5
    assert report.llm_generated_count == 2
