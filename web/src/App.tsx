import { useCallback, useEffect, useRef, useState } from "react";

import { searchRecords } from "./api/client";
import type { SearchFilters, SearchResult } from "./api/types";
import { EMPTY_FILTERS, Filters } from "./components/Filters";
import { PatientDrawer } from "./components/PatientDrawer";
import { ResultList } from "./components/ResultList";
import { EmptyState, ErrorState, LoadingState, WelcomeState } from "./components/ResultStates";
import { SearchBar } from "./components/SearchBar";
import { useAsync } from "./hooks/useAsync";
import { useDebouncedValue } from "./hooks/useDebouncedValue";

const DEBOUNCE_MS = 300;

function isValid(filters: SearchFilters): boolean {
  return !(filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo);
}

/** The query is kept in the URL (?q=...) so a search can be bookmarked or shared. */
function queryFromUrl(): string {
  return new URLSearchParams(window.location.search).get("q") ?? "";
}

export function App() {
  const [input, setInput] = useState(queryFromUrl);
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [submitted, setSubmitted] = useState<string | null>(queryFromUrl);
  const [retryToken, setRetryToken] = useState(0);
  const [selected, setSelected] = useState<SearchResult | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const firstResultRef = useRef<HTMLButtonElement>(null);

  // Search as the user types (debounced); Enter or an example searches at once.
  const debounced = useDebouncedValue(input, DEBOUNCE_MS);
  const query = (submitted === input ? submitted : debounced).trim();
  const hasFilters = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
  const requestKey = query && isValid(filters) ? JSON.stringify([query, filters]) : null;

  const runSearch = useCallback(
    (signal: AbortSignal) => searchRecords(query, filters, signal),
    [query, filters],
  );
  const search = useAsync(requestKey, runSearch, retryToken);
  const closeDrawer = useCallback(() => setSelected(null), []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
  }, [query]);

  function searchNow(text: string) {
    setInput(text);
    setSubmitted(text);
  }

  const announcement =
    search.status === "loading"
      ? "Searching"
      : search.status === "success"
        ? `${search.data.count} ${search.data.count === 1 ? "result" : "results"} for ${search.data.query}`
        : "";

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#results"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-30 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:shadow"
      >
        Skip to results
      </a>

      <p className="bg-slate-800 px-4 py-1.5 text-center text-xs text-slate-100">
        Demonstration only. Every patient and record shown here is synthetic.
      </p>

      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-4">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <h1 className="text-lg font-semibold leading-tight text-slate-900">
              EHR Media Intelligence
            </h1>
            <p className="text-sm text-slate-600">
              Semantic search over FHIR R4 patient records
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
        <section aria-label="Search">
          <SearchBar
            value={input}
            onChange={setInput}
            onSubmit={() => setSubmitted(input)}
            onArrowDown={() => firstResultRef.current?.focus()}
            inputRef={inputRef}
          />
          <Filters filters={filters} onChange={setFilters} />
        </section>

        <section
          id="results"
          aria-label="Results"
          aria-busy={search.status === "loading"}
          className="mt-6"
        >
          <p className="sr-only" role="status" aria-live="polite">
            {announcement}
          </p>

          {search.status === "idle" && <WelcomeState onExample={searchNow} />}
          {search.status === "loading" && <LoadingState />}
          {search.status === "error" && (
            <ErrorState
              message={search.message}
              onRetry={() => setRetryToken((token) => token + 1)}
            />
          )}
          {search.status === "success" && search.data.count === 0 && (
            <EmptyState query={search.data.query} hasFilters={hasFilters} />
          )}
          {search.status === "success" && search.data.count > 0 && (
            <>
              <p className="mb-3 text-sm text-slate-600" aria-hidden="true">
                Top {search.data.count} {search.data.count === 1 ? "match" : "matches"} in{" "}
                {search.data.took_ms.toFixed(0)} ms
              </p>
              <ResultList
                results={search.data.results}
                onOpen={setSelected}
                firstResultRef={firstResultRef}
                onLeaveTop={() => inputRef.current?.focus()}
              />
            </>
          )}
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white px-4 py-3 text-center text-xs text-slate-500">
        AI summaries are generated by a language model, may contain errors and are not clinical
        decisions.
      </footer>

      {selected && (
        <PatientDrawer
          patientId={selected.patient.patient_id}
          patientName={selected.patient.name}
          matchedResourceId={selected.resource_id}
          onClose={closeDrawer}
        />
      )}
    </div>
  );
}
