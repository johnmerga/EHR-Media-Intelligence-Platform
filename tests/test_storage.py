"""The SQLite store round-trips each stage's output."""

from __future__ import annotations

from pathlib import Path

import pytest

from ehr_platform.fhir.mapper import build_bundles
from ehr_platform.fhir.validation import validate_bundles
from ehr_platform.ingestion import ingest_directory
from ehr_platform.storage import Store, hash_bundle
from tests.conftest import RAW_DATA_DIR, TODAY
from tests.factories import make_ingestion_result


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "nested" / "ehr.db")


def test_ingestion_result_round_trips(store: Store) -> None:
    result = ingest_directory(RAW_DATA_DIR, today=TODAY)

    store.save_ingestion(result)

    assert store.load_ingestion() == result


def test_audit_log_is_queryable_per_patient(store: Store) -> None:
    result = ingest_directory(RAW_DATA_DIR, today=TODAY)
    store.save_ingestion(result)

    rules = {entry.rule for entry in store.audit_for_patient("MRN-001236")}

    assert "demographics.conflict_resolved" in rules
    assert store.audit_for_patient("MRN-999999") == []


def test_saving_again_replaces_rather_than_appends(store: Store) -> None:
    result = make_ingestion_result()

    store.save_ingestion(result)
    store.save_ingestion(result)

    assert len(store.load_ingestion().records) == len(result.records)


def test_bundles_are_stored_with_hash_and_validity(store: Store) -> None:
    bundles = build_bundles(make_ingestion_result())
    bundles["MRN-000001"]["entry"][0]["resource"]["gender"] = "F"  # invalid on purpose
    report = validate_bundles(bundles)

    store.save_bundles(bundles, report.bundles)

    (stored,) = store.list_bundles()
    assert stored.mrn == "MRN-000001"
    assert stored.is_valid is False
    assert stored.record_hash == hash_bundle(bundles["MRN-000001"])
    assert store.get_bundle(stored.patient_id) == stored
    assert store.get_bundle("missing") is None
    assert [issue.path for issue in store.validation_issues("MRN-000001")] == ["gender"]


def test_bundle_hash_changes_with_content() -> None:
    bundle = build_bundles(make_ingestion_result())["MRN-000001"]
    changed = {**bundle, "id": "different"}

    assert hash_bundle(bundle) == hash_bundle(dict(reversed(bundle.items())))
    assert hash_bundle(bundle) != hash_bundle(changed)


def test_summary_cache_stores_replaces_and_prunes(store: Store) -> None:
    assert store.get_summary("p1", "k1") is None

    store.put_summary("p1", "k1", "old")
    store.put_summary("p1", "k1", "new")
    store.put_summary("p1", "k2", "other")

    assert store.get_summary("p1", "k1") == "new"
    assert store.prune_summaries(keep={("p1", "k1")}) == 1
    assert store.get_summary("p1", "k2") is None
