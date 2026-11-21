import type { ResourceType } from "../api/types";

const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

/** Format an ISO date (YYYY-MM-DD) without shifting it across time zones. */
export function formatDate(iso: string | null): string {
  if (!iso) return "Undated";
  const parsed = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? iso : DATE_FORMAT.format(parsed);
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

export const RESOURCE_LABELS: Record<ResourceType, string> = {
  Patient: "AI summary",
  DiagnosticReport: "Diagnostic report",
  DocumentReference: "Document",
};

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
