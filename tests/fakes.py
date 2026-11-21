"""Test doubles."""

from __future__ import annotations

import hashlib
import math
import re


class FakeEmbedder:
    """Deterministic bag-of-words embedding: texts that share words are similar.

    It stands in for the sentence-transformers model so search logic can be
    tested in milliseconds and without downloading anything.
    """

    name = "fake-bag-of-words"
    dimensions = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
