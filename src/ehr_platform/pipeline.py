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
from ehr_platform.fhir.reader import read_bundle
from ehr_platform.fhir.validation import ValidationReport, validate_bundles
from ehr_platform.ingestion import IngestionResult, ingest_directory
from ehr_platform.storage import Store
from ehr_platform.summarization.evaluation import EvaluationReport, evaluate_summary
from ehr_platform.summarization.generators import (
    OpenAICompatibleGenerator,
    RuleBasedGenerator,
    SummaryGenerator,
)
from ehr_platform.summarization.prompt import render_patient
from ehr_platform.summarization.service import Summarizer

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


def build_generator(settings: Settings) -> SummaryGenerator:
    """The configured LLM, or the rule-based extractor when no API key is set."""
    if not settings.llm_api_key:
        return RuleBasedGenerator()
    return OpenAICompatibleGenerator(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )


def run_summarize(
    settings: Settings,
    store: Store,
    *,
    refresh: bool = False,
    generator: SummaryGenerator | None = None,
) -> EvaluationReport:
    """Stage 3: summarize each patient (cached), then evaluate the summaries."""
    generator = generator or build_generator(settings)
    if generator.kind != "llm":
        logger.warning(
            "No LLM API key configured: cached summaries are reused, and any patient "
            "without one gets a rule-based summary that is not AI-generated"
        )
    summarizer = Summarizer(store, generator, fallback=RuleBasedGenerator())

    manifest_path = settings.data_dir / "synthetic_manifest.json"
    planted: dict[str, list[str]] = (
        json.loads(manifest_path.read_text())["planted_anomalies"] if manifest_path.exists() else {}
    )

    evaluations = []
    current: set[tuple[str, str]] = set()
    for stored in store.list_bundles():
        summary = summarizer.summarize(stored, refresh=refresh)
        current.add((summary.patient_id, summary.record_hash))
        patient = read_bundle(stored.bundle)
        source_text = render_patient(patient, summarizer.data_quality_notes(patient.mrn))
        evaluations.append(
            evaluate_summary(summary, patient, source_text, planted.get(patient.mrn))
        )
    store.prune_summaries(keep=current)

    report = EvaluationReport.from_evaluations(evaluations)
    _write_report(settings.reports_dir / "evaluation_report.json", report.model_dump(mode="json"))
    logger.info(
        "Summarized %d patients (%d from cache, %d generated). Evaluation: %d/%d passed, "
        "mean %.0f words, groundedness %.2f, planted-anomaly recall %s",
        report.summary_count,
        summarizer.cache_hits,
        summarizer.cache_misses,
        report.passed_count,
        report.summary_count,
        report.mean_word_count,
        report.mean_groundedness,
        report.planted_anomaly_recall,
    )
    return report
