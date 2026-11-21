"""Vector index backed by an embedded ChromaDB collection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from ehr_platform.search.documents import IndexEntry

_COLLECTION = "ehr_records"


@dataclass(frozen=True)
class IndexMatch:
    entry_id: str
    relevance: float
    metadata: dict[str, Any]


class VectorIndex:
    """Cosine-similarity index with metadata filters.

    Pass a directory to persist the index, or ``None`` for an in-memory one.
    """

    def __init__(self, directory: Path | None) -> None:
        settings = ChromaSettings(anonymized_telemetry=False)
        if directory is None:
            self._client = chromadb.EphemeralClient(settings=settings)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(directory), settings=settings)
        self._collection = self._client.get_or_create_collection(
            _COLLECTION, configuration={"hnsw": {"space": "cosine"}}
        )

    @property
    def fingerprint(self) -> str | None:
        value = (self._collection.metadata or {}).get("fingerprint")
        return str(value) if value else None

    def count(self) -> int:
        return self._collection.count()

    def rebuild(
        self, entries: list[IndexEntry], vectors: list[list[float]], fingerprint: str
    ) -> None:
        """Replace the whole index."""
        self._client.delete_collection(_COLLECTION)
        self._collection = self._client.create_collection(
            _COLLECTION,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"fingerprint": fingerprint},
        )
        if entries:
            embeddings: list[Sequence[float] | Sequence[int]] = list(vectors)
            self._collection.add(
                ids=[entry.entry_id for entry in entries],
                embeddings=embeddings,
                metadatas=[entry.metadata() for entry in entries],
            )

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        resource_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[IndexMatch]:
        conditions: list[dict[str, Any]] = []
        if resource_type is not None:
            conditions.append({"resource_type": resource_type})
        if date_from is not None:
            conditions.append({"date_ordinal": {"$gte": date_from.toordinal()}})
        if date_to is not None:
            conditions.append({"date_ordinal": {"$lte": date_to.toordinal()}})
        where: Any = None
        if len(conditions) == 1:
            where = conditions[0]
        elif conditions:
            where = {"$and": conditions}

        result = self._collection.query(
            query_embeddings=[vector],  # type: ignore[arg-type]
            n_results=top_k,
            where=where,
            include=["metadatas", "distances"],
        )
        ids = result["ids"][0]
        distances = (result["distances"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        return [
            IndexMatch(
                entry_id=entry_id,
                # Cosine distance is 1 - similarity; clamp so scores stay in [0, 1].
                relevance=round(min(1.0, max(0.0, 1.0 - distance)), 4),
                metadata=dict(metadata),
            )
            for entry_id, distance, metadata in zip(ids, distances, metadatas, strict=True)
        ]
