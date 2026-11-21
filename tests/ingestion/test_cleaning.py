"""Edge cases of the cleaning policy, each built from the smallest possible batch."""

from __future__ import annotations

from datetime import date
from typing import Any

from ehr_platform.ingestion.cleaning import clean
from ehr_platform.ingestion.models import (
    AuditEntry,
    Gender,
    IngestionResult,
    RawBatch,
    RawDemographics,
    RawEncounter,
    RawRecord,
    Severity,
    Source,
)
from tests.conftest import TODAY


def raw_record(source: Source = Source.JSON, ref: str = "a", **overrides: Any) -> RawRecord:
    """A valid raw record; pass keyword arguments to break it in one specific way."""
    patient = {
        "mrn": overrides.pop("mrn", "MRN-000001"),
        "name": overrides.pop("name", "Ada Lovelace"),
        "dob": overrides.pop("dob", "1980-05-06"),
        "sex": overrides.pop("sex", "female"),
    }
    fields: dict[str, Any] = {
        "kind": "Progress Note",
        "title": "Clinic note",
        "record_date": "2025-01-02",
        "text": "Patient is well.",
    }
    fields.update(overrides)
    return RawRecord(source=source, source_ref=ref, patient=RawDemographics(**patient), **fields)


def run(*records: RawRecord, encounters: list[RawEncounter] | None = None) -> IngestionResult:
    return clean(RawBatch(records=list(records), encounters=encounters or []), today=TODAY)


def rules(entries: list[AuditEntry]) -> set[str]:
    return {entry.rule for entry in entries}


def test_conflicting_birth_dates_resolve_to_the_most_trusted_source() -> None:
    result = run(
        raw_record(Source.TEXT, "scan.txt", dob="06-May-1908"),
        raw_record(Source.JSON, "export.json", dob="1980-05-06"),
    )

    (patient,) = result.patients
    assert patient.birth_date == date(1980, 5, 6)
    assert patient.has_conflict is True
    (conflict,) = [e for e in patient.audit if e.severity is Severity.CONFLICT]
    assert conflict.rule == "demographics.conflict_resolved"
    assert conflict.old_value == "1908-05-06 (text)"
    assert conflict.new_value == "1980-05-06 (json)"


def test_same_patient_under_differently_formatted_mrns_is_one_patient() -> None:
    result = run(
        raw_record(Source.JSON, "a", mrn="MRN-000042"),
        raw_record(Source.CSV, "b", mrn="42", kind="lab", text="Sodium 140."),
        raw_record(Source.TEXT, "c", mrn="mrn 000042", text="Scanned letter."),
    )

    assert [p.mrn for p in result.patients] == ["MRN-000042"]
    assert len(result.records) == 3
    assert "mrn.canonicalized" in rules(result.patients[0].audit)


def test_patients_with_different_mrns_are_flagged_but_never_merged() -> None:
    result = run(
        raw_record(ref="a", mrn="100"),
        raw_record(ref="b", mrn="200", text="Another visit."),
    )

    assert len(result.patients) == 2
    for patient in result.patients:
        assert "patient.possible_duplicate" in rules(patient.audit)


def test_exact_duplicates_are_dropped_and_logged() -> None:
    result = run(raw_record(ref="row=2"), raw_record(ref="row=3"))

    (record,) = result.records
    assert record.source_refs == ["row=2", "row=3"]
    assert "record.exact_duplicate_dropped" in rules(record.audit)


def test_near_duplicates_across_sources_merge_into_the_trusted_copy() -> None:
    result = run(
        raw_record(Source.TEXT, "scan.txt", text="PATIENT   is well.\n"),
        raw_record(Source.JSON, "export.json", text="Patient is well."),
    )

    (record,) = result.records
    assert record.text == "Patient is well."
    assert record.sources == [Source.JSON, Source.TEXT]
    assert "record.near_duplicate_merged" in rules(record.audit)


def test_records_with_different_content_on_the_same_day_are_kept_apart() -> None:
    result = run(raw_record(ref="a"), raw_record(ref="b", text="Patient reports headache."))

    assert len(result.records) == 2


def test_record_without_a_patient_identifier_is_quarantined_not_dropped() -> None:
    result = run(raw_record(ref="orphan", mrn=None), raw_record(ref="ok"))

    assert len(result.records) == 1
    (quarantined,) = result.quarantined
    assert quarantined.source_ref == "orphan"
    assert quarantined.rule == "record.missing_patient_identifier"


def test_record_without_content_is_quarantined() -> None:
    result = run(raw_record(ref="empty", text="   "), raw_record(ref="ok"))

    assert [q.rule for q in result.quarantined] == ["record.empty_content"]


def test_impossible_record_date_is_cleared_and_the_record_is_kept() -> None:
    result = run(raw_record(record_date="02/30/2025"))

    (record,) = result.records
    assert record.record_date is None
    assert "date.unparseable" in rules(record.audit)


def test_missing_gender_is_filled_from_a_less_trusted_source() -> None:
    result = run(
        raw_record(Source.JSON, "a", sex=None),
        raw_record(Source.CSV, "b", sex="F", kind="lab", text="Sodium 140."),
    )

    (patient,) = result.patients
    assert patient.gender is Gender.FEMALE
    assert patient.has_conflict is False
    assert "demographics.filled_from_other_source" in rules(patient.audit)


def test_gender_missing_everywhere_defaults_to_unknown() -> None:
    result = run(raw_record(sex=None))

    (patient,) = result.patients
    assert patient.gender is Gender.UNKNOWN
    assert "gender.defaulted_unknown" in rules(patient.audit)


def test_explicit_unknown_gender_does_not_conflict_with_a_real_value() -> None:
    result = run(
        raw_record(Source.JSON, "a", sex="U"),
        raw_record(Source.CSV, "b", sex="M", kind="lab", text="Sodium 140."),
    )

    (patient,) = result.patients
    assert patient.gender is Gender.MALE
    assert patient.has_conflict is False


def test_birth_date_in_the_future_is_cleared() -> None:
    result = run(raw_record(dob="2090-01-01"))

    (patient,) = result.patients
    assert patient.birth_date is None
    assert {"date.implausible", "demographics.missing"} <= rules(patient.audit)


def test_unknown_encounter_reference_is_removed_with_a_warning() -> None:
    known = RawEncounter(
        source_ref="x", mrn="MRN-000001", encounter_id="ENC-1", start="2025-01-02", end="2025-01-02"
    )
    result = run(
        raw_record(ref="a", encounter_id="ENC-1"),
        raw_record(ref="b", encounter_id="ENC-404", text="Other note."),
        encounters=[known],
    )

    by_ref = {record.source_refs[0]: record for record in result.records}
    assert by_ref["a"].encounter_id == "ENC-1"
    assert by_ref["b"].encounter_id is None
    assert "encounter.unknown_reference_removed" in rules(by_ref["b"].audit)


def test_record_ids_are_stable_across_runs() -> None:
    first = run(raw_record())
    second = run(raw_record())

    assert first.records[0].record_id == second.records[0].record_id
    assert first.records[0].record_id.startswith("rec-")
