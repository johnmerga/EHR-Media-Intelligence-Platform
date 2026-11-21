"""Read clinical content back out of a stored FHIR Bundle.

Later stages (summarization, search, the API) work from the Bundles rather
than from the intermediate representation, so the FHIR store is the single
source of truth downstream of mapping.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import date
from typing import Any

from ehr_platform.fhir import codes

CLINICAL_RESOURCE_TYPES = ("DiagnosticReport", "DocumentReference")


@dataclass(frozen=True)
class ClinicalDocument:
    """One DiagnosticReport or DocumentReference, flattened for display and search."""

    resource_id: str
    resource_type: str
    title: str
    category: str
    record_date: date | None
    text: str
    author: str | None
    encounter_id: str | None
    abnormal: bool | None


@dataclass(frozen=True)
class PatientRecord:
    """A patient's Bundle, flattened."""

    patient_id: str
    mrn: str
    name: str
    gender: str
    birth_date: date | None
    has_demographic_conflict: bool
    documents: list[ClinicalDocument]
    resources: list[dict[str, Any]]

    @property
    def latest_record_date(self) -> date | None:
        return max((d.record_date for d in self.documents if d.record_date), default=None)


def _parse_day(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _first_coding(concept: dict[str, Any] | None) -> dict[str, Any]:
    codings = (concept or {}).get("coding") or [{}]
    first: dict[str, Any] = codings[0]
    return first


def _local_reference(reference: dict[str, Any] | None) -> str | None:
    value = (reference or {}).get("reference", "")
    return value.removeprefix("urn:uuid:") or None


def _decode_attachment(resource: dict[str, Any]) -> str:
    for content in resource.get("content", []):
        data = content.get("attachment", {}).get("data")
        if data:
            try:
                return base64.b64decode(data).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                return ""
    return ""


def _read_diagnostic_report(resource: dict[str, Any]) -> ClinicalDocument:
    interpreters = resource.get("resultsInterpreter") or [{}]
    interpretation = _first_coding((resource.get("conclusionCode") or [None])[0]).get("code")
    category = _first_coding((resource.get("category") or [None])[0]).get("code")
    return ClinicalDocument(
        resource_id=resource["id"],
        resource_type="DiagnosticReport",
        title=resource.get("code", {}).get("text") or "Diagnostic report",
        category="Imaging report" if category == "RAD" else "Laboratory report",
        record_date=_parse_day(resource.get("effectiveDateTime")),
        text=resource.get("conclusion", ""),
        author=interpreters[0].get("display"),
        encounter_id=_local_reference(resource.get("encounter")),
        abnormal=None if interpretation is None else interpretation != "N",
    )


def _read_document_reference(resource: dict[str, Any]) -> ClinicalDocument:
    authors = resource.get("author") or [{}]
    encounters = resource.get("context", {}).get("encounter") or [None]
    return ClinicalDocument(
        resource_id=resource["id"],
        resource_type="DocumentReference",
        title=resource.get("description") or "Clinical document",
        category=_first_coding(resource.get("type")).get("display") or "Note",
        record_date=_parse_day(resource.get("date")),
        text=_decode_attachment(resource),
        author=authors[0].get("display"),
        encounter_id=_local_reference(encounters[0]),
        abnormal=None,
    )


def read_bundle(bundle: dict[str, Any]) -> PatientRecord:
    """Flatten a patient Bundle. Raises ``ValueError`` if it holds no Patient."""
    resources = [entry["resource"] for entry in bundle.get("entry", []) if "resource" in entry]
    patient = next((r for r in resources if r.get("resourceType") == "Patient"), None)
    if patient is None:
        raise ValueError("Bundle does not contain a Patient resource")

    identifiers = patient.get("identifier", [])
    mrn = next((i["value"] for i in identifiers if i.get("system") == codes.MRN_SYSTEM), "")
    names = patient.get("name") or [{}]
    tags = patient.get("meta", {}).get("tag", [])

    documents = []
    for resource in resources:
        if resource.get("resourceType") == "DiagnosticReport":
            documents.append(_read_diagnostic_report(resource))
        elif resource.get("resourceType") == "DocumentReference":
            documents.append(_read_document_reference(resource))
    documents.sort(key=lambda d: (d.record_date or date.min, d.resource_id), reverse=True)

    return PatientRecord(
        patient_id=patient["id"],
        mrn=mrn,
        name=names[0].get("text") or "Unknown",
        gender=patient.get("gender", "unknown"),
        birth_date=_parse_day(patient.get("birthDate")),
        has_demographic_conflict=any(
            tag.get("code") == codes.DEMOGRAPHIC_CONFLICT_TAG for tag in tags
        ),
        documents=documents,
        resources=resources,
    )
