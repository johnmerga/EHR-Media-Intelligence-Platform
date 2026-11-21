"""Checks that need the real sentence-transformers model (downloads ~90 MB once)."""

from __future__ import annotations

import time

import pytest

from ehr_platform.config import Settings
from ehr_platform.search.embedder import SentenceTransformerEmbedder
from ehr_platform.search.index import VectorIndex
from ehr_platform.search.service import SearchFilters, SearchService, build_index
from ehr_platform.storage import Store

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def service(dataset: tuple[Settings, Store]) -> SearchService:
    settings, store = dataset
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    index = VectorIndex(None)
    build_index(store, index, embedder)
    return SearchService(index, embedder)


@pytest.mark.parametrize(
    ("query", "expected_title"),
    [
        ("heart attack blood test", "Troponin I, high sensitivity"),
        ("lung infection on x-ray", "Chest X-ray, two views"),
        ("broken hip", "X-ray right hip and pelvis"),
        ("underactive thyroid", "Thyroid stimulating hormone"),
    ],
)
def test_query_without_shared_keywords_finds_the_right_record(
    service: SearchService, query: str, expected_title: str
) -> None:
    filters = SearchFilters(resource_type="DiagnosticReport")

    titles = [m.metadata["title"] for m in service.search(query, filters, top_k=5)]

    assert expected_title in titles[:3]


def test_search_over_the_dataset_returns_well_under_two_seconds(service: SearchService) -> None:
    service.search("warm up", SearchFilters(), top_k=5)

    started = time.perf_counter()
    matches = service.search("elevated cardiac enzymes", SearchFilters(), top_k=5)
    elapsed = time.perf_counter() - started

    assert len(matches) == 5
    assert elapsed < 2.0
