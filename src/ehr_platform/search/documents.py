"""Decide what gets indexed: one entry per clinical resource and per patient summary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from ehr_platform.fhir.reader import read_bundle
from ehr_platform.storage import Store
from ehr_platform.summarization.models import ClinicalSummary

SEARCHABLE_RESOURCE_TYPES = ("Patient", "DiagnosticReport", "DocumentReference")


@dataclass(frozen=True)
class IndexEntry:
    """One searchable item.

    ``resource_type`` is ``Patient`` for an AI summary (it describes the whole
    patient) and the FHIR type for a single clinical record.
    """

    entry_id: str
    text: str
    resource_type: str
    resource_id: str
    patient_id: str
    title: str
    category: str
    record_date: date | None

    def metadata(self) -> dict[str, str | int]:
        """Flat metadata for the vector store. Undated entries carry no date keys,
        so they never match a date-range filter."""
        metadata: dict[str, str | int] = {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "patient_id": self.patient_id,
            "title": self.title,
            "category": self.category,
        }
        if self.record_date is not None:
            metadata["record_date"] = self.record_date.isoformat()
            metadata["date_ordinal"] = self.record_date.toordinal()
        return metadata


def build_entries(store: Store) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    for stored in store.list_bundles():
        patient = read_bundle(stored.bundle)
        for document in patient.documents:
            entries.append(
                IndexEntry(
                    entry_id=document.resource_id,
                    text=f"{document.title}. {document.category}. {document.text}",
                    resource_type=document.resource_type,
                    resource_id=document.resource_id,
                    patient_id=patient.patient_id,
                    title=document.title,
                    category=document.category,
                    record_date=document.record_date,
                )
            )
        payload = store.summary_for_patient(patient.patient_id)
        if payload is not None:
            summary = ClinicalSummary.model_validate_json(payload)
            entries.append(
                IndexEntry(
                    entry_id=f"summary-{patient.patient_id}",
                    text=summary.narrative_text(),
                    resource_type="Patient",
                    resource_id=patient.patient_id,
                    patient_id=patient.patient_id,
                    title="Patient summary",
                    category="AI summary",
                    record_date=patient.latest_record_date,
                )
            )
    return entries


def fingerprint(entries: list[IndexEntry], embedder_name: str) -> str:
    """Identifies an index build; lets the API tell whether a stored index is stale."""
    digest = hashlib.sha256(embedder_name.encode())
    for entry in sorted(entries, key=lambda e: e.entry_id):
        digest.update(repr((entry.entry_id, entry.text, sorted(entry.metadata().items()))).encode())
    return digest.hexdigest()
