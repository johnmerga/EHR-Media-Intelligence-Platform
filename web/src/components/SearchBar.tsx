import type { KeyboardEvent, RefObject } from "react";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onArrowDown: () => void;
  inputRef: RefObject<HTMLInputElement | null>;
}

export function SearchBar({ value, onChange, onSubmit, onArrowDown, inputRef }: SearchBarProps) {
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      onArrowDown();
    }
  }

  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="search-input" className="sr-only">
        Search patient records
      </label>
      <div className="relative">
        <svg
          className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-slate-400"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.45 4.39l3.08 3.08a.75.75 0 1 1-1.06 1.06l-3.08-3.08A7 7 0 0 1 2 9Z"
            clipRule="evenodd"
          />
        </svg>
        <input
          id="search-input"
          ref={inputRef}
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          maxLength={300}
          autoComplete="off"
          spellCheck={false}
          placeholder="Search records in plain language, e.g. elevated troponin"
          aria-describedby="search-hint"
          className="w-full rounded-lg border border-slate-300 bg-white py-3 pl-11 pr-4 text-base shadow-sm placeholder:text-slate-400 focus:border-teal-600"
        />
      </div>
      <p id="search-hint" className="sr-only">
        Results update as you type. Press the down arrow to move into the results.
      </p>
    </form>
  );
}
