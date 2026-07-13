"""EmbeddingBackend interface (contracts/embedding-backend.md).

Turns text into dense + sparse vectors. Same interface both profiles; device differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Embedding:
    dense: list[float]                       # length == backend.dim
    sparse: dict[int, float] = field(default_factory=dict)   # token-id -> weight (lexical)


@runtime_checkable
class EmbeddingBackend(Protocol):
    dim: int
    model_id: str

    def embed_query(self, text: str) -> Embedding: ...

    def embed_batch(self, texts: list[str]) -> list[Embedding]: ...
