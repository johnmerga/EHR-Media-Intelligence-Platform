"""Task 1: read messy EHR inputs and produce a clean, audited representation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ehr_platform.ingestion.cleaning import clean
from ehr_platform.ingestion.models import IngestionResult
from ehr_platform.ingestion.readers import IngestionError, read_directory

__all__ = ["IngestionError", "IngestionResult", "ingest_directory"]


def ingest_directory(directory: Path, *, today: date | None = None) -> IngestionResult:
    """Read every supported file under ``directory`` and clean the result."""
    return clean(read_directory(directory), today=today)
