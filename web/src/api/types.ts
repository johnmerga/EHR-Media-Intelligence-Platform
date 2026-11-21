// These types mirror the response models in src/ehr_platform/api/schemas.py.

export type ResourceType = "Patient" | "DiagnosticReport" | "DocumentReference";

export interface SearchFilters {
  resourceType: ResourceType | "";
  dateFrom: string;
  dateTo: string;
}

export interface PatientRef {
  patient_id: string;
  name: string;
  mrn: string;
}

export interface SearchResult {
  resource_id: string;
  resource_type: ResourceType;
  title: string;
  category: string;
  record_date: string | null;
  relevance: number;
  patient: PatientRef;
  summary_snippet: string | null;
}

export interface SearchResponse {
  query: string;
  count: number;
  took_ms: number;
  results: SearchResult[];
}

export interface MediaRecord {
  date: string;
  type: string;
  finding: string;
}

export interface ClinicalSummary {
  chief_concern: string;
  key_diagnoses: string[];
  recent_media_records: MediaRecord[];
  flagged_anomalies: string[];
  confidence: "low" | "medium" | "high";
  generator: "llm" | "rule_based";
  model: string;
  generated_at: string;
  disclaimer: string;
}

export interface DataQualityNote {
  severity: "warning" | "conflict";
  field: string;
  message: string;
  kept_value: string | null;
  rejected_value: string | null;
}

export interface LinkedResource {
  resource_id: string;
  resource_type: string;
  title: string;
  category: string | null;
  record_date: string | null;
  author: string | null;
  abnormal: boolean | null;
  text: string | null;
  fhir: Record<string, unknown>;
}

export interface PatientDetail {
  patient_id: string;
  mrn: string;
  name: string;
  gender: string;
  birth_date: string | null;
  bundle_is_valid: boolean;
  summary: ClinicalSummary | null;
  data_quality_notes: DataQualityNote[];
  resources: LinkedResource[];
}
