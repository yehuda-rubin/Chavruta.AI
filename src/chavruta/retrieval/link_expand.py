"""LinkExpander (research D10) — task T016a.

Follows the Links graph + anchor chains from the anchor pesukim to related material:
supercommentaries (anchor_kind=commentary) and, across loaded corpora, the chain of
transmission (pasuk → Rishonim → Acharonim → Halacha). Returns RankedHits merged with the
vector hits by the retriever. Activates the full cross-corpus reach as corpora are loaded.
"""

from __future__ import annotations

from chavruta.corpus.links import LinkGraph
from chavruta.corpus.schema import Query
from chavruta.retrieval.base import RankedHit


class LinkExpander:
    def __init__(self, store, link_graph: LinkGraph, profile, *, link_score: float = 0.5):
        self.store = store
        self.link_graph = link_graph
        self.profile = profile
        self.link_score = link_score  # expanded hits score below direct vector hits

    def expand(self, anchor_refs: list[str], query: Query) -> list[RankedHit]:
        reached = self.link_graph.expand(
            anchor_refs, depth=query.expand_depth, work_ids=query.work_ids
        )
        if not reached:
            return []
        filters = {"work_id": list(query.work_ids)} if query.work_ids else None
        raw = self.store.fetch_by_refs(self.profile.collection, reached, filters=filters)
        hits: list[RankedHit] = []
        for h in raw:
            p = h.payload or {}
            hits.append(RankedHit(
                chunk_id=h.chunk_id,
                ref=p.get("ref", ""),
                text=p.get("text", ""),
                score=self.link_score,
                commentator_id=p.get("commentator_id"),
                deep_link=p.get("deep_link", ""),
                work_id=p.get("work_id", ""),
                anchor_ref=p.get("anchor_ref"),
                period=p.get("period"),
            ))
        return hits
