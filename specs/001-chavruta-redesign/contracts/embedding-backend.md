# Contract: EmbeddingBackend

The seam that turns text into vectors. Same interface in both profiles (Principle II); the
concrete impl is `BgeM3Embedding`.

## Interface

```python
class EmbeddingBackend(Protocol):
    dim: int                      # dense dimension (bge-m3 = 1024)
    model_id: str                 # e.g. "BAAI/bge-m3"

    def embed_query(self, text: str) -> Embedding: ...
    def embed_batch(self, texts: list[str]) -> list[Embedding]: ...

class Embedding:
    dense: list[float]            # length == dim
    sparse: dict[int, float]      # token-id -> weight (lexical), may be empty
```

## Contract rules

- `embed_query` and `embed_batch` MUST produce vectors comparable in the same space (same
  model, same normalization).
- `dense` length MUST equal `dim` for every embedding.
- MUST be deterministic for a given text + model (reproducibility, Principle V).
- MUST run on CPU within the offline budget for single-query latency; batch/GPU path is for
  indexing only.
- MUST handle Hebrew and English input equivalently (Principle IV).

## Conformance tests (tests/contract)

- Embedding a Hebrew query and its English translation yields vectors whose nearest stored
  source is the same in ≥90% of eval pairs (supports FR-011/SC-003).
- `len(embed_query(x).dense) == dim`.
- Same input → identical vector across two calls.
