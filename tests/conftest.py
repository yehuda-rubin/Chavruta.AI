"""Shared test fakes — let the core logic (grounding, retrieval, pipeline) be validated
without heavy models, a running LLM, or the corpus on disk.

The fakes faithfully implement the backend contracts, so they double as conformance
vehicles for the deployment-agnostic interfaces (Principle II).
"""

from __future__ import annotations

import math
from collections.abc import Iterator

import pytest

from chavruta.embedding.base import Embedding
from chavruta.llm.base import GroundedPrompt, LLMResult
from chavruta.store.base import Filter, Hit, HybridQuery, StoredChunk


# ── Fake embedding (deterministic, tiny) ──
class FakeEmbedding:
    dim = 16
    model_id = "fake-embedding"

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for i, ch in enumerate(text):
            v[i % self.dim] += (ord(ch) % 17) / 17.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def _sparse(self, text: str) -> dict[int, float]:
        return {hash(tok) % 10000: 1.0 for tok in text.split()}

    def embed_query(self, text: str) -> Embedding:
        return Embedding(dense=self._vec(text), sparse=self._sparse(text))

    def embed_batch(self, texts: list[str]) -> list[Embedding]:
        return [self.embed_query(t) for t in texts]


# ── In-memory vector store (faithful to contracts/vector-store.md) ──
class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, StoredChunk]] = {}

    def ensure_collection(self, name: str, dim: int) -> None:
        self._data.setdefault(name, {})

    def upsert(self, name: str, chunks: list[StoredChunk]) -> None:
        coll = self._data.setdefault(name, {})
        for c in chunks:
            coll[c.chunk_id] = c   # idempotent by chunk_id

    def _matches(self, payload: dict, filters: Filter | None) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            pv = payload.get(key)
            if isinstance(value, (list, tuple)):
                if pv not in value:
                    return False
            elif pv != value:
                return False
        return True

    @staticmethod
    def _cos(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def search(self, name: str, query: HybridQuery, top_k: int,
               filters: Filter | None = None) -> list[Hit]:
        coll = self._data.get(name, {})
        scored = []
        for c in coll.values():
            if not self._matches(c.payload, filters):
                continue
            score = self._cos(query.dense, c.dense)
            if query.sparse:
                score += 0.5 * sum(query.sparse.get(i, 0.0) * w for i, w in c.sparse.items())
            scored.append(Hit(chunk_id=c.chunk_id, score=score, payload=c.payload))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    def dense_scores(self, name: str, dense, filters: Filter | None = None, top_k: int = 30) -> dict:
        coll = self._data.get(name, {})
        scored = {c.chunk_id: self._cos(dense, c.dense) for c in coll.values()
                  if self._matches(c.payload, filters)}
        return dict(sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:top_k])

    def top_dense_score(self, name: str, dense, filters: Filter | None = None) -> float:
        vals = [self._cos(dense, c.dense) for c in self._data.get(name, {}).values()
                if self._matches(c.payload, filters)]
        return max(vals) if vals else 0.0

    def count(self, name: str, filters: Filter | None = None) -> int:
        return sum(1 for c in self._data.get(name, {}).values() if self._matches(c.payload, filters))

    def delete(self, name: str, filters: Filter) -> None:
        coll = self._data.get(name, {})
        for cid in [cid for cid, c in coll.items() if self._matches(c.payload, filters)]:
            del coll[cid]

    def fetch_by_refs(self, name: str, refs: list[str], filters: Filter | None = None) -> list[Hit]:
        coll = self._data.get(name, {})
        out = []
        for c in coll.values():
            in_refs = c.payload.get("ref") in refs or c.payload.get("anchor_ref") in refs
            if in_refs and self._matches(c.payload, filters):
                out.append(Hit(chunk_id=c.chunk_id, score=1.0, payload=c.payload))
        return out


# ── Fake LLM (cites the first source so the grounding gate passes) ──
class FakeLLM:
    model_id = "fake-llm"
    profile = "test"

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        if not prompt.sources:
            return LLMResult(text="No sources." if lang == "en" else "אין מקורות.")
        first = prompt.sources[0]
        quote = first.text[:30]
        if lang == "he":
            return LLMResult(text=f"לפי המקור [{first.marker}]: {quote}")
        return LLMResult(text=f"According to [{first.marker}]: {quote}")

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        yield self.generate(prompt, lang=lang, max_tokens=max_tokens, temperature=temperature).text

    def request(self, body_md: str, *, lang: str = "he"):
        """Agentic-path (job markdown) answer — mirrors generate(): cite the first ### [S#] source. No
        self-fetch. Returns (text, fetched)."""
        import re
        m = re.search(r"###\s*\[\s*(S\d+)\s*\]", body_md or "")
        if not m:
            return ("No sources." if lang == "en" else "אין מקורות.", [])
        marker = m.group(1)
        return ((f"According to [{marker}]." if lang == "en" else f"לפי המקור [{marker}]."), [])


@pytest.fixture
def fake_embedding():
    return FakeEmbedding()


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def fake_llm():
    return FakeLLM()
