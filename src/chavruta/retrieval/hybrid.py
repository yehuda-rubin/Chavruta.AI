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
        period=p.get("period"),
    )


# The load-bearing sources a grounded answer should always be able to reach.
_FOUNDATIONAL_WORKS = ("tanakh", "mishnah", "talmud_bavli", "halacha", "midrash")


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

    def _work_filter(self, query: Query) -> Filter | None:
        """Work scope only — used for ref anchoring so the verse itself and ALL its
        commentaries are fetched, not just the named commentators (the named ones are
        still boosted to score 1.0; this also brings the pasuk in for context)."""
        return {"work_id": list(query.work_ids)} if query.work_ids else None

    def retrieve(self, query: Query, *, top_k: int) -> RetrievalResult:
        emb = self.embedding.embed_query(query.search_text or query.text)
        use_sparse = self.profile.hybrid and bool(emb.sparse)
        hquery = HybridQuery(dense=emb.dense, sparse=emb.sparse if use_sparse else None)

        raw = self.store.search(
            self.profile.collection, hquery, top_k=top_k * 3, filters=self._filters(query)
        )
        hits = [_to_hit(h) for h in raw]

        # Named-ref anchoring: the question explicitly names a verse → fetch that verse and
        # everything anchored on it (exact, score above the relevance threshold by design).
        if query.named_refs:
            # Named commentators → fetch them *specifically* on the ref (small, never
            # truncated), guaranteeing e.g. Rashi AND Ramban on Genesis.1.1. No named
            # commentator → fetch the verse + all its commentaries (work scope) for context.
            anchor_filter = self._filters(query) if query.commentator_ids else self._work_filter(query)
            anchored = self.store.fetch_by_refs(
                self.profile.collection, query.named_refs, filters=anchor_filter
            )
            for h in anchored:
                rh = _to_hit(h)
                rh.score = max(rh.score, 1.0)
                hits.append(rh)

        # Foundational-source floor: on thematic topics (חגים, מחשבה) derush/Chassidut saturates the
        # topic vocabulary and crowds out the terse foundational mechanics. Reserve a few slots for
        # foundational works (pasuk/Mishnah/Gemara/halacha), gently boosted, so the model always has a
        # grounding source available. Skipped when the query is already scoped to a work/commentator.
        if not query.work_ids and not query.commentator_ids:
            try:
                found = self.store.search(self.profile.collection, hquery, top_k=6,
                                          filters={"work_id": list(_FOUNDATIONAL_WORKS)})
                for h in found:
                    rh = _to_hit(h)
                    rh.score += 0.05
                    hits.append(rh)
            except Exception:
                pass

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

        # Relevance / honesty gate. hits[0].score is a COSINE only in dense-only mode; in hybrid it is
        # an RRF fusion score on a different scale, so we probe the raw dense cosine instead. Exact
        # named-ref anchors (score ≥ 1.0) are always relevant.
        has_anchor = any(h.score >= 1.0 for h in hits)
        if not hits:
            is_empty = True
        elif has_anchor:
            is_empty = False
        elif use_sparse:
            top_dense = self.store.top_dense_score(self.profile.collection, emb.dense, self._filters(query))
            is_empty = top_dense < self.profile.relevance_threshold
        else:
            is_empty = hits[0].score < self.profile.relevance_threshold
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
        # Keep the HIGHEST-scoring occurrence per chunk: an anchored hit (score 1.0) must
        # win over the same chunk appearing as a low-scored vector hit, otherwise a verse's
        # named commentator can be demoted out of top_k (it returns sorted by the caller).
        best: dict[str, RankedHit] = {}
        for h in hits:
            cur = best.get(h.chunk_id)
            if cur is None or h.score > cur.score:
                best[h.chunk_id] = h
        return list(best.values())
