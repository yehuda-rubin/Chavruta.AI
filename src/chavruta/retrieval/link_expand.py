"""LinkExpander (research D10) — task T016a.

Follows the Links graph + anchor chains from the anchor pesukim to related material:
supercommentaries (anchor_kind=commentary) and, across loaded corpora, the chain of
transmission (pasuk → Rishonim → Acharonim → Halacha). Returns RankedHits merged with the
vector hits by the retriever. Activates the full cross-corpus reach as corpora are loaded.
"""

from __future__ import annotations

from chavruta.corpus.refs import canonical_ref
from chavruta.corpus.schema import Query
from chavruta.retrieval.base import RankedHit


class LinkExpander:
    def __init__(self, store, link_graph, profile, *, link_score: float = 0.5,
                 ref_resolver=None, max_refs: int = 60):
        self.store = store
        self.link_graph = link_graph
        self.profile = profile
        self.link_score = link_score  # expanded hits score below direct vector hits
        # When the graph is keyed by CANONICAL refs (LinkStore), a resolver maps a canonical
        # neighbour back to the original chunk-ref strings the vector store stores.
        self.ref_resolver = ref_resolver
        self.max_refs = max_refs

    def expand(self, anchor_refs: list[str], query: Query) -> list[RankedHit]:
        if self.ref_resolver is not None:
            canon = [canonical_ref(r) for r in anchor_refs if r]
            reached_canon = self.link_graph.expand(canon, depth=query.expand_depth)
            reached, seen = [], set()
            for c in reached_canon:
                for orig in self.ref_resolver.originals(c):
                    if orig not in seen:
                        seen.add(orig)
                        reached.append(orig)
                if len(reached) >= self.max_refs:
                    break
        else:
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
