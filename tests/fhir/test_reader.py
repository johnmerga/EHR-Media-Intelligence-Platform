"""Reading a Bundle back gives the content that went in."""

from __future__ import annotations

from datetime import date

import pytest

from ehr_platform.fhir.mapper import build_bundle, build_bundles
from ehr_platform.fhir.reader import read_bundle
from tests.factories import make_ingestion_result, make_patient


def test_round_trip_preserves_patient_and_documents() -> None:
    record = read_bundle(build_bundles(make_ingestion_result())["MRN-000001"])

    assert (record.mrn, record.name, record.gender) == ("MRN-000001", "Ada Lovelace", "female")
    assert record.birth_date == date(1980, 5, 6)
    assert record.latest_record_date == date(2025, 1, 4)

    newest, oldest = record.documents  # newest first
    assert newest.resource_type == "DocumentReference"
    assert newest.category == "Discharge summary"
    assert newest.text == "Admitted with chest pain. Diagnosis: NSTEMI. Stent placed."
    assert newest.abnormal is None
    assert oldest.resource_type == "DiagnosticReport"
    assert oldest.category == "Laboratory report"
    assert oldest.title == "Troponin I"
    assert oldest.abnormal is True
    assert oldest.author == "Dr. Who"
    assert oldest.encounter_id is not None


def test_conflict_tag_is_read_back() -> None:
    record = read_bundle(build_bundle(make_patient(has_conflict=True), [], []))

    assert record.has_demographic_conflict is True
    assert record.documents == []
    assert record.latest_record_date is None


def test_bundle_without_a_patient_is_rejected() -> None:
    with pytest.raises(ValueError, match="Patient"):
        read_bundle({"resourceType": "Bundle", "type": "collection", "entry": []})
