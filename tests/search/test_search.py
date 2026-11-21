"""Indexing, ranking and filtering, tested with a fake embedder."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ehr_platform.config import Settings
from ehr_platform.search.documents import build_entries
from ehr_platform.search.index import VectorIndex
from ehr_platform.search.service import SearchFilters, SearchService, build_index
from ehr_platform.storage import Store
from tests.fakes import FakeEmbedder


@pytest.fixture(scope="module")
def service(dataset: tuple[Settings, Store]) -> SearchService:
    _, store = dataset
    index, embedder = VectorIndex(None), FakeEmbedder()
    build_index(store, index, embedder)
    return SearchService(index, embedder)


def test_every_clinical_resource_and_summary_is_indexed(dataset: tuple[Settings, Store]) -> None:
    _, store = dataset

    entries = build_entries(store)

    by_type = {
        t: sum(e.resource_type == t for e in entries) for t in {e.resource_type for e in entries}
    }
    assert by_type["Patient"] == 16  # one AI summary per patient
    assert by_type["DiagnosticReport"] + by_type["DocumentReference"] == 52
    assert len({e.entry_id for e in entries}) == len(entries)


def test_results_are_ranked_by_relevance_and_capped(service: SearchService) -> None:
    matches = service.search("troponin elevated myocardial injury", SearchFilters(), top_k=5)

    assert len(matches) == 5
    assert matches[0].metadata["title"] == "Troponin I, high sensitivity"
    scores = [match.relevance for match in matches]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)


@pytest.mark.parametrize("resource_type", ["Patient", "DiagnosticReport", "DocumentReference"])
def test_resource_type_filter(service: SearchService, resource_type: str) -> None:
    matches = service.search("chest pain", SearchFilters(resource_type=resource_type), top_k=5)

    assert matches
    assert {match.metadata["resource_type"] for match in matches} == {resource_type}


def test_date_range_filter_is_inclusive(service: SearchService) -> None:
    filters = SearchFilters(date_from=date(2025, 2, 3), date_to=date(2025, 2, 6))

    matches = service.search("pneumonia consolidation", filters, top_k=5)

    assert matches
    dates = {match.metadata["record_date"] for match in matches}
    assert min(dates) >= "2025-02-03"
    assert max(dates) <= "2025-02-06"
    assert "2025-02-03" in dates


def test_filters_combine(service: SearchService) -> None:
    filters = SearchFilters(resource_type="DiagnosticReport", date_from=date(2025, 6, 1))

    matches = service.search("fracture", filters, top_k=5)

    assert matches
    for match in matches:
        assert match.metadata["resource_type"] == "DiagnosticReport"
        assert match.metadata["record_date"] >= "2025-06-01"


def test_undated_records_are_searchable_but_excluded_by_date_filters(
    service: SearchService,
) -> None:
    query = "invasive ductal carcinoma core biopsy pathology"

    unfiltered = service.search(query, SearchFilters(), top_k=5)
    filtered = service.search(query, SearchFilters(date_from=date(2000, 1, 1)), top_k=50)

    assert unfiltered[0].metadata["title"] == "Surgical pathology report"
    assert "record_date" not in unfiltered[0].metadata
    assert all("record_date" in match.metadata for match in filtered)


def test_filter_matching_nothing_returns_an_empty_list(service: SearchService) -> None:
    assert service.search("anything", SearchFilters(date_from=date(2030, 1, 1)), top_k=5) == []


def test_index_is_rebuilt_only_when_content_changes(
    dataset: tuple[Settings, Store], tmp_path: Path
) -> None:
    _, store = dataset

    class CountingEmbedder(FakeEmbedder):
        calls = 0

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            return super().embed(texts)

    embedder = CountingEmbedder()
    first = VectorIndex(tmp_path / "index")
    assert build_index(store, first, embedder) == 68
    reopened = VectorIndex(tmp_path / "index")  # persisted on disk
    build_index(store, reopened, embedder)

    assert embedder.calls == 1
    assert reopened.count() == 68
