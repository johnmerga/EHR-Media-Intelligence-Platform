"""Text embedding."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Local sentence-transformers model. Vectors are L2-normalized for cosine search."""

    def __init__(self, model_name: str) -> None:
        # Imported here because loading torch takes seconds and tests use a fake.
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        embedded: list[list[float]] = vectors.tolist()
        return embedded
