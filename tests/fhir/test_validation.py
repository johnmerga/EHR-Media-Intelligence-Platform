"""The validation report surfaces every kind of problem, attributed to its resource."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from ehr_platform.fhir.mapper import build_bundles
from ehr_platform.fhir.validation import BundleValidation, validate_bundle, validate_bundles
from ehr_platform.ingestion import ingest_directory
from tests.conftest import RAW_DATA_DIR, TODAY
from tests.factories import make_ingestion_result

MRN = "MRN-000001"


@pytest.fixture
def bundle() -> dict[str, Any]:
    return copy.deepcopy(build_bundles(make_ingestion_result())[MRN])


def resource(bundle: dict[str, Any], resource_type: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    )
    return found


def issues_from(validation: BundleValidation, validator: str) -> list[tuple[str, str]]:
    return [(i.resource_type, i.path) for i in validation.issues if i.validator == validator]


def test_a_well_formed_bundle_has_no_issues(bundle: dict[str, Any]) -> None:
    validation = validate_bundle(MRN, bundle)

    assert validation.is_valid
    assert validation.resource_counts == {
        "Patient": 1,
        "Encounter": 1,
        "DiagnosticReport": 1,
        "DocumentReference": 1,
    }


def test_malformed_date_is_reported_by_both_schema_validators(bundle: dict[str, Any]) -> None:
    resource(bundle, "Patient")["birthDate"] = "06/05/1980"

    validation = validate_bundle(MRN, bundle)

    assert ("Patient", "birthDate") in issues_from(validation, "fhir.resources")
    assert ("Patient", "birthDate") in issues_from(validation, "fhirclient")


def test_missing_required_element_is_reported(bundle: dict[str, Any]) -> None:
    del resource(bundle, "DiagnosticReport")["code"]

    validation = validate_bundle(MRN, bundle)

    assert ("DiagnosticReport", "code") in issues_from(validation, "fhir.resources")
    assert not validation.is_valid


def test_element_that_is_not_part_of_r4_is_reported(bundle: dict[str, Any]) -> None:
    resource(bundle, "DocumentReference")["notAnR4Element"] = "x"

    validation = validate_bundle(MRN, bundle)

    assert ("DocumentReference", "notAnR4Element") in issues_from(validation, "fhir.resources")
    assert any(i.validator == "fhirclient" for i in validation.issues)


def test_code_outside_a_required_value_set_is_reported(bundle: dict[str, Any]) -> None:
    resource(bundle, "Patient")["gender"] = "F"

    validation = validate_bundle(MRN, bundle)

    assert issues_from(validation, "terminology") == [("Patient", "gender")]


def test_dangling_reference_is_reported(bundle: dict[str, Any]) -> None:
    resource(bundle, "DiagnosticReport")["encounter"] = {"reference": "urn:uuid:missing"}

    validation = validate_bundle(MRN, bundle)

    assert issues_from(validation, "references") == [("DiagnosticReport", "encounter")]


def test_resource_pointing_at_another_patient_is_reported(bundle: dict[str, Any]) -> None:
    encounter_url = f"urn:uuid:{resource(bundle, 'Encounter')['id']}"
    resource(bundle, "DocumentReference")["subject"] = {"reference": encounter_url}

    validation = validate_bundle(MRN, bundle)

    assert ("DocumentReference", "subject") in issues_from(validation, "references")


def test_report_counts_and_renders_failures(bundle: dict[str, Any]) -> None:
    broken = copy.deepcopy(bundle)
    resource(broken, "Patient")["gender"] = "F"

    report = validate_bundles({"MRN-000001": bundle, "MRN-000002": broken})

    assert (report.bundle_count, report.valid_bundle_count, report.issue_count) == (2, 1, 1)
    text = report.render_text()
    assert "1/2 bundles valid" in text
    assert "MRN-000002" in text
    assert "[terminology] Patient/" in text


def test_every_bundle_of_the_synthetic_dataset_is_valid() -> None:
    report = validate_bundles(build_bundles(ingest_directory(RAW_DATA_DIR, today=TODAY)))

    assert report.bundle_count == 16
    assert report.issue_count == 0, report.render_text()
