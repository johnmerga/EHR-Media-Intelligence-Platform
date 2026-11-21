import type { ReactNode } from "react";

export const EXAMPLE_QUERIES = [
  "elevated troponin after chest pain",
  "lung infection on chest x-ray",
  "suspicious breast mass",
  "worsening kidney function",
];

function Panel({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      {children}
    </div>
  );
}

export function WelcomeState({ onExample }: { onExample: (query: string) => void }) {
  return (
    <Panel>
      <h2 className="text-base font-semibold text-slate-900">Search across patient records</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
        Describe what you are looking for in your own words. Labs, imaging reports, clinical notes
        and AI summaries are searched by meaning, not just by keyword.
      </p>
      <p className="mt-5 text-xs font-medium uppercase tracking-wide text-slate-500">Try</p>
      <ul className="mt-2 flex flex-wrap justify-center gap-2">
        {EXAMPLE_QUERIES.map((query) => (
          <li key={query}>
            <button
              type="button"
              onClick={() => onExample(query)}
              className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-teal-500 hover:text-teal-800"
            >
              {query}
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function LoadingState() {
  return (
    <ul className="space-y-3" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <li key={index} className="animate-pulse rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex justify-between">
            <div className="h-4 w-40 rounded bg-slate-200" />
            <div className="h-3 w-24 rounded bg-slate-200" />
          </div>
          <div className="mt-4 h-3 w-64 max-w-full rounded bg-slate-200" />
          <div className="mt-3 h-3 w-full rounded bg-slate-100" />
          <div className="mt-2 h-3 w-4/5 rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}

export function EmptyState({ query, hasFilters }: { query: string; hasFilters: boolean }) {
  return (
    <Panel>
      <h2 className="text-base font-semibold text-slate-900">No matching records</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
        Nothing matched <span className="font-medium text-slate-800">"{query}"</span>
        {hasFilters
          ? " with the current filters. Try widening the date range or choosing all resource types."
          : ". Try describing the finding, test or diagnosis differently."}
      </p>
    </Panel>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-8 text-center">
      <h2 className="text-base font-semibold text-rose-900">Search failed</h2>
      <p className="mt-1 text-sm text-rose-800">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-md bg-rose-700 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-rose-800"
      >
        Try again
      </button>
    </div>
  );
}
