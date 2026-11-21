"""Readers extract values verbatim from each supported format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ehr_platform.ingestion.models import Source
from ehr_platform.ingestion.readers import (
    IngestionError,
    read_directory,
    read_json_export,
    read_lab_csv,
    read_scanned_note,
)


def test_json_export_yields_documents_and_encounters(tmp_path: Path) -> None:
    path = tmp_path / "export.json"
    path.write_text(
        json.dumps(
            {
                "patients": [
                    {
                        "mrn": "mrn#7",
                        "name": {"first": "Ada", "last": "Lovelace"},
                        "dob": "1980-05-06",
                        "sex": "F",
                        "encounters": [{"encounter_id": "ENC-1", "class": "inpatient"}],
                        "documents": [{"category": "Imaging", "title": "CT", "text": "Normal."}],
                    }
                ]
            }
        )
    )

    batch = read_json_export(path)

    (record,) = batch.records
    assert record.source is Source.JSON
    assert record.patient.mrn == "mrn#7"  # untouched: cleaning happens later
    assert record.patient.name == "Ada Lovelace"
    assert record.kind == "Imaging"
    assert batch.encounters[0].encounter_id == "ENC-1"


def test_lab_csv_yields_one_record_per_row(tmp_path: Path) -> None:
    path = tmp_path / "labs.csv"
    path.write_text(
        "mrn,patient_name,dob,sex,collected,panel,result,flag,encounter_id,ordered_by\n"
        '7,"Lovelace, Ada",05/06/1980,F,01/02/2025,Sodium,"Sodium 140, normal.",N,,Dr. Who\n'
    )

    (record,) = read_lab_csv(path).records

    assert record.source_ref == "labs.csv#row=2"
    assert record.text == "Sodium 140, normal."
    assert record.abnormal_flag == "N"
    assert record.encounter_id is None  # empty cells become None


def test_scanned_note_splits_header_from_body(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text(
        "*** SCANNED DOCUMENT ***\nPatient: Ada Lovelace\nMRN: mrn 000007\n"
        "Date of Service: 02-Jan-2025\nDocument Type: Clinic letter\n\nFirst line.\nSecond line.\n"
    )

    (record,) = read_scanned_note(path).records

    assert record.patient.mrn == "mrn 000007"
    assert record.title == "Clinic letter"
    assert record.record_date == "02-Jan-2025"
    assert record.text == "First line.\nSecond line."


def test_directory_reader_combines_formats_and_ignores_others(tmp_path: Path) -> None:
    (tmp_path / "export.json").write_text('{"patients": []}')
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.txt").write_text("MRN: 1\n\nBody.")
    (tmp_path / "readme.md").write_text("ignored")

    assert len(read_directory(tmp_path).records) == 1


def test_malformed_json_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json")

    with pytest.raises(IngestionError, match=r"broken\.json"):
        read_json_export(path)


def test_missing_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(IngestionError):
        read_directory(tmp_path / "absent")
