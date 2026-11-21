"""End-to-end check: every defect injected into the dataset is caught and logged."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ehr_platform.ingestion import IngestionResult, ingest_directory
from tests.conftest import MANIFEST_PATH, RAW_DATA_DIR, TODAY

MANIFEST: dict[str, Any] = json.loads(MANIFEST_PATH.read_text())


@pytest.fixture(scope="module")
def result() -> IngestionResult:
    return ingest_directory(RAW_DATA_DIR, today=TODAY)


def test_counts_match_the_manifest(result: IngestionResult) -> None:
    assert len(result.patients) == MANIFEST["expected_patients"]
    assert len(result.records) == MANIFEST["expected_records"]
    assert len(result.quarantined) == MANIFEST["expected_quarantined"]


def test_no_raw_record_is_lost(result: IngestionResult) -> None:
    accounted_for = sum(len(r.source_refs) for r in result.records) + len(result.quarantined)

    assert accounted_for == result.raw_record_count


@pytest.mark.parametrize("defect", MANIFEST["defects"], ids=lambda d: f"{d['rule']}:{d['mrn']}")
def test_every_injected_defect_is_in_the_audit_log(
    result: IngestionResult, defect: dict[str, Any]
) -> None:
    if defect["mrn"] is None:
        assert defect["rule"] in {q.rule for q in result.quarantined}
        return

    owner = {r.record_id: r.patient_mrn for r in result.records}
    logged = {(e.rule, owner.get(e.entity_id, e.entity_id)) for e in result.audit_entries()}

    assert (defect["rule"], defect["mrn"]) in logged


def test_every_record_belongs_to_a_known_patient(result: IngestionResult) -> None:
    mrns = {p.mrn for p in result.patients}

    assert {r.patient_mrn for r in result.records} <= mrns
    assert len({r.record_id for r in result.records}) == len(result.records)
