"""FastAPI application.

The API is read-only: it serves search and patient detail from the SQLite
store and the vector index. It never calls the LLM.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from ehr_platform.api.patients import build_patient_detail, load_summary
from ehr_platform.api.schemas import (
    AppliedFilters,
    Health,
    PatientDetail,
    PatientRef,
    ResourceType,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from ehr_platform.config import Settings, get_settings
from ehr_platform.fhir.reader import read_bundle
from ehr_platform.search.embedder import Embedder, SentenceTransformerEmbedder
from ehr_platform.search.index import VectorIndex
from ehr_platform.search.service import SearchFilters, SearchService, build_index
from ehr_platform.storage import Store

_SNIPPET_LENGTH = 220


@dataclass
class AppState:
    settings: Settings
    store: Store
    index: VectorIndex
    embedder: Embedder
    search: SearchService
    patients: dict[str, PatientRef]
    summary_snippets: dict[str, str]


def _snippet(text: str) -> str:
    if len(text) <= _SNIPPET_LENGTH:
        return text
    return text[:_SNIPPET_LENGTH].rsplit(" ", 1)[0] + "..."


def build_state(
    settings: Settings, *, embedder: Embedder | None = None, index: VectorIndex | None = None
) -> AppState:
    """Open the store, make sure the index is current and cache what search needs."""
    store = Store(settings.database_path)
    embedder = embedder or SentenceTransformerEmbedder(settings.embedding_model)
    index = index or VectorIndex(settings.index_dir)
    build_index(store, index, embedder)

    patients: dict[str, PatientRef] = {}
    snippets: dict[str, str] = {}
    for stored in store.list_bundles():
        record = read_bundle(stored.bundle)
        patients[record.patient_id] = PatientRef(
            patient_id=record.patient_id, name=record.name, mrn=record.mrn
        )
        summary = load_summary(store, record.patient_id)
        if summary is not None:
            diagnoses = "; ".join(summary.key_diagnoses)
            snippets[record.patient_id] = _snippet(f"{summary.chief_concern} {diagnoses}".strip())

    return AppState(
        settings=settings,
        store=store,
        index=index,
        embedder=embedder,
        search=SearchService(index, embedder),
        patients=patients,
        summary_snippets=snippets,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not hasattr(app.state, "ehr"):
        app.state.ehr = build_state(get_settings())
    yield


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.ehr
    return state


State = Annotated[AppState, Depends(get_state)]


def create_app(state: AppState | None = None) -> FastAPI:
    """Create the app. Pass ``state`` to inject test doubles."""
    app = FastAPI(
        title="EHR Media Intelligence API",
        version="0.1.0",
        description="Semantic search over synthetic FHIR R4 patient records.",
        lifespan=_lifespan,
        root_path=get_settings().api_root_path,
    )
    if state is not None:
        app.state.ehr = state

    @app.get("/health", response_model=Health)
    def health(state: State) -> Health:
        return Health(
            status="ok",
            patients=len(state.patients),
            indexed_entries=state.index.count(),
            embedding_model=state.embedder.name,
        )

    @app.post("/search", response_model=SearchResponse)
    def search(
        body: SearchRequest,
        state: State,
        resource_type: Annotated[
            ResourceType | None,
            Query(description="Only return this FHIR resource type. 'Patient' means AI summaries."),
        ] = None,
        date_from: Annotated[
            date | None, Query(description="Earliest record date, inclusive (YYYY-MM-DD).")
        ] = None,
        date_to: Annotated[
            date | None, Query(description="Latest record date, inclusive (YYYY-MM-DD).")
        ] = None,
    ) -> SearchResponse:
        """Return the records most relevant to a free-text query, best first."""
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must not be after date_to")

        started = time.perf_counter()
        filters = SearchFilters(resource_type, date_from, date_to)
        matches = state.search.search(body.query, filters, top_k=state.settings.search_top_k)
        results = [
            SearchResult(
                resource_id=match.metadata["resource_id"],
                resource_type=match.metadata["resource_type"],
                title=match.metadata["title"],
                category=match.metadata["category"],
                record_date=match.metadata.get("record_date"),
                relevance=match.relevance,
                patient=state.patients[match.metadata["patient_id"]],
                summary_snippet=state.summary_snippets.get(match.metadata["patient_id"]),
            )
            for match in matches
        ]
        return SearchResponse(
            query=body.query,
            filters=AppliedFilters(
                resource_type=resource_type, date_from=date_from, date_to=date_to
            ),
            count=len(results),
            took_ms=round((time.perf_counter() - started) * 1000, 1),
            results=results,
        )

    @app.get("/patients/{patient_id}", response_model=PatientDetail)
    def patient_detail(patient_id: str, state: State) -> PatientDetail:
        """A patient's AI summary, data-quality notes and linked FHIR resources."""
        stored = state.store.get_bundle(patient_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        return build_patient_detail(state.store, stored)

    return app


app = create_app()
