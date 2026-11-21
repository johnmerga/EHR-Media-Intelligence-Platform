import type { ResourceType } from "../api/types";
import { RESOURCE_LABELS, formatPercent } from "../lib/format";

const RESOURCE_STYLES: Record<string, string> = {
  Patient: "bg-violet-50 text-violet-800 ring-violet-200",
  Encounter: "bg-slate-100 text-slate-700 ring-slate-200",
  DiagnosticReport: "bg-sky-50 text-sky-800 ring-sky-200",
  DocumentReference: "bg-amber-50 text-amber-900 ring-amber-200",
};
const DEFAULT_STYLE = "bg-slate-100 text-slate-700 ring-slate-200";

/**
 * In search results a `Patient` hit is that patient's AI summary, so it gets a
 * friendly label. Pass `fhirName` to show the plain FHIR type name instead.
 */
export function ResourceBadge({ type, fhirName = false }: { type: string; fhirName?: boolean }) {
  const label = fhirName ? type : (RESOURCE_LABELS[type as ResourceType] ?? type);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${RESOURCE_STYLES[type] ?? DEFAULT_STYLE}`}
      title={`FHIR resource type: ${type}`}
    >
      {label}
    </span>
  );
}

export function RelevanceScore({ relevance }: { relevance: number }) {
  const percent = formatPercent(relevance);
  return (
    <div className="flex items-center gap-2" aria-label={`Relevance ${percent}`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200" aria-hidden="true">
        <div className="h-full rounded-full bg-teal-600" style={{ width: percent }} />
      </div>
      <span className="w-9 text-right text-xs font-semibold tabular-nums text-slate-700">
        {percent}
      </span>
    </div>
  );
}

const CONFIDENCE_STYLES = {
  high: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  medium: "bg-amber-50 text-amber-900 ring-amber-200",
  low: "bg-rose-50 text-rose-800 ring-rose-200",
};

export function ConfidenceBadge({ level }: { level: "low" | "medium" | "high" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${CONFIDENCE_STYLES[level]}`}
    >
      {level.charAt(0).toUpperCase() + level.slice(1)} confidence
    </span>
  );
}
