import type { KeyboardEvent, Ref } from "react";

import type { SearchResult } from "../api/types";
import { formatDate } from "../lib/format";
import { RelevanceScore, ResourceBadge } from "./Badges";

interface ResultCardProps {
  result: SearchResult;
  position: number;
  onOpen: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  buttonRef: Ref<HTMLButtonElement>;
}

export function ResultCard({ result, position, onOpen, onKeyDown, buttonRef }: ResultCardProps) {
  return (
    <li>
      <button
        ref={buttonRef}
        type="button"
        onClick={onOpen}
        onKeyDown={onKeyDown}
        aria-haspopup="dialog"
        aria-label={`Result ${position}: ${result.title} for ${result.patient.name}. Open patient details.`}
        className="group w-full rounded-lg border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-teal-500 hover:shadow"
      >
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-slate-900 group-hover:text-teal-800">
              {result.patient.name}
            </p>
            <p className="font-mono text-xs text-slate-500">{result.patient.mrn}</p>
          </div>
          <RelevanceScore relevance={result.relevance} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-sm">
          <ResourceBadge type={result.resource_type} />
          <span className="font-medium text-slate-800">{result.title}</span>
          <time
            className="whitespace-nowrap text-slate-600"
            dateTime={result.record_date ?? undefined}
          >
            {formatDate(result.record_date)}
          </time>
        </div>

        {result.summary_snippet && (
          <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-slate-600">
            <span className="font-medium text-slate-700">Summary: </span>
            {result.summary_snippet}
          </p>
        )}
      </button>
    </li>
  );
}
