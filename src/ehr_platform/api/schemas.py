"""Request and response models of the HTTP API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from ehr_platform.summarization.models import ClinicalSummary

ResourceType = Literal["Patient", "DiagnosticReport", "DocumentReference"]


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class PatientRef(BaseModel):
    patient_id: str
    name: str
    mrn: str


class SearchResult(BaseModel):
    resource_id: str
    resource_type: ResourceType
    title: str
    category: str
    record_date: date | None
    relevance: float = Field(ge=0, le=1, description="Cosine similarity, 0 to 1.")
    patient: PatientRef
    summary_snippet: str | None = Field(description="Start of the patient's AI summary.")


class AppliedFilters(BaseModel):
    resource_type: ResourceType | None
    date_from: date | None
    date_to: date | None


class SearchResponse(BaseModel):
    query: str
    filters: AppliedFilters
    count: int
    took_ms: float
    results: list[SearchResult]


class DataQualityNote(BaseModel):
    severity: Literal["warning", "conflict"]
    field: str
    message: str
    kept_value: str | None
    rejected_value: str | None


class LinkedResource(BaseModel):
    resource_id: str
    resource_type: str
    title: str
    category: str | None
    record_date: date | None
    author: str | None
    abnormal: bool | None
    text: str | None
    fhir: dict[str, Any] = Field(description="The resource as stored, in FHIR R4 JSON.")


class PatientDetail(BaseModel):
    patient_id: str
    mrn: str
    name: str
    gender: str
    birth_date: date | None
    bundle_is_valid: bool
    summary: ClinicalSummary | None
    data_quality_notes: list[DataQualityNote]
    resources: list[LinkedResource]


class Health(BaseModel):
    status: Literal["ok"]
    patients: int
    indexed_entries: int
    embedding_model: str
