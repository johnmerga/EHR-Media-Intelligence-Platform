"""Small builders for clean models, shared by tests of the later stages."""

from __future__ import annotations

from datetime import date
from typing import Any

from ehr_platform.ingestion.models import (
    CleanEncounter,
    CleanPatient,
    CleanRecord,
    EncounterClass,
    Gender,
    IngestionResult,
    RecordKind,
    Source,
)


def make_patient(**overrides: Any) -> CleanPatient:
    fields: dict[str, Any] = {
        "mrn": "MRN-000001",
        "given_name": "Ada",
        "family_name": "Lovelace",
        "birth_date": date(1980, 5, 6),
        "gender": Gender.FEMALE,
        "sources": [Source.JSON],
    }
    return CleanPatient(**(fields | overrides))


def make_encounter(**overrides: Any) -> CleanEncounter:
    fields: dict[str, Any] = {
        "encounter_id": "ENC-1",
        "patient_mrn": "MRN-000001",
        "encounter_class": EncounterClass.INPATIENT,
        "start": date(2025, 1, 2),
        "end": date(2025, 1, 4),
    }
    return CleanEncounter(**(fields | overrides))


def make_record(**overrides: Any) -> CleanRecord:
    fields: dict[str, Any] = {
        "record_id": "rec-0000000000000001",
        "patient_mrn": "MRN-000001",
        "kind": RecordKind.LAB_REPORT,
        "title": "Troponin I",
        "record_date": date(2025, 1, 2),
        "text": "Troponin I 842 ng/L, markedly elevated.",
        "encounter_id": "ENC-1",
        "author": "Dr. Who",
        "abnormal": True,
        "sources": [Source.CSV],
        "source_refs": ["labs.csv#row=2"],
    }
    return CleanRecord(**(fields | overrides))


def make_ingestion_result() -> IngestionResult:
    """One patient with one encounter, a lab report and a discharge summary."""
    return IngestionResult(
        patients=[make_patient()],
        encounters=[make_encounter()],
        records=[
            make_record(),
            make_record(
                record_id="rec-0000000000000002",
                kind=RecordKind.DISCHARGE_SUMMARY,
                title="Discharge summary",
                record_date=date(2025, 1, 4),
                text="Admitted with chest pain. Diagnosis: NSTEMI. Stent placed.",
                abnormal=None,
                sources=[Source.JSON],
                source_refs=["export.json#patient=0,document=0"],
            ),
        ],
        quarantined=[],
        raw_record_count=2,
    )
