"""Reranker (research D5) — task T017.

Optional cross-encoder reranking (bge-reranker-v2-m3): sharpens ordering when compute is
available (cloud profile by default; optional locally). Config-gated via `profile.rerank`.
FlagEmbedding is imported lazily.
"""

from __future__ import annotations

from chavruta.retrieval.base import RankedHit


class Reranker:
    def __init__(self, model_id: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu",
                 use_fp16: bool | None = None):
        self.model_id = model_id
        self.device = device
        self._use_fp16 = (device != "cpu") if use_fp16 is None else use_fp16
        self._model = None  # lazy

    def _ensure(self):
        if self._model is None:
            from FlagEmbedding import FlagReranker  # lazy

            self._model = FlagReranker(self.model_id, use_fp16=self._use_fp16, device=self.device)
        return self._model

    def rerank(self, query: str, hits: list[RankedHit]) -> list[RankedHit]:
        if not hits:
            return hits
        model = self._ensure()
        scores = model.compute_score([[query, h.text] for h in hits], normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        for h, s in zip(hits, scores):
            h.score = float(s)
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits
