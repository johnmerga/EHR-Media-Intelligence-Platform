"""Raw and cleaned representations of EHR records.

Readers produce ``Raw*`` models that hold values exactly as they were found.
The cleaning stage turns them into ``Clean*`` models, which are the validated
intermediate representation that the FHIR mapper consumes. Every change made
on the way is captured as an :class:`AuditEntry`.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    """Where a value came from, ordered from most to least trusted."""

    JSON = "json"
    CSV = "csv"
    TEXT = "text"

    @property
    def precedence(self) -> int:
        """Lower is more trusted: structured export, then lab feed, then OCR."""
        return list(Source).index(self)


class RecordKind(StrEnum):
    LAB_REPORT = "lab_report"
    IMAGING_REPORT = "imaging_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    PROGRESS_NOTE = "progress_note"
    SCANNED_NOTE = "scanned_note"


class Gender(StrEnum):
    """FHIR administrative gender codes."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class EncounterClass(StrEnum):
    EMERGENCY = "emergency"
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"


class Severity(StrEnum):
    INFO = "info"  # a format was normalized or a documented convention was applied
    WARNING = "warning"  # a value was missing, unusable or needs human review
    CONFLICT = "conflict"  # sources disagreed and one value was chosen


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Raw models
# --------------------------------------------------------------------------- #


class RawDemographics(_Frozen):
    """Patient details exactly as one source wrote them."""

    mrn: str | None = None
    name: str | None = None
    dob: str | None = None
    sex: str | None = None


class RawRecord(_Frozen):
    """One clinical record exactly as one source wrote it."""

    source: Source
    source_ref: str = Field(description="File and position, e.g. 'lab_results.csv#row=3'.")
    patient: RawDemographics
    kind: str | None = None
    title: str | None = None
    record_date: str | None = None
    text: str | None = None
    encounter_id: str | None = None
    author: str | None = None
    abnormal_flag: str | None = None


class RawEncounter(_Frozen):
    source_ref: str
    mrn: str | None = None
    encounter_id: str | None = None
    encounter_class: str | None = None
    start: str | None = None
    end: str | None = None


class RawBatch(BaseModel):
    """Everything the readers extracted from the input files."""

    records: list[RawRecord] = Field(default_factory=list)
    encounters: list[RawEncounter] = Field(default_factory=list)

    def extend(self, other: RawBatch) -> None:
        self.records.extend(other.records)
        self.encounters.extend(other.encounters)


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #


class AuditEntry(_Frozen):
    """One change, assumption or decision made while cleaning."""

    entity_id: str = Field(description="MRN, record ID or encounter ID the entry is about.")
    field: str
    old_value: str | None
    new_value: str | None
    rule: str = Field(description="Stable rule name, e.g. 'date.ambiguous_month_first'.")
    severity: Severity
    message: str


# --------------------------------------------------------------------------- #
# Clean models
# --------------------------------------------------------------------------- #


class CleanPatient(BaseModel):
    mrn: str = Field(pattern=r"^MRN-\d{6}$")
    given_name: str | None
    family_name: str | None
    birth_date: date | None
    gender: Gender
    has_conflict: bool = False
    sources: list[Source]
    audit: list[AuditEntry] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        parts = [self.given_name, self.family_name]
        return " ".join(part for part in parts if part) or "Unknown"


class CleanEncounter(BaseModel):
    encounter_id: str
    patient_mrn: str
    encounter_class: EncounterClass
    start: date | None
    end: date | None
    audit: list[AuditEntry] = Field(default_factory=list)


class CleanRecord(BaseModel):
    record_id: str
    patient_mrn: str
    kind: RecordKind
    title: str
    record_date: date | None
    text: str = Field(min_length=1)
    encounter_id: str | None
    author: str | None
    abnormal: bool | None = Field(description="Lab abnormal flag; None when not reported.")
    sources: list[Source]
    source_refs: list[str]
    audit: list[AuditEntry] = Field(default_factory=list)


class QuarantinedRecord(_Frozen):
    """A record that could not be cleaned safely and was set aside, not dropped."""

    source_ref: str
    rule: str
    reason: str
    raw: RawRecord


class IngestionResult(BaseModel):
    patients: list[CleanPatient]
    encounters: list[CleanEncounter]
    records: list[CleanRecord]
    quarantined: list[QuarantinedRecord]
    raw_record_count: int

    def audit_entries(self) -> list[AuditEntry]:
        """Every audit entry in the run, in a stable order."""
        entries: list[AuditEntry] = []
        for patient in self.patients:
            entries.extend(patient.audit)
        for encounter in self.encounters:
            entries.extend(encounter.audit)
        for record in self.records:
            entries.extend(record.audit)
        return entries

    def records_for(self, mrn: str) -> list[CleanRecord]:
        return [record for record in self.records if record.patient_mrn == mrn]

    def encounters_for(self, mrn: str) -> list[CleanEncounter]:
        return [encounter for encounter in self.encounters if encounter.patient_mrn == mrn]
