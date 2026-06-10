"""HybridRetriever (research D5) — task T016.

Embeds the query (dense + sparse via bge-m3), searches Qdrant with RRF fusion, scopes by
work / biases by named commentator, optionally reranks, optionally expands along links, then
dedups, anchors to pesukim, and applies a relevance threshold → `is_empty` (the honest
no-source signal that protects Principle I).
"""

from __future__ import annotations

from chavruta.corpus.schema import Query, UnitType
from chavruta.retrieval.base import RankedHit, RetrievalResult
from chavruta.store.base import Filter, HybridQuery


def _to_hit(h) -> RankedHit:
    p = h.payload or {}
    return RankedHit(
        chunk_id=h.chunk_id,
        ref=p.get("ref", ""),
        text=p.get("text", ""),
        score=h.score,
        commentator_id=p.get("commentator_id"),
        deep_link=p.get("deep_link", ""),
        work_id=p.get("work_id", ""),
        anchor_ref=p.get("anchor_ref"),
    )


class HybridRetriever:
    def __init__(self, embedding, store, profile, *, reranker=None, link_expander=None):
        self.embedding = embedding
        self.store = store
        self.profile = profile
        self.reranker = reranker
        self.link_expander = link_expander

    def _filters(self, query: Query) -> Filter | None:
        f: Filter = {}
        if query.work_ids:
            f["work_id"] = list(query.work_ids)
        if query.commentator_ids:
            f["commentator_id"] = list(query.commentator_ids)
        return f or None

    def retrieve(self, query: Query, *, top_k: int) -> RetrievalResult:
        emb = self.embedding.embed_query(query.text)
        use_sparse = self.profile.hybrid and bool(emb.sparse)
        hquery = HybridQuery(dense=emb.dense, sparse=emb.sparse if use_sparse else None)

        raw = self.store.search(
            self.profile.collection, hquery, top_k=top_k * 3, filters=self._filters(query)
        )
        hits = [_to_hit(h) for h in raw]

        # Optional reranking (heavy in cloud / optional local)
        if self.reranker is not None and self.profile.rerank and hits:
            hits = self.reranker.rerank(query.text, hits)

        # Optional link-based expansion (chain of transmission / supercommentary)
        anchor_refs = self._anchor_refs(hits)
        if query.expand_links and self.link_expander is not None and anchor_refs:
            hits = hits + self.link_expander.expand(anchor_refs, query)

        hits = self._dedup(hits)
        hits.sort(key=lambda h: h.score, reverse=True)
        hits = hits[:top_k]

        is_empty = (not hits) or (hits[0].score < self.profile.relevance_threshold)
        return RetrievalResult(
            hits=[] if is_empty else hits,
            anchor_refs=self._anchor_refs(hits),
            is_empty=is_empty,
        )

    @staticmethod
    def _anchor_refs(hits: list[RankedHit]) -> list[str]:
        refs: list[str] = []
        for h in hits:
            ref = h.anchor_ref or (h.ref if not h.commentator_id else None)
            if ref and ref not in refs:
                refs.append(ref)
        return refs

    @staticmethod
    def _dedup(hits: list[RankedHit]) -> list[RankedHit]:
        seen: set[str] = set()
        out: list[RankedHit] = []
        for h in hits:
            if h.chunk_id in seen:
                continue
            seen.add(h.chunk_id)
            out.append(h)
        return out
