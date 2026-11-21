"""HTTP contract of the API, with a fake embedder injected."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ehr_platform.api.app import build_state, create_app
from ehr_platform.config import Settings
from ehr_platform.search.index import VectorIndex
from ehr_platform.storage import Store
from tests.fakes import FakeEmbedder


@pytest.fixture(scope="module")
def client(dataset: tuple[Settings, Store]) -> Iterator[TestClient]:
    settings, _ = dataset
    state = build_state(settings, embedder=FakeEmbedder(), index=VectorIndex(None))
    with TestClient(create_app(state)) as test_client:
        yield test_client


def test_health_reports_what_is_loaded(client: TestClient) -> None:
    body = client.get("/health").json()

    assert body == {
        "status": "ok",
        "patients": 16,
        "indexed_entries": 68,
        "embedding_model": "fake-bag-of-words",
    }


def test_search_returns_top_five_ranked_results(client: TestClient) -> None:
    response = client.post("/search", json={"query": "troponin elevated myocardial injury"})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 5
    assert body["took_ms"] < 2000
    top = body["results"][0]
    assert top["title"] == "Troponin I, high sensitivity"
    assert top["resource_type"] == "DiagnosticReport"
    assert top["record_date"] == "2025-01-08"
    assert top["patient"]["name"] == "Robert Hayes"
    assert top["patient"]["mrn"] == "MRN-001234"
    assert 0 < top["relevance"] <= 1
    assert top["summary_snippet"]
    scores = [result["relevance"] for result in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_search_filters_are_query_parameters(client: TestClient) -> None:
    response = client.post(
        "/search",
        params={
            "resource_type": "DiagnosticReport",
            "date_from": "2025-05-01",
            "date_to": "2025-05-31",
        },
        json={"query": "abdomen CT"},
    )

    body = response.json()
    assert body["filters"] == {
        "resource_type": "DiagnosticReport",
        "date_from": "2025-05-01",
        "date_to": "2025-05-31",
    }
    assert body["results"]
    for result in body["results"]:
        assert result["resource_type"] == "DiagnosticReport"
        assert "2025-05-01" <= result["record_date"] <= "2025-05-31"


def test_search_with_no_matches_returns_an_empty_list(client: TestClient) -> None:
    response = client.post("/search", params={"date_from": "2030-01-01"}, json={"query": "x"})

    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.parametrize(
    ("params", "body"),
    [
        ({}, {"query": "   "}),
        ({}, {"query": "x" * 301}),
        ({}, {}),
        ({"resource_type": "Observation"}, {"query": "x"}),
        ({"date_from": "01/02/2025"}, {"query": "x"}),
        ({"date_from": "2025-06-01", "date_to": "2025-01-01"}, {"query": "x"}),
    ],
    ids=["blank", "too-long", "missing", "bad-type", "bad-date", "inverted-range"],
)
def test_invalid_search_requests_are_rejected(
    client: TestClient, params: dict[str, str], body: dict[str, str]
) -> None:
    assert client.post("/search", params=params, json=body).status_code == 422


def test_patient_detail_has_summary_notes_and_linked_resources(client: TestClient) -> None:
    hit = client.post("/search", json={"query": "HbA1c glycemic control"}).json()["results"][0]

    response = client.get(f"/patients/{hit['patient']['patient_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "James O'Connor"
    assert body["bundle_is_valid"] is True
    assert body["summary"]["disclaimer"]
    assert body["summary"]["chief_concern"]
    assert [note["severity"] for note in body["data_quality_notes"]] == ["conflict"]
    assert body["data_quality_notes"][0]["rejected_value"] == "1955-07-12 (csv)"

    types = [resource["resource_type"] for resource in body["resources"]]
    assert types.count("Patient") == 1
    assert types.count("Encounter") == 2
    assert types.count("DiagnosticReport") + types.count("DocumentReference") == 4
    assert hit["resource_id"] in {resource["resource_id"] for resource in body["resources"]}
    for resource in body["resources"]:
        assert resource["fhir"]["resourceType"] == resource["resource_type"]
        assert resource["fhir"]["id"] == resource["resource_id"]


def test_unknown_patient_is_a_404(client: TestClient) -> None:
    assert client.get("/patients/does-not-exist").status_code == 404
