# Contract: Retriever

Turns a question into a ranked, grounded set of source chunks. Composes EmbeddingBackend +
VectorStore + optional Reranker. Impl: `HybridRetriever`.

## Interface

```python
class Retriever(Protocol):
    def retrieve(self, query: Query, *, top_k: int) -> RetrievalResult: ...

class Query:
    text: str
    lang: str
    work_ids: list[str] | None        # corpus scoping (default: all loaded)
    commentator_ids: list[str] | None # named-commentator bias/filter
    intent: str                        # qa | explain | lesson
    expand_links: bool = False         # follow Link edges + anchor chains from the anchors
    expand_depth: int = 1              # how far to traverse (e.g. pasuk → commentary → supercommentary)

class RetrievalResult:
    hits: list[RankedHit]              # ordered, deduped, pasuk-anchored, per-commentator
    anchor_refs: list[str]             # the primary pesukim the answer hangs on
    is_empty: bool                     # True → honest "no grounded source" (FR-003)

class RankedHit:
    chunk_id: str; ref: str; commentator_id: str | None
    text: str; deep_link: str; score: float
```

## Contract rules

- MUST run **hybrid** retrieval (dense + sparse via RRF) by default; dense-only is a config
  fallback (D5).
- When `expand_links` is set, MUST follow **Link edges and `anchor_ref` chains** from the
  anchor pesukim — gathering supercommentaries (anchor_kind=commentary) and, across loaded
  corpora, the Rishonim/Acharonim/Halacha along the chain — then merge with the vector hits
  (D10). Expansion MUST stay scoped to loaded works and respect `expand_depth`.
- Reranking is **optional** and config-gated (heavy reranker in cloud; optional local) — the
  interface is identical whether or not it runs.
- MUST honor `work_ids` scoping (Principle III) and bias toward `commentator_ids` when the
  question names commentators (FR-006/007).
- MUST set `is_empty = True` when no hit clears the relevance threshold, so the pipeline can
  return the honest no-source answer rather than forcing generation (Principle I).
- MUST dedupe and anchor results to their pesukim and group per commentator so citations are
  precise and attributions correct (FR-004).
- MUST be interactive on the offline target (retrieval ~1s budget).

## Conformance tests (tests/contract)

- A query naming "רש״י" surfaces Rashi's comment on the relevant verse above unrelated hits.
- An out-of-corpus query returns `is_empty = True` (drives FR-003 / SC-002).
- Scoping to `work_ids=["tanakh"]` excludes other works.
- Retrieval@K for the eval set meets the target that ≥95% grounded answers cite a real,
  relevant source (SC-001) — measured by the harness.
