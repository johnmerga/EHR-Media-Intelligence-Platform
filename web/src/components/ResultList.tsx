import { type KeyboardEvent, type RefObject, useRef } from "react";

import type { SearchResult } from "../api/types";
import { ResultCard } from "./ResultCard";

interface ResultListProps {
  results: SearchResult[];
  onOpen: (result: SearchResult) => void;
  /** Lets the search bar move focus into the list. */
  firstResultRef: RefObject<HTMLButtonElement | null>;
  onLeaveTop: () => void;
}

/** Results as a list; arrow keys, Home and End move between cards. */
export function ResultList({ results, onOpen, firstResultRef, onLeaveTop }: ResultListProps) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = results.length - 1;
    const target = {
      ArrowDown: Math.min(index + 1, last),
      ArrowUp: index - 1,
      Home: 0,
      End: last,
    }[event.key];
    if (target === undefined) return;
    event.preventDefault();
    if (target < 0) onLeaveTop();
    else buttons.current[target]?.focus();
  }

  return (
    <ol className="space-y-3" aria-label="Search results, most relevant first">
      {results.map((result, index) => (
        <ResultCard
          key={result.resource_id}
          result={result}
          position={index + 1}
          onOpen={() => onOpen(result)}
          onKeyDown={(event) => onKeyDown(event, index)}
          buttonRef={(node) => {
            buttons.current[index] = node;
            if (index === 0) firstResultRef.current = node;
          }}
        />
      ))}
    </ol>
  );
}
