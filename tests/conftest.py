"""Shared fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ehr_platform.config import Settings
from ehr_platform.pipeline import run_fhir, run_ingest, run_summarize
from ehr_platform.storage import Store
from ehr_platform.summarization.generators import RuleBasedGenerator

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = REPO_ROOT / "data" / "synthetic_manifest.json"

# A fixed "today" keeps two-digit-year and future-date rules reproducible.
TODAY = date(2025, 7, 1)


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture(scope="session")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Settings, Store]:
    """A store holding the full synthetic dataset, with rule-based summaries."""
    data_dir = tmp_path_factory.mktemp("data")
    (data_dir / "raw").symlink_to(RAW_DATA_DIR)
    settings = Settings(data_dir=data_dir, llm_api_key="", _env_file=None)  # type: ignore[call-arg]
    store = Store(settings.database_path)
    run_ingest(settings, store, today=TODAY)
    run_fhir(settings, store)
    run_summarize(settings, store, generator=RuleBasedGenerator())
    return settings, store
