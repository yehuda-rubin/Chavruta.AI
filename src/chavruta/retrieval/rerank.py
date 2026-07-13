"""Reranker (research D5) — task T017.

Optional cross-encoder reranking (bge-reranker-v2-m3): sharpens ordering when compute is
available (cloud profile by default; optional locally). Config-gated via `profile.rerank`.

Uses sentence-transformers' CrossEncoder rather than FlagEmbedding's FlagReranker: the
latter calls `tokenizer.prepare_for_model`, which current transformers removed, breaking
the slow XLM-Roberta path. CrossEncoder runs the same model on a maintained code path.
"""

from __future__ import annotations

import math

from chavruta.retrieval.base import RankedHit


class Reranker:
    def __init__(self, model_id: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu",
                 use_fp16: bool | None = None):
        self.model_id = model_id
        self.device = device
        self._model = None  # lazy

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder  # lazy

            self._model = CrossEncoder(self.model_id, device=self.device)
        return self._model

    def rerank(self, query: str, hits: list[RankedHit]) -> list[RankedHit]:
        if not hits:
            return hits
        model = self._ensure()
        raw = model.predict([(query, h.text) for h in hits])
        for h, s in zip(hits, raw):
            # sigmoid → 0..1 (matches the previous normalize=True relevance semantics)
            h.score = 1.0 / (1.0 + math.exp(-float(s)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits
