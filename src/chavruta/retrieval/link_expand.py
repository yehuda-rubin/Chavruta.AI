"""LinkExpander (research D10) — task T016a.

Follows the Links graph + anchor chains from the anchor pesukim to related material:
supercommentaries (anchor_kind=commentary) and, across loaded corpora, the chain of
transmission (pasuk → Rishonim → Acharonim → Halacha). Returns RankedHits merged with the
vector hits by the retriever. Activates the full cross-corpus reach as corpora are loaded.
"""

from __future__ import annotations

from dataclasses import replace

from chavruta.corpus.refs import canonical_ref
from chavruta.corpus.schema import Query
from chavruta.retrieval.base import RankedHit
from chavruta.retrieval.hybrid import _to_hit


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
        # Reuse hybrid.py's own payload->RankedHit mapping instead of a second, hand-rolled one here:
        # a link-expanded hit is built from the exact same store payload shape as a direct vector hit,
        # so a second copy of the field list only invites the two to drift — which they had (lang,
        # text_he/text_en, license, version_title were missing here), silently blanking attribution
        # and reader-facing text for every source that arrived via link expansion instead of a direct
        # hit. Only the score differs (link-expanded hits rank below direct vector hits by design).
        return [replace(_to_hit(h), score=self.link_score) for h in raw]
