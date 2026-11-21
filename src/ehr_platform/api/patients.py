"""Assemble the patient detail view from the store."""

from __future__ import annotations

from datetime import date
from typing import Any

from ehr_platform.api.schemas import DataQualityNote, LinkedResource, PatientDetail
from ehr_platform.fhir.reader import PatientRecord, read_bundle
from ehr_platform.ingestion.models import Severity
from ehr_platform.storage import Store, StoredBundle
from ehr_platform.summarization.models import ClinicalSummary


def load_summary(store: Store, patient_id: str) -> ClinicalSummary | None:
    payload = store.summary_for_patient(patient_id)
    return ClinicalSummary.model_validate_json(payload) if payload else None


def _data_quality_notes(store: Store, mrn: str) -> list[DataQualityNote]:
    notes = []
    for entry in store.audit_for_patient(mrn):
        if entry.severity in (Severity.WARNING, Severity.CONFLICT):
            note = DataQualityNote(
                severity=entry.severity.value,  # type: ignore[arg-type]
                field=entry.field,
                message=entry.message,
                kept_value=entry.new_value,
                rejected_value=entry.old_value,
            )
            if note not in notes:
                notes.append(note)
    return notes


def _supporting_resource(resource: dict[str, Any], patient: PatientRecord) -> LinkedResource:
    """Describe a Patient or Encounter resource, which carry no clinical text."""
    record_date: date | None = None
    title = resource["resourceType"]
    if resource["resourceType"] == "Patient":
        title = f"{patient.name} ({patient.mrn})"
    elif resource["resourceType"] == "Encounter":
        start = resource.get("period", {}).get("start")
        record_date = date.fromisoformat(start[:10]) if start else None
        title = f"{resource.get('class', {}).get('display', 'Clinical')} encounter".capitalize()
    return LinkedResource(
        resource_id=resource["id"],
        resource_type=resource["resourceType"],
        title=title,
        category=None,
        record_date=record_date,
        author=None,
        abnormal=None,
        text=None,
        fhir=resource,
    )


def build_patient_detail(store: Store, stored: StoredBundle) -> PatientDetail:
    patient = read_bundle(stored.bundle)
    fhir_by_id = {resource["id"]: resource for resource in patient.resources}
    documents = {document.resource_id: document for document in patient.documents}

    clinical = [
        LinkedResource(
            resource_id=document.resource_id,
            resource_type=document.resource_type,
            title=document.title,
            category=document.category,
            record_date=document.record_date,
            author=document.author,
            abnormal=document.abnormal,
            text=document.text,
            fhir=fhir_by_id[document.resource_id],
        )
        for document in patient.documents  # newest first
    ]
    supporting = [
        _supporting_resource(resource, patient)
        for resource in patient.resources
        if resource["id"] not in documents
    ]

    return PatientDetail(
        patient_id=patient.patient_id,
        mrn=patient.mrn,
        name=patient.name,
        gender=patient.gender,
        birth_date=patient.birth_date,
        bundle_is_valid=stored.is_valid,
        summary=load_summary(store, patient.patient_id),
        data_quality_notes=_data_quality_notes(store, patient.mrn),
        resources=clinical + supporting,
    )
