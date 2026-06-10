# Contract: VectorStore

Persists chunks + vectors and answers hybrid similarity searches. Same interface for Qdrant
embedded (local) and Qdrant server (cloud) — chosen by config (Principle II). Impl:
`QdrantStore`.

## Interface

```python
class VectorStore(Protocol):
    def ensure_collection(self, name: str, dim: int) -> None: ...
    def upsert(self, name: str, chunks: list[StoredChunk]) -> None: ...      # incremental
    def search(self, name: str, query: HybridQuery, top_k: int,
               filters: Filter | None = None) -> list[Hit]: ...
    def count(self, name: str, filters: Filter | None = None) -> int: ...
    def delete(self, name: str, filters: Filter) -> None: ...               # partial re-index

class HybridQuery:
    dense: list[float]
    sparse: dict[int, float] | None

class Hit:
    chunk_id: str
    score: float
    payload: dict           # full chunk metadata incl. ref, work_id, commentator_id, text, deep_link

Filter = dict   # e.g. {"work_id": "tanakh", "commentator_id": ["rashi","ramban"]}
```

## Contract rules

- `upsert` MUST be **idempotent** by `chunk_id` and support incremental adds without
  rebuilding the collection (FR-015).
- `search` MUST support **dense-only** and **dense+sparse (hybrid)** queries, and MUST honor
  `filters` (per-`work_id` / per-`commentator_id`) so retrieval can be scoped (Principle III).
- `delete` by filter MUST enable partial re-index of one work/ref range.
- The **same `payload` schema** is returned regardless of profile (no behavioral drift).
- Embedded and server modes MUST be selectable by config only.

## Conformance tests (tests/contract)

- Upserting the same chunk twice yields `count == 1` for it.
- A filtered search by `work_id` never returns chunks from another work.
- Hybrid search returns a superset-quality ranking vs dense-only on a fixed fixture
  (exact-term query finds the lexically-matching chunk).
- Same fixture returns equivalent hits in embedded and server modes (profile parity, SC-006).
