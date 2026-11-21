import type { PatientDetail, SearchFilters, SearchResponse } from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const message =
      response.status === 429
        ? "Too many searches in a short time. Please wait a moment."
        : `The server returned an error (${response.status}).`;
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

/** POST /search: the query goes in the body, filters in the query string. */
export function searchRecords(
  query: string,
  filters: SearchFilters,
  signal: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams();
  if (filters.resourceType) params.set("resource_type", filters.resourceType);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  const suffix = params.size > 0 ? `?${params}` : "";

  return request<SearchResponse>(`/search${suffix}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    signal,
  });
}

export function fetchPatient(patientId: string, signal: AbortSignal): Promise<PatientDetail> {
  return request<PatientDetail>(`/patients/${encodeURIComponent(patientId)}`, { signal });
}
