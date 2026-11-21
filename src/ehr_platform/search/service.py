"""Build the index and answer search queries."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from ehr_platform.search.documents import IndexEntry, build_entries, fingerprint
from ehr_platform.search.embedder import Embedder
from ehr_platform.search.index import IndexMatch, VectorIndex
from ehr_platform.storage import Store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchFilters:
    resource_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None


def build_index(
    store: Store, index: VectorIndex, embedder: Embedder, *, force: bool = False
) -> int:
    """Embed every entry and replace the index, unless it is already up to date.

    Returns the number of entries in the index.
    """
    entries: list[IndexEntry] = build_entries(store)
    current = fingerprint(entries, embedder.name)
    if not force and index.fingerprint == current and index.count() == len(entries):
        logger.info("Search index is up to date (%d entries)", len(entries))
        return len(entries)

    vectors = embedder.embed([entry.text for entry in entries]) if entries else []
    index.rebuild(entries, vectors, current)
    logger.info("Indexed %d entries with %s", len(entries), embedder.name)
    return len(entries)


class SearchService:
    def __init__(self, index: VectorIndex, embedder: Embedder) -> None:
        self._index = index
        self._embedder = embedder

    def search(self, query: str, filters: SearchFilters, *, top_k: int) -> list[IndexMatch]:
        (vector,) = self._embedder.embed([query])
        return self._index.query(
            vector,
            top_k=top_k,
            resource_type=filters.resource_type,
            date_from=filters.date_from,
            date_to=filters.date_to,
        )
