"""Readers that turn input files into raw records without changing any value.

Three formats are supported:

* ``.json`` - a structured EHR export with nested patients, encounters and documents
* ``.csv``  - a flat lab-results feed, one result per row
* ``.txt``  - OCR text of a scanned note: a ``Key: value`` header, a blank line, the body

Readers only extract. All interpretation happens in :mod:`ehr_platform.ingestion.cleaning`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ehr_platform.ingestion.models import (
    RawBatch,
    RawDemographics,
    RawEncounter,
    RawRecord,
    Source,
)


class IngestionError(Exception):
    """An input file could not be read at all."""


def _text(value: Any) -> str | None:
    """Return a stripped string, or ``None`` for missing and empty values."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _json_name(value: Any) -> str | None:
    """Names appear either as a string or as ``{"first": ..., "last": ...}``."""
    if isinstance(value, dict):
        parts = [_text(value.get("first")), _text(value.get("last"))]
        return " ".join(part for part in parts if part) or None
    return _text(value)


def read_json_export(path: Path) -> RawBatch:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IngestionError(f"Cannot read JSON export {path}: {error}") from error

    batch = RawBatch()
    for patient_index, patient in enumerate(payload.get("patients", [])):
        demographics = RawDemographics(
            mrn=_text(patient.get("mrn")),
            name=_json_name(patient.get("name")),
            dob=_text(patient.get("dob")),
            sex=_text(patient.get("sex")),
        )
        for encounter in patient.get("encounters", []):
            batch.encounters.append(
                RawEncounter(
                    source_ref=f"{path.name}#patient={patient_index}",
                    mrn=demographics.mrn,
                    encounter_id=_text(encounter.get("encounter_id")),
                    encounter_class=_text(encounter.get("class")),
                    start=_text(encounter.get("start")),
                    end=_text(encounter.get("end")),
                )
            )
        for document_index, document in enumerate(patient.get("documents", [])):
            batch.records.append(
                RawRecord(
                    source=Source.JSON,
                    source_ref=f"{path.name}#patient={patient_index},document={document_index}",
                    patient=demographics,
                    kind=_text(document.get("category")),
                    title=_text(document.get("title")),
                    record_date=_text(document.get("date")),
                    text=_text(document.get("text")),
                    encounter_id=_text(document.get("encounter_id")),
                    author=_text(document.get("author")),
                )
            )
    return batch


def read_lab_csv(path: Path) -> RawBatch:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as error:
        raise IngestionError(f"Cannot read lab CSV {path}: {error}") from error

    batch = RawBatch()
    for row_number, row in enumerate(rows, start=2):  # row 1 is the header
        batch.records.append(
            RawRecord(
                source=Source.CSV,
                source_ref=f"{path.name}#row={row_number}",
                patient=RawDemographics(
                    mrn=_text(row.get("mrn")),
                    name=_text(row.get("patient_name")),
                    dob=_text(row.get("dob")),
                    sex=_text(row.get("sex")),
                ),
                kind="lab",
                title=_text(row.get("panel")),
                record_date=_text(row.get("collected")),
                text=_text(row.get("result")),
                encounter_id=_text(row.get("encounter_id")),
                author=_text(row.get("ordered_by")),
                abnormal_flag=_text(row.get("flag")),
            )
        )
    return batch


def read_scanned_note(path: Path) -> RawBatch:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise IngestionError(f"Cannot read scanned note {path}: {error}") from error

    header_block, _, body = content.partition("\n\n")
    header: dict[str, str] = {}
    for line in header_block.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            header[key.strip().lower()] = value.strip()

    record = RawRecord(
        source=Source.TEXT,
        source_ref=path.name,
        patient=RawDemographics(
            mrn=_text(header.get("mrn")),
            name=_text(header.get("patient")),
            dob=_text(header.get("dob")),
            sex=_text(header.get("sex")),
        ),
        kind=None,
        title=_text(header.get("document type")),
        record_date=_text(header.get("date of service")),
        text=_text(body),
        encounter_id=_text(header.get("encounter")),
        author=_text(header.get("author")),
    )
    return RawBatch(records=[record])


_READERS = {
    ".json": read_json_export,
    ".csv": read_lab_csv,
    ".txt": read_scanned_note,
}


def read_directory(directory: Path) -> RawBatch:
    """Read every supported file under ``directory``, in a stable order."""
    if not directory.is_dir():
        raise IngestionError(f"Input directory {directory} does not exist")

    batch = RawBatch()
    for path in sorted(directory.rglob("*")):
        reader = _READERS.get(path.suffix.lower())
        if path.is_file() and reader is not None:
            batch.extend(reader(path))
    return batch
