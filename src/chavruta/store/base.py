"""VectorStore interface (contracts/vector-store.md).

Persists chunks + vectors and answers hybrid similarity searches. Same interface for Qdrant
embedded (local) and server (cloud). `Filter` scopes search per work / commentator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

Filter = dict   # e.g. {"work_id": "tanakh", "commentator_id": ["rashi", "ramban"]}


@dataclass
class StoredChunk:
    chunk_id: str
    dense: list[float]
    sparse: dict[int, float]
    payload: dict                            # Chunk.to_payload()


@dataclass
class HybridQuery:
    dense: list[float]
    sparse: Optional[dict[int, float]] = None


@dataclass
class Hit:
    chunk_id: str
    score: float
    payload: dict = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    def ensure_collection(self, name: str, dim: int) -> None: ...

    def upsert(self, name: str, chunks: list[StoredChunk]) -> None: ...

    def search(
        self, name: str, query: HybridQuery, top_k: int, filters: Optional[Filter] = None
    ) -> list[Hit]: ...

    def count(self, name: str, filters: Optional[Filter] = None) -> int: ...

    def delete(self, name: str, filters: Filter) -> None: ...

    def fetch_by_refs(
        self, name: str, refs: list[str], filters: Optional[Filter] = None
    ) -> list[Hit]: ...   # non-vector lookup, used by link-based retrieval
