import { useId, useState } from "react";

import type { LinkedResource } from "../api/types";
import { formatDate } from "../lib/format";
import { ResourceBadge } from "./Badges";

interface ResourceItemProps {
  resource: LinkedResource;
  isMatch: boolean;
}

/** One linked FHIR resource. Expands to show its text and the stored FHIR JSON. */
export function ResourceItem({ resource, isMatch }: ResourceItemProps) {
  const [isOpen, setIsOpen] = useState(isMatch);
  const [showFhir, setShowFhir] = useState(false);
  const panelId = useId();
  const details = [
    resource.category,
    // Patient and Encounter resources have no clinical text and may have no date.
    resource.record_date || resource.text ? formatDate(resource.record_date) : null,
    resource.author,
  ].filter(Boolean);

  return (
    <li
      className={`rounded-md border bg-white ${isMatch ? "border-teal-500 ring-1 ring-teal-500" : "border-slate-200"}`}
    >
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((open) => !open)}
        className="flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left hover:bg-slate-50"
      >
        <svg
          className={`mt-1 size-3.5 shrink-0 text-slate-400 transition-transform ${isOpen ? "rotate-90" : ""}`}
          viewBox="0 0 12 12"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M4 1.5 9 6l-5 4.5z" />
        </svg>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <ResourceBadge type={resource.resource_type} fhirName />
            <span className="text-sm font-medium text-slate-900">{resource.title}</span>
            {resource.abnormal && (
              <span className="rounded bg-rose-50 px-1.5 py-0.5 text-xs font-medium text-rose-800 ring-1 ring-inset ring-rose-200">
                Abnormal
              </span>
            )}
            {isMatch && (
              <span className="rounded bg-teal-50 px-1.5 py-0.5 text-xs font-medium text-teal-800 ring-1 ring-inset ring-teal-200">
                Matched your search
              </span>
            )}
          </span>
          {details.length > 0 && (
            <span className="mt-0.5 block text-xs text-slate-500">{details.join(" · ")}</span>
          )}
        </span>
      </button>

      {isOpen && (
        <div id={panelId} className="border-t border-slate-100 px-3 py-3">
          {resource.text && (
            <p className="text-sm leading-relaxed text-slate-800">{resource.text}</p>
          )}
          <button
            type="button"
            aria-expanded={showFhir}
            onClick={() => setShowFhir((shown) => !shown)}
            className={`rounded text-xs font-medium text-teal-700 hover:underline ${resource.text ? "mt-2" : ""}`}
          >
            {showFhir ? "Hide" : "Show"} FHIR R4 JSON
          </button>
          {showFhir && (
            <pre
              tabIndex={0}
              aria-label={`FHIR JSON for ${resource.title}`}
              className="mt-2 max-h-72 overflow-auto rounded bg-slate-900 p-3 text-xs leading-relaxed text-slate-100"
            >
              {JSON.stringify(resource.fhir, null, 2)}
            </pre>
          )}
        </div>
      )}
    </li>
  );
}
