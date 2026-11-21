import type { ResourceType, SearchFilters } from "../api/types";

interface FiltersProps {
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
}

const FIELD =
  "mt-1 block h-9 w-full rounded-md border border-slate-300 bg-white px-2.5 text-sm shadow-sm focus:border-teal-600";
const LABEL = "block text-xs font-medium text-slate-600";

export const EMPTY_FILTERS: SearchFilters = { resourceType: "", dateFrom: "", dateTo: "" };

export function Filters({ filters, onChange }: FiltersProps) {
  const isActive = filters.resourceType !== "" || filters.dateFrom !== "" || filters.dateTo !== "";
  const rangeInverted =
    filters.dateFrom !== "" && filters.dateTo !== "" && filters.dateFrom > filters.dateTo;

  return (
    <fieldset className="mt-3">
      <legend className="sr-only">Filter results</legend>
      <div className="grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:items-end">
        <div className="col-span-2 sm:w-52">
          <label htmlFor="filter-type" className={LABEL}>
            Resource type
          </label>
          <select
            id="filter-type"
            className={FIELD}
            value={filters.resourceType}
            onChange={(event) =>
              onChange({ ...filters, resourceType: event.target.value as ResourceType | "" })
            }
          >
            <option value="">All types</option>
            <option value="DiagnosticReport">Diagnostic reports (labs, imaging)</option>
            <option value="DocumentReference">Documents (notes, summaries)</option>
            <option value="Patient">AI patient summaries</option>
          </select>
        </div>
        <div>
          <label htmlFor="filter-from" className={LABEL}>
            From
          </label>
          <input
            id="filter-from"
            type="date"
            className={FIELD}
            value={filters.dateFrom}
            max={filters.dateTo || undefined}
            onChange={(event) => onChange({ ...filters, dateFrom: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="filter-to" className={LABEL}>
            To
          </label>
          <input
            id="filter-to"
            type="date"
            className={FIELD}
            value={filters.dateTo}
            min={filters.dateFrom || undefined}
            aria-invalid={rangeInverted}
            aria-describedby={rangeInverted ? "filter-range-error" : undefined}
            onChange={(event) => onChange({ ...filters, dateTo: event.target.value })}
          />
        </div>
        {isActive && (
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="col-span-2 justify-self-start rounded-md px-2.5 py-1.5 text-sm font-medium text-teal-700 hover:bg-teal-50 sm:col-auto"
          >
            Clear filters
          </button>
        )}
      </div>
      {rangeInverted && (
        <p id="filter-range-error" role="alert" className="mt-2 text-sm text-rose-700">
          The "From" date is after the "To" date.
        </p>
      )}
    </fieldset>
  );
}
