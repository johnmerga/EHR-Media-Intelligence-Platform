"""Clean records map to the right FHIR resources with resolvable references."""

from __future__ import annotations

import base64
from typing import Any

from ehr_platform.fhir import codes
from ehr_platform.fhir.mapper import build_bundle, build_bundles
from ehr_platform.ingestion.models import Gender, RecordKind
from tests.factories import make_encounter, make_ingestion_result, make_patient, make_record


def resources_of(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    return [
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]


def test_bundle_is_a_collection_with_one_entry_per_resource() -> None:
    result = make_ingestion_result()

    bundle = build_bundles(result)["MRN-000001"]

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert [entry["resource"]["resourceType"] for entry in bundle["entry"]] == [
        "Patient",
        "Encounter",
        "DiagnosticReport",
        "DocumentReference",
    ]
    for entry in bundle["entry"]:
        assert entry["fullUrl"] == f"urn:uuid:{entry['resource']['id']}"


def test_patient_carries_mrn_identifier_and_demographics() -> None:
    bundle = build_bundle(make_patient(), [], [])

    (patient,) = resources_of(bundle, "Patient")
    (identifier,) = patient["identifier"]
    assert identifier["system"] == codes.MRN_SYSTEM
    assert identifier["value"] == "MRN-000001"
    assert identifier["type"]["coding"][0]["code"] == "MR"
    assert patient["name"][0] == {
        "use": "official",
        "text": "Ada Lovelace",
        "family": "Lovelace",
        "given": ["Ada"],
    }
    assert patient["gender"] == "female"
    assert patient["birthDate"] == "1980-05-06"


def test_missing_demographics_are_omitted_not_invented() -> None:
    patient = make_patient(birth_date=None, gender=Gender.UNKNOWN)

    (resource,) = resources_of(build_bundle(patient, [], []), "Patient")

    assert "birthDate" not in resource
    assert resource["gender"] == "unknown"


def test_demographic_conflict_is_tagged_on_the_patient() -> None:
    (resource,) = resources_of(build_bundle(make_patient(has_conflict=True), [], []), "Patient")

    assert resource["meta"]["tag"][0]["code"] == codes.DEMOGRAPHIC_CONFLICT_TAG


def test_lab_report_becomes_a_diagnostic_report_linked_to_patient_and_encounter() -> None:
    bundle = build_bundle(make_patient(), [make_encounter()], [make_record()])

    (patient,) = resources_of(bundle, "Patient")
    (encounter,) = resources_of(bundle, "Encounter")
    (report,) = resources_of(bundle, "DiagnosticReport")
    assert report["status"] == "final"
    assert report["category"][0]["coding"][0]["code"] == "LAB"
    assert report["code"]["text"] == "Troponin I"
    assert report["effectiveDateTime"] == "2025-01-02"
    assert report["conclusion"].startswith("Troponin I 842")
    assert report["conclusionCode"][0]["coding"][0]["code"] == "A"
    assert report["subject"]["reference"] == f"urn:uuid:{patient['id']}"
    assert report["encounter"]["reference"] == f"urn:uuid:{encounter['id']}"


def test_imaging_report_is_categorized_as_radiology() -> None:
    record = make_record(kind=RecordKind.IMAGING_REPORT, title="CT head", abnormal=None)

    (report,) = resources_of(build_bundle(make_patient(), [], [record]), "DiagnosticReport")

    assert report["category"][0]["coding"][0]["code"] == "RAD"
    assert "conclusionCode" not in report


def test_note_becomes_a_document_reference_with_base64_text() -> None:
    record = make_record(
        kind=RecordKind.DISCHARGE_SUMMARY, title="Discharge summary", text="Went home well."
    )

    bundle = build_bundle(make_patient(), [make_encounter()], [record])

    (document,) = resources_of(bundle, "DocumentReference")
    (encounter,) = resources_of(bundle, "Encounter")
    attachment = document["content"][0]["attachment"]
    assert document["status"] == "current"
    assert document["type"]["coding"][0] == {
        "system": codes.LOINC,
        "code": "18842-5",
        "display": "Discharge summary",
    }
    assert base64.b64decode(attachment["data"]).decode() == "Went home well."
    assert document["date"] == "2025-01-02T00:00:00Z"
    assert document["context"]["encounter"][0]["reference"] == f"urn:uuid:{encounter['id']}"


def test_record_without_date_or_encounter_omits_those_elements() -> None:
    record = make_record(record_date=None, encounter_id=None)

    (report,) = resources_of(build_bundle(make_patient(), [], [record]), "DiagnosticReport")

    assert "effectiveDateTime" not in report
    assert "encounter" not in report


def test_mapping_is_deterministic() -> None:
    assert build_bundles(make_ingestion_result()) == build_bundles(make_ingestion_result())
