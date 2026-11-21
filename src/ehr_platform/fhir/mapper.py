"""Map the clean intermediate representation to FHIR R4 resources.

One ``collection`` Bundle is built per patient. It holds the Patient, the
patient's Encounters, and one resource per clinical record:

* lab and imaging reports become ``DiagnosticReport``
* discharge summaries, progress notes and scanned notes become ``DocumentReference``

Resource IDs are UUIDv5 values derived from the MRN and record ID, so mapping
the same input twice yields byte-identical Bundles. References between
resources use ``urn:uuid:`` URLs that resolve to an entry's ``fullUrl`` inside
the same Bundle.
"""

from __future__ import annotations

import base64
import uuid
from datetime import date
from typing import Any

from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.diagnosticreport import DiagnosticReport
from fhir.resources.R4B.documentreference import DocumentReference
from fhir.resources.R4B.encounter import Encounter
from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.resource import Resource

from ehr_platform.fhir import codes
from ehr_platform.ingestion.models import (
    CleanEncounter,
    CleanPatient,
    CleanRecord,
    IngestionResult,
)

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:ehr-media-intelligence")


def resource_id(kind: str, key: str) -> str:
    """Deterministic resource ID for a source key."""
    return str(uuid.uuid5(_NAMESPACE, f"{kind}:{key}"))


def _reference(resource_uuid: str, display: str | None = None) -> dict[str, str]:
    reference = {"reference": f"urn:uuid:{resource_uuid}"}
    if display:
        reference["display"] = display
    return reference


def _concept(system: str, code: str, display: str, text: str | None = None) -> dict[str, Any]:
    concept: dict[str, Any] = {"coding": [{"system": system, "code": code, "display": display}]}
    if text:
        concept["text"] = text
    return concept


def _instant(value: date) -> str:
    """FHIR ``instant`` needs a time and zone; sources only give a calendar day."""
    return f"{value.isoformat()}T00:00:00Z"


def map_patient(patient: CleanPatient) -> Patient:
    payload: dict[str, Any] = {
        "id": resource_id("patient", patient.mrn),
        "identifier": [
            {
                "use": "usual",
                "type": _concept(codes.IDENTIFIER_TYPE_SYSTEM, "MR", "Medical record number"),
                "system": codes.MRN_SYSTEM,
                "value": patient.mrn,
            }
        ],
        "gender": patient.gender.value,
    }
    if patient.family_name or patient.given_name:
        name: dict[str, Any] = {"use": "official", "text": patient.display_name}
        if patient.family_name:
            name["family"] = patient.family_name
        if patient.given_name:
            name["given"] = patient.given_name.split()
        payload["name"] = [name]
    if patient.birth_date:
        payload["birthDate"] = patient.birth_date.isoformat()
    if patient.has_conflict:
        payload["meta"] = {
            "tag": [
                {
                    "system": codes.DATA_QUALITY_SYSTEM,
                    "code": codes.DEMOGRAPHIC_CONFLICT_TAG,
                    "display": "Sources disagreed on this patient's demographics",
                }
            ]
        }
    return Patient.model_validate(payload)


def map_encounter(encounter: CleanEncounter, patient: CleanPatient) -> Encounter:
    code, display = codes.ENCOUNTER_CLASS_CODES[encounter.encounter_class]
    payload: dict[str, Any] = {
        "id": resource_id("encounter", encounter.encounter_id),
        "identifier": [{"system": codes.ENCOUNTER_ID_SYSTEM, "value": encounter.encounter_id}],
        "status": "finished",
        "class": {"system": codes.ENCOUNTER_CLASS_SYSTEM, "code": code, "display": display},
        "subject": _reference(resource_id("patient", patient.mrn), patient.display_name),
    }
    period = {
        key: value.isoformat()
        for key, value in (("start", encounter.start), ("end", encounter.end))
        if value
    }
    if period:
        payload["period"] = period
    return Encounter.model_validate(payload)


def _common_fields(record: CleanRecord, patient: CleanPatient) -> dict[str, Any]:
    return {
        "id": resource_id("record", record.record_id),
        "identifier": [{"system": codes.RECORD_ID_SYSTEM, "value": record.record_id}],
        "subject": _reference(resource_id("patient", patient.mrn), patient.display_name),
    }


def map_diagnostic_report(record: CleanRecord, patient: CleanPatient) -> DiagnosticReport:
    code, display = codes.REPORT_CODES[record.kind]
    category_code, category_display = codes.REPORT_CATEGORIES[record.kind]
    payload = _common_fields(record, patient) | {
        "status": "final",
        "category": [_concept(codes.DIAGNOSTIC_SECTION_SYSTEM, category_code, category_display)],
        "code": _concept(codes.LOINC, code, display, text=record.title),
        "conclusion": record.text,
    }
    if record.record_date:
        payload["effectiveDateTime"] = record.record_date.isoformat()
    if record.encounter_id:
        payload["encounter"] = _reference(resource_id("encounter", record.encounter_id))
    if record.author:
        payload["resultsInterpreter"] = [{"display": record.author}]
    if record.abnormal is not None:
        flag = ("A", "Abnormal") if record.abnormal else ("N", "Normal")
        payload["conclusionCode"] = [_concept(codes.INTERPRETATION_SYSTEM, *flag)]
    return DiagnosticReport.model_validate(payload)


def map_document_reference(record: CleanRecord, patient: CleanPatient) -> DocumentReference:
    code, display = codes.DOCUMENT_TYPE_CODES[record.kind]
    payload = _common_fields(record, patient) | {
        "status": "current",
        "docStatus": "final",
        "type": _concept(codes.LOINC, code, display, text=record.title),
        "category": [_concept(codes.DOCUMENT_CATEGORY_SYSTEM, "clinical-note", "Clinical Note")],
        "description": record.title,
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain; charset=utf-8",
                    "title": record.title,
                    "data": base64.b64encode(record.text.encode()).decode(),
                }
            }
        ],
    }
    if record.record_date:
        payload["date"] = _instant(record.record_date)
    if record.author:
        payload["author"] = [{"display": record.author}]
    if record.encounter_id:
        payload["context"] = {
            "encounter": [_reference(resource_id("encounter", record.encounter_id))]
        }
    return DocumentReference.model_validate(payload)


def map_record(record: CleanRecord, patient: CleanPatient) -> Resource:
    if record.kind in codes.REPORT_CODES:
        return map_diagnostic_report(record, patient)
    return map_document_reference(record, patient)


def build_bundle(
    patient: CleanPatient, encounters: list[CleanEncounter], records: list[CleanRecord]
) -> dict[str, Any]:
    """Build one patient's Bundle and return it as FHIR JSON."""
    resources: list[Resource] = [map_patient(patient)]
    resources += [map_encounter(encounter, patient) for encounter in encounters]
    resources += [map_record(record, patient) for record in records]

    bundle = Bundle.model_validate(
        {
            "id": resource_id("bundle", patient.mrn),
            "type": "collection",
            "entry": [
                {"fullUrl": f"urn:uuid:{resource.id}", "resource": resource}
                for resource in resources
            ],
        }
    )
    fhir_json: dict[str, Any] = bundle.model_dump(mode="json", exclude_none=True)
    return fhir_json


def build_bundles(result: IngestionResult) -> dict[str, dict[str, Any]]:
    """Build a Bundle for every patient, keyed by MRN."""
    return {
        patient.mrn: build_bundle(
            patient, result.encounters_for(patient.mrn), result.records_for(patient.mrn)
        )
        for patient in result.patients
    }
