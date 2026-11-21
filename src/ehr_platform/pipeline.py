"""Pipeline stages. Each one reads the previous stage's output from the store."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from ehr_platform.config import Settings
from ehr_platform.fhir.mapper import build_bundles
from ehr_platform.fhir.validation import ValidationReport, validate_bundles
from ehr_platform.ingestion import IngestionResult, ingest_directory
from ehr_platform.storage import Store

logger = logging.getLogger(__name__)


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", path)


def run_ingest(settings: Settings, store: Store, *, today: date | None = None) -> IngestionResult:
    """Stage 1: read raw files, clean them, store the result and an audit report."""
    result = ingest_directory(settings.raw_dir, today=today)
    store.save_ingestion(result)

    audit = result.audit_entries()
    _write_report(
        settings.reports_dir / "ingestion_report.json",
        {
            "raw_records": result.raw_record_count,
            "patients": len(result.patients),
            "encounters": len(result.encounters),
            "clean_records": len(result.records),
            "quarantined_records": len(result.quarantined),
            "patients_with_conflicts": [p.mrn for p in result.patients if p.has_conflict],
            "audit_entries_by_severity": dict(
                sorted(Counter(entry.severity.value for entry in audit).items())
            ),
            "audit_entries_by_rule": dict(sorted(Counter(entry.rule for entry in audit).items())),
            "quarantine": [
                {"source_ref": q.source_ref, "rule": q.rule, "reason": q.reason}
                for q in result.quarantined
            ],
        },
    )
    logger.info(
        "Ingested %d raw records: %d patients, %d clean records, %d quarantined, %d audit entries",
        result.raw_record_count,
        len(result.patients),
        len(result.records),
        len(result.quarantined),
        len(audit),
    )
    return result


def run_fhir(settings: Settings, store: Store) -> ValidationReport:
    """Stage 2: map clean records to FHIR Bundles, validate and store them."""
    bundles = build_bundles(store.load_ingestion())
    report = validate_bundles(bundles)
    store.save_bundles(bundles, report.bundles)
    _write_report(settings.reports_dir / "validation_report.json", report.model_dump(mode="json"))
    logger.info(report.render_text())
    return report
