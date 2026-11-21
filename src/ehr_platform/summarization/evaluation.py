"""Automated quality checks for generated summaries.

These checks cannot prove a summary is clinically right, but they catch the
failure modes that matter most and can be measured without a clinician:

* structure - every section present, disclaimer attached, under the word limit
* dates     - each cited record date belongs to a real record of that patient
* numbers   - every number in the summary appears in the source records
* grounding - share of the summary's clinical terms found in the source records
* recall    - abnormal findings planted in the synthetic data are mentioned
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from ehr_platform.fhir.reader import PatientRecord
from ehr_platform.summarization.models import WORD_LIMIT, ClinicalSummary

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_TERM = re.compile(r"[a-z][a-z0-9'-]{3,}")
_STOPWORDS = frozenset(
    [
        "about",
        "above",
        "after",
        "also",
        "and",
        "are",
        "been",
        "both",
        "data",
        "date",
        "from",
        "have",
        "into",
        "most",
        "more",
        "none",
        "not",
        "documented",
        "over",
        "patient",
        "patients",
        "record",
        "records",
        "result",
        "results",
        "show",
        "showed",
        "shows",
        "than",
        "that",
        "the",
        "their",
        "there",
        "this",
        "under",
        "undated",
        "was",
        "were",
        "which",
        "with",
        "within",
        "without",
        "source",
        "sources",
        "between",
        "disagree",
        "disagreed",
        "warning",
        "quality",
        "birth",
        "finding",
        "findings",
        "noted",
    ]
)


class SummaryEvaluation(BaseModel):
    mrn: str
    generator: str
    word_count: int
    within_word_limit: bool
    sections_complete: bool
    has_disclaimer: bool
    invalid_media_dates: list[str]
    unsupported_numbers: list[str]
    groundedness: float
    ungrounded_terms: list[str]
    planted_anomalies: list[str]
    missed_anomalies: list[str]

    @property
    def passed(self) -> bool:
        """Hard checks only. Groundedness and recall are reported as metrics."""
        return (
            self.within_word_limit
            and self.sections_complete
            and self.has_disclaimer
            and not self.invalid_media_dates
            and not self.unsupported_numbers
        )


class EvaluationReport(BaseModel):
    word_limit: int = WORD_LIMIT
    summary_count: int
    llm_generated_count: int
    passed_count: int
    mean_word_count: float
    max_word_count: int
    mean_groundedness: float
    planted_anomaly_recall: float | None
    failures: list[str]
    evaluations: list[SummaryEvaluation]

    @classmethod
    def from_evaluations(cls, evaluations: list[SummaryEvaluation]) -> EvaluationReport:
        count = len(evaluations) or 1
        planted = sum(len(e.planted_anomalies) for e in evaluations)
        missed = sum(len(e.missed_anomalies) for e in evaluations)
        return cls(
            summary_count=len(evaluations),
            llm_generated_count=sum(e.generator == "llm" for e in evaluations),
            passed_count=sum(e.passed for e in evaluations),
            mean_word_count=round(sum(e.word_count for e in evaluations) / count, 1),
            max_word_count=max((e.word_count for e in evaluations), default=0),
            mean_groundedness=round(sum(e.groundedness for e in evaluations) / count, 3),
            planted_anomaly_recall=round(1 - missed / planted, 3) if planted else None,
            failures=[e.mrn for e in evaluations if not e.passed],
            evaluations=evaluations,
        )


def _normalize_number(number: str) -> str:
    return number.replace(",", "").rstrip(".")


def evaluate_summary(
    summary: ClinicalSummary,
    patient: PatientRecord,
    source_text: str,
    planted_anomalies: list[str] | None = None,
) -> SummaryEvaluation:
    narrative = summary.narrative_text()
    narrative_lower = narrative.lower()
    source_lower = source_text.lower()

    known_dates = {d.record_date.isoformat() for d in patient.documents if d.record_date}
    if any(d.record_date is None for d in patient.documents):
        known_dates.add("undated")

    source_numbers = {_normalize_number(n) for n in _NUMBER.findall(source_text)}
    summary_numbers = {_normalize_number(n) for n in _NUMBER.findall(narrative)}

    terms = sorted(set(_TERM.findall(narrative_lower)) - _STOPWORDS)
    ungrounded = [term for term in terms if term not in source_lower]

    planted = planted_anomalies or []
    return SummaryEvaluation(
        mrn=summary.mrn,
        generator=summary.generator,
        word_count=summary.word_count(),
        within_word_limit=summary.word_count() < WORD_LIMIT,
        sections_complete=bool(
            summary.chief_concern.strip()
            and summary.key_diagnoses
            and summary.recent_media_records is not None
            and summary.flagged_anomalies is not None
        ),
        has_disclaimer=bool(summary.disclaimer.strip()),
        invalid_media_dates=sorted({m.date for m in summary.recent_media_records} - known_dates),
        unsupported_numbers=sorted(summary_numbers - source_numbers),
        groundedness=round(1 - len(ungrounded) / len(terms), 3) if terms else 1.0,
        ungrounded_terms=ungrounded,
        planted_anomalies=planted,
        missed_anomalies=[term for term in planted if term.lower() not in narrative_lower],
    )
