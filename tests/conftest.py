"""Shared fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = REPO_ROOT / "data" / "synthetic_manifest.json"

# A fixed "today" keeps two-digit-year and future-date rules reproducible.
TODAY = date(2025, 7, 1)


@pytest.fixture
def today() -> date:
    return TODAY
