import { useCallback, useRef, useState } from "react";

import { fetchPatient } from "../api/client";
import type { PatientDetail } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { capitalize, formatDate } from "../lib/format";
import { ResourceItem } from "./ResourceItem";
import { SummaryPanel } from "./SummaryPanel";

interface PatientDrawerProps {
  patientId: string;
  patientName: string;
  matchedResourceId: string;
  onClose: () => void;
}

const SECTION_HEADING = "text-sm font-semibold text-slate-900";

function DataQualityNotes({ patient }: { patient: PatientDetail }) {
  if (patient.data_quality_notes.length === 0) return null;
  return (
    <section aria-labelledby="quality-heading" className="rounded-md border border-amber-300 bg-amber-50 p-3">
      <h3 id="quality-heading" className="text-sm font-semibold text-amber-950">
        Data-quality notes
      </h3>
      <ul className="mt-1.5 space-y-1.5 text-sm text-amber-950">
        {patient.data_quality_notes.map((note) => (
          <li key={`${note.field}-${note.message}`}>
            {note.message}
            {note.severity === "conflict" && (
              <span className="block text-xs text-amber-800">
                Kept {note.kept_value}; rejected {note.rejected_value}.
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function DrawerBody({ patient, matchedResourceId }: { patient: PatientDetail; matchedResourceId: string }) {
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-xs text-slate-500">MRN</dt>
          <dd className="font-mono text-slate-900">{patient.mrn}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Date of birth</dt>
          <dd className="text-slate-900">
            {patient.birth_date ? formatDate(patient.birth_date) : "Not recorded"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Gender</dt>
          <dd className="text-slate-900">{capitalize(patient.gender)}</dd>
        </div>
      </dl>

      <DataQualityNotes patient={patient} />

      <section aria-labelledby="summary-heading">
        <h3 id="summary-heading" className={SECTION_HEADING}>
          Clinical summary
        </h3>
        <div className="mt-2">
          <SummaryPanel summary={patient.summary} />
        </div>
      </section>

      <section aria-labelledby="resources-heading">
        <div className="flex items-baseline justify-between gap-2">
          <h3 id="resources-heading" className={SECTION_HEADING}>
            Linked FHIR resources ({patient.resources.length})
          </h3>
          <span className="text-xs text-slate-500">
            Bundle {patient.bundle_is_valid ? "passed" : "failed"} R4 validation
          </span>
        </div>
        <ul className="mt-2 space-y-2">
          {patient.resources.map((resource) => (
            <ResourceItem
              key={resource.resource_id}
              resource={resource}
              isMatch={resource.resource_id === matchedResourceId}
            />
          ))}
        </ul>
      </section>
    </div>
  );
}

export function PatientDrawer({ patientId, patientName, matchedResourceId, onClose }: PatientDrawerProps) {
  const panel = useRef<HTMLDivElement>(null);
  const [retryToken, setRetryToken] = useState(0);
  const load = useCallback((signal: AbortSignal) => fetchPatient(patientId, signal), [patientId]);
  const state = useAsync(patientId, load, retryToken);
  useFocusTrap(panel, onClose);

  return (
    <div className="fixed inset-0 z-20">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-slate-50 shadow-xl outline-none"
      >
        <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
          <h2 id="drawer-title" className="truncate text-lg font-semibold text-slate-900">
            {patientName}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
          >
            <span className="sr-only">Close patient details</span>
            <svg className="size-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5" aria-busy={state.status === "loading"}>
          {state.status === "loading" && (
            <div role="status" className="animate-pulse space-y-3">
              <span className="sr-only">Loading patient details</span>
              <div className="h-4 w-2/3 rounded bg-slate-200" />
              <div className="h-24 rounded bg-slate-200" />
              <div className="h-40 rounded bg-slate-200" />
            </div>
          )}
          {state.status === "error" && (
            <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
              <p>{state.message}</p>
              <button
                type="button"
                onClick={() => setRetryToken((token) => token + 1)}
                className="mt-3 rounded-md bg-rose-700 px-3 py-1.5 font-medium text-white hover:bg-rose-800"
              >
                Try again
              </button>
            </div>
          )}
          {state.status === "success" && (
            <DrawerBody patient={state.data} matchedResourceId={matchedResourceId} />
          )}
        </div>
      </div>
    </div>
  );
}
