"""SQLite store shared by every pipeline stage and the API.

Each stage reads what the previous one wrote:

* ingest    -> ``clean_*``, ``audit_log``, ``quarantine``
* fhir      -> ``bundles``, ``validation_issues``
* summarize -> ``summaries`` (a cache; never cleared by other stages)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ehr_platform.fhir.validation import BundleValidation, ValidationIssue
from ehr_platform.ingestion.models import (
    AuditEntry,
    CleanEncounter,
    CleanPatient,
    CleanRecord,
    IngestionResult,
    QuarantinedRecord,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clean_patients (
    mrn     TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clean_encounters (
    encounter_id TEXT PRIMARY KEY,
    patient_mrn  TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clean_records (
    record_id   TEXT PRIMARY KEY,
    patient_mrn TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY,
    patient_mrn TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    rule        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_log_by_patient ON audit_log (patient_mrn);
CREATE TABLE IF NOT EXISTS quarantine (
    source_ref TEXT PRIMARY KEY,
    rule       TEXT NOT NULL,
    reason     TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    raw_record_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bundles (
    patient_id  TEXT PRIMARY KEY,
    mrn         TEXT NOT NULL UNIQUE,
    record_hash TEXT NOT NULL,
    is_valid    INTEGER NOT NULL,
    bundle      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_issues (
    id            INTEGER PRIMARY KEY,
    mrn           TEXT NOT NULL,
    validator     TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id   TEXT,
    path          TEXT NOT NULL,
    message       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    patient_id TEXT NOT NULL,
    cache_key  TEXT NOT NULL,
    payload    TEXT NOT NULL,
    PRIMARY KEY (patient_id, cache_key)
);
"""


@dataclass(frozen=True)
class StoredBundle:
    patient_id: str
    mrn: str
    record_hash: str
    is_valid: bool
    bundle: dict[str, Any]


