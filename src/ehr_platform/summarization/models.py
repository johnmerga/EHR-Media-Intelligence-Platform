"""The structured summary: what the model writes and what the system adds."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

WORD_LIMIT = 200

DISCLAIMERS = {
    "llm": (
        "AI-generated summary of the patient's records. It may contain errors or omissions, "
        "is not a clinical decision, and must be verified against the source documents."
    ),
    "rule_based": (
        "Automatically extracted from the patient's records without a language model, "
        "because none was configured. It is incomplete, is not a clinical decision, and "
        "must be verified against the source documents."
    ),
}


class MediaRecord(BaseModel):
    date: str = Field(description="Record date as YYYY-MM-DD, or 'undated'.")
    type: str = Field(description="Kind of record, e.g. 'Chest X-ray' or 'Troponin I'.")
    finding: str = Field(description="The key finding in one short phrase.")


class SummaryContent(BaseModel):
    """The fields the language model is asked to produce."""

    chief_concern: str = Field(description="Why the patient sought care, in one sentence.")
    key_diagnoses: list[str] = Field(description="Diagnoses stated in the records.")
    recent_media_records: list[MediaRecord] = Field(
        description="The most recent imaging and laboratory records, newest first."
    )
    flagged_anomalies: list[str] = Field(
        description="Abnormal results, concerning findings and data-quality warnings."
    )
    confidence: Literal["low", "medium", "high"]

    def narrative_text(self) -> str:
        """All model-written prose, used for word counts, search and evaluation."""
        parts = [self.chief_concern, *self.key_diagnoses]
        parts += [f"{m.type} {m.finding}" for m in self.recent_media_records]
        parts += self.flagged_anomalies
        return " ".join(part.strip() for part in parts if part.strip())

    def word_count(self) -> int:
        return len(re.findall(r"\S+", self.narrative_text()))


class ClinicalSummary(SummaryContent):
    """A summary plus the provenance and disclaimer added by the system."""

    patient_id: str
    mrn: str
    record_hash: str
    generator: Literal["llm", "rule_based"]
    model: str
    prompt_version: str
    generated_at: str
    disclaimer: str