def hash_bundle(bundle: dict[str, Any]) -> str:
    """Content hash of a Bundle; changes whenever any record changes."""
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:  # commit on success, roll back on error
                yield connection
        finally:
            connection.close()

    # ----------------------------------------------------------------- ingest

    def save_ingestion(self, result: IngestionResult) -> None:
        """Replace the stored clean representation with ``result``."""
        owner = {patient.mrn: patient.mrn for patient in result.patients}
        owner |= {e.encounter_id: e.patient_mrn for e in result.encounters}
        owner |= {r.record_id: r.patient_mrn for r in result.records}

        with self._connect() as db:
            for table in (
                "clean_patients",
                "clean_encounters",
                "clean_records",
                "audit_log",
                "quarantine",
                "ingestion_runs",
            ):
                db.execute(f"DELETE FROM {table}")
            db.executemany(
                "INSERT INTO clean_patients VALUES (?, ?)",
                [(p.mrn, p.model_dump_json()) for p in result.patients],
            )
            db.executemany(
                "INSERT INTO clean_encounters VALUES (?, ?, ?)",
                [(e.encounter_id, e.patient_mrn, e.model_dump_json()) for e in result.encounters],
            )
            db.executemany(
                "INSERT INTO clean_records VALUES (?, ?, ?)",
                [(r.record_id, r.patient_mrn, r.model_dump_json()) for r in result.records],
            )
            db.executemany(
                "INSERT INTO audit_log (patient_mrn, entity_id, field, old_value, new_value,"
                " rule, severity, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        owner[a.entity_id],
                        a.entity_id,
                        a.field,
                        a.old_value,
                        a.new_value,
                        a.rule,
                        a.severity.value,
                        a.message,
                    )
                    for a in result.audit_entries()
                ],
            )
            db.executemany(
                "INSERT INTO quarantine VALUES (?, ?, ?, ?)",
                [(q.source_ref, q.rule, q.reason, q.model_dump_json()) for q in result.quarantined],
            )
            db.execute("INSERT INTO ingestion_runs VALUES (1, ?)", (result.raw_record_count,))

    def load_ingestion(self) -> IngestionResult:
        with self._connect() as db:
            run = db.execute("SELECT raw_record_count FROM ingestion_runs").fetchone()
            return IngestionResult(
                patients=[
                    CleanPatient.model_validate_json(row["payload"])
                    for row in db.execute("SELECT payload FROM clean_patients ORDER BY mrn")
                ],
                encounters=[
                    CleanEncounter.model_validate_json(row["payload"])
                    for row in db.execute(
                        "SELECT payload FROM clean_encounters ORDER BY patient_mrn, encounter_id"
                    )
                ],
                records=[
                    CleanRecord.model_validate_json(row["payload"])
                    for row in db.execute("SELECT payload FROM clean_records ORDER BY rowid")
                ],
                quarantined=[
                    QuarantinedRecord.model_validate_json(row["payload"])
                    for row in db.execute("SELECT payload FROM quarantine ORDER BY rowid")
                ],
                raw_record_count=run["raw_record_count"] if run else 0,
            )

    def audit_for_patient(self, mrn: str) -> list[AuditEntry]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT entity_id, field, old_value, new_value, rule, severity, message"
                " FROM audit_log WHERE patient_mrn = ? ORDER BY id",
                (mrn,),
            ).fetchall()
        return [AuditEntry(**dict(row)) for row in rows]

    # ------------------------------------------------------------------- fhir

    def save_bundles(
        self, bundles: dict[str, dict[str, Any]], validations: list[BundleValidation]
    ) -> None:
        """Replace the stored Bundles and their validation results."""
        validity = {v.patient_mrn: v for v in validations}
        with self._connect() as db:
            db.execute("DELETE FROM bundles")
            db.execute("DELETE FROM validation_issues")
            for mrn, bundle in bundles.items():
                patient_id = next(
                    entry["resource"]["id"]
                    for entry in bundle["entry"]
                    if entry["resource"]["resourceType"] == "Patient"
                )
                db.execute(
                    "INSERT INTO bundles VALUES (?, ?, ?, ?, ?)",
                    (
                        patient_id,
                        mrn,
                        hash_bundle(bundle),
                        validity[mrn].is_valid,
                        json.dumps(bundle),
                    ),
                )
                db.executemany(
                    "INSERT INTO validation_issues (mrn, validator, resource_type, resource_id,"
                    " path, message) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (mrn, i.validator, i.resource_type, i.resource_id, i.path, i.message)
                        for i in validity[mrn].issues
                    ],
                )

    @staticmethod
    def _to_bundle(row: sqlite3.Row) -> StoredBundle:
        return StoredBundle(
            patient_id=row["patient_id"],
            mrn=row["mrn"],
            record_hash=row["record_hash"],
            is_valid=bool(row["is_valid"]),
            bundle=json.loads(row["bundle"]),
        )

    def list_bundles(self) -> list[StoredBundle]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM bundles ORDER BY mrn").fetchall()
        return [self._to_bundle(row) for row in rows]

    def get_bundle(self, patient_id: str) -> StoredBundle | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM bundles WHERE patient_id = ?", (patient_id,)).fetchone()
        return self._to_bundle(row) if row else None

    def validation_issues(self, mrn: str) -> list[ValidationIssue]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT validator, resource_type, resource_id, path, message"
                " FROM validation_issues WHERE mrn = ? ORDER BY id",
                (mrn,),
            ).fetchall()
        return [ValidationIssue(**dict(row)) for row in rows]

    # -------------------------------------------------------------- summaries

    def get_summary(self, patient_id: str, cache_key: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload FROM summaries WHERE patient_id = ? AND cache_key = ?",
                (patient_id, cache_key),
            ).fetchone()
        return row["payload"] if row else None

    def put_summary(self, patient_id: str, cache_key: str, payload: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO summaries VALUES (?, ?, ?)",
                (patient_id, cache_key, payload),
            )

    def prune_summaries(self, keep: set[tuple[str, str]]) -> int:
        """Delete cached summaries that no current Bundle would use."""
        with self._connect() as db:
            stale = [
                (row["patient_id"], row["cache_key"])
                for row in db.execute("SELECT patient_id, cache_key FROM summaries")
                if (row["patient_id"], row["cache_key"]) not in keep
            ]
            db.executemany("DELETE FROM summaries WHERE patient_id = ? AND cache_key = ?", stale)
        return len(stale)
