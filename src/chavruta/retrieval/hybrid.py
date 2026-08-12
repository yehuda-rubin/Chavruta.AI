"""HybridRetriever (research D5) — task T016.

Embeds the query (dense + sparse via bge-m3), searches Qdrant with RRF fusion, scopes by
work / biases by named commentator, optionally reranks, optionally expands along links, then
dedups, anchors to pesukim, and applies a relevance threshold → `is_empty` (the honest
no-source signal that protects Principle I).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import replace

from chavruta.corpus.refs import (
    commentary_refs,
    commentator_from_ref,
    is_commentary_ref,
    license_for_ref,
    with_ref_variants,
)
from chavruta.corpus.schema import Query
from chavruta.retrieval.base import RankedHit, RetrievalResult
from chavruta.store.base import Filter, HybridQuery

logger = logging.getLogger(__name__)


@contextmanager
def _timed(acc: dict, key: str):
    """Accumulate wall-clock into `acc[key]`. Retrieval is many store round-trips, and until it was
    measured the assumption was that generation dominated a slow request — it does not."""
    t0 = time.monotonic()
    try:
        yield
    finally:
        acc[key] = acc.get(key, 0.0) + (time.monotonic() - t0)


def _to_hit(h) -> RankedHit:
    p = h.payload or {}
    # Rights are per LANGUAGE, not per work: Peninei Halakhah is CC-BY-NC in Hebrew and CC0 in
    # English. A chunk's `text` is in its own `lang`, so read the licence for THAT language.
    # `license`/`version_title` (unsuffixed) are the shape written by a fresh ingest; the
    # *_he/*_en pair is what the backfill stamps onto the already-indexed corpus. Accept both so a
    # partly-backfilled collection still reports honestly instead of silently reading blank.
    lang = (p.get("lang") or "he").lower()
    suffix = "en" if lang.startswith("en") else "he"
    return RankedHit(
        chunk_id=h.chunk_id,
        ref=p.get("ref", ""),
        text=p.get("text", ""),
        score=h.score,
        # The commercial corpus was indexed with `commentator_id` empty on all 2.4M points, and the
        # name is fully recoverable from the ref ('Rashi_on_Genesis.1.1.1' → 'rashi'). Deriving it
        # here costs a string split and needs no rewrite of an on-disk collection; the payload value
        # still wins where a fresh ingest wrote one.
        commentator_id=p.get("commentator_id") or commentator_from_ref(p.get("ref")),
        deep_link=p.get("deep_link", ""),
        work_id=p.get("work_id", ""),
        anchor_ref=p.get("anchor_ref"),
        period=p.get("period"),
        lang=lang,
        text_he=p.get("text_he") or "",
        text_en=p.get("text_en") or "",
        # …and if the payload carries neither (it carries neither on any point of the commercial
        # corpus), fall back to the work-level table. Licence is a property of the EDITION, not of
        # the chunk, so a per-work lookup is both correct and the only affordable option — see
        # docs/legal/REVIEW-2026-07-27.md finding C. Without this, attribution_line() renders empty
        # and the 464 CC-BY / 87 CC-BY-SA sources are reproduced with no credit, which is the
        # condition their licence is granted on.
        license=(p.get("license") or p.get(f"license_{suffix}")
                 or license_for_ref(p.get("ref"), lang)[0]),
        version_title=(p.get("version_title") or p.get(f"version_{suffix}")
                       or license_for_ref(p.get("ref"), lang)[1]),
    )


# The load-bearing sources a grounded answer should always be able to reach.
#
# These MUST be the `work_id` values the corpus actually carries, not the names the registry uses
# for them. They diverged: the collection tags the Talmud Bavli `gemara` and the responsa `shut`,
# so the floors below filtered on `talmud_bavli` — a value held by 0 of 2,403,599 points — and the
# single largest tier in the corpus (516,854 points) never had a reserved slot. A question whose
# answer lives in a sugya was competing for space against derush with no floor protecting it, which
# is exactly the shape of the failure reported 2026-08-12 (the Rashi/Tosafot machloket on Sukkah
# 41a: both sides sitting in the corpus, neither retrieved). Verified against the live collection —
# see the tier counts in docs/CORPUS.md.
_FOUNDATIONAL_WORKS = ("tanakh", "mishnah", "gemara", "halacha", "midrash")


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
        still boosted above the rest; this also brings the pasuk in for context)."""
        return {"work_id": list(query.work_ids)} if query.work_ids else None

    def retrieve(self, query: Query, *, top_k: int) -> RetrievalResult:
        t_all = time.monotonic()
        t: dict[str, float] = {}
        with _timed(t, "embed"):
            emb = self.embedding.embed_query(query.search_text or query.text)
        use_sparse = self.profile.hybrid and bool(emb.sparse)
        hquery = HybridQuery(dense=emb.dense, sparse=emb.sparse if use_sparse else None)

        # Read the named commentators BEFORE the empty-scope fallback below can clear them: on a
        # corpus where the `commentator_id` payload is empty the scoped search always comes back
        # empty, and that is precisely the question ("what does Rashi say here") whose anchoring
        # still has to know which commentator was asked for.
        wanted = {c.lower() for c in (query.commentator_ids or ())}

        filters = self._filters(query)
        try:
            with _timed(t, "search"):
                raw = self.store.search(
                    self.profile.collection, hquery, top_k=top_k * 3, filters=filters
                )
            if not raw and filters is not None:
                # A SCOPED search (work_ids / commentator_ids) came back empty. That scope can be wrong
                # — e.g. a hallucinated or mis-resolved named_ref pinned the query to the wrong tractate
                # (Bava Metzia for a Sanhedrin topic). A wrong scope must never collapse retrieval to
                # zero: fall back to an UNSCOPED semantic search so the topically-relevant sources still
                # surface. (The floors below also key off query.work_ids, so clear the scope for them.)
                logger.info("scoped retrieval empty; falling back to unscoped semantic search")
                with _timed(t, "search"):
                    raw = self.store.search(self.profile.collection, hquery, top_k=top_k * 3,
                                            filters=None)
                query = replace(query, work_ids=None, commentator_ids=None)
        except Exception as exc:
            # A backend failure (e.g. a Qdrant search timeout under load) must degrade to an honest
            # "no grounded source" rather than 500 the whole request.
            logger.warning("main retrieval search failed (%s); returning empty result", exc)
            return RetrievalResult(hits=[], anchor_refs=[], is_empty=True)
        hits = [_to_hit(h) for h in raw]

        # Per-hit relevance floor (hybrid only): prune off-topic-but-similar noise (e.g. Kilayim
        # sources surfacing for a Shabbat question). The RRF fusion score is NOT a cosine, so we read
        # each candidate's true DENSE cosine from a dense-only probe (`dense_map`, also reused for the
        # honesty gate below). We drop a hit ONLY if dense retrieval surfaced it with a sub-threshold
        # cosine — sparse/lexical-driven hits (absent from the dense map) and anchors/enrichment added
        # later are never pruned, so exact-term recall is preserved.
        dense_map: dict[str, float] = {}
        if use_sparse:
            try:
                with _timed(t, "dense_probe"):
                    dense_map = self.store.dense_scores(
                        self.profile.collection, emb.dense, self._filters(query), top_k=top_k * 3)
                thr = self.profile.relevance_threshold
                pruned = [h for h in hits
                          if not (h.chunk_id in dense_map and dense_map[h.chunk_id] < thr)]
                if pruned:                    # never let the floor alone empty the pool
                    hits = pruned
            except Exception:
                dense_map = {}

        # Named-ref anchoring: the question explicitly names a verse → fetch that verse and
        # everything anchored on it (exact, score above the relevance threshold by design).
        anchored_ids: set[str] = set()   # true named-ref anchors — the honest is_empty signal below
        if query.named_refs:
            # The router emits dotted refs ('Genesis.1.1') but the corpus stores base texts with a
            # space ('Genesis 1.1'); pass BOTH forms so the anchor actually resolves (without this the
            # exact match silently returned 0 → the base pasuk/daf never anchored).
            # The scope here is by WORK, never by commentator. `commentator_id` is empty on every
            # point of the commercial corpus, so a server-side filter on it matched nothing and the
            # anchor came back empty — the bug that answered "there is no Rashi here" with Rashi
            # sitting in the index.
            # `anchor_ref` is empty there too, so a ref lookup returns the base segment ALONE and
            # never its commentaries. A named commentator is therefore fetched by its own exact ref
            # ('Rashi_on_Genesis.1.1.k'), derived from the base ref — the one construction that does
            # not depend on either missing field. Refs that don't exist simply return nothing, so a
            # commentator with no comment here stays honestly absent.
            ref_variants = with_ref_variants(query.named_refs)
            targets = ref_variants + commentary_refs(ref_variants, wanted)
            with _timed(t, "anchor"):
                anchored = self.store.fetch_by_refs(
                    self.profile.collection, targets,
                    filters=self._work_filter(query),
                    limit=600 if wanted else None,
                )
            for h in anchored:
                rh = _to_hit(h)
                # A named commentator outranks the rest of the verse's commentaries; without a name
                # every anchor is equal, as before.
                rh.score = max(rh.score, 1.1 if (rh.commentator_id or "") in wanted else 1.0)
                anchored_ids.add(rh.chunk_id)          # explicit anchor set (see has_anchor below)
                hits.append(rh)

        # Base-source floor: within the foundational works, COMMENTARY chunks vastly outnumber base
        # ones, so a thematic / free-form / English query can fill every foundational slot with
        # commentary and never surface the actual pasuk/mishnah/daf. Reserve a few slots for the base
        # text — but ONLY where it is genuinely relevant (dense cosine ≥ threshold): the filtered
        # sub-search's RRF is not a cosine and would otherwise promote off-topic pesukim un-prunably.
        #
        # The filter used to be `unit_type: "source"`, on the belief that commentary could not satisfy
        # it. In this corpus it can: EVERY point carries unit_type="source" — 516,854 of 516,854 in
        # the gemara tier — and `Rashi_on_Bava_Metzia.42.1.1` and `Bava_Metzia.42.1` are identical on
        # both work_id and unit_type. So the floor reserved nothing and the base text kept losing to
        # its own commentaries, which is the dominant failure in eval/torah_questions_v1.jsonl:
        # "found Rashi on the sugya, missed the sugya".
        #
        # The one reliable signal is the ref shape — a commentary ref carries `_on_`. It isn't a
        # server-side filter, so over-fetch and drop commentary here.
        if not query.work_ids and not query.commentator_ids:
            try:
                bfilt = {"work_id": list(_FOUNDATIONAL_WORKS)}
                with _timed(t, "floors"):
                    base = self.store.search(self.profile.collection, hquery, top_k=24, filters=bfilt)
                    bmap = self.store.dense_scores(self.profile.collection, emb.dense, bfilt, top_k=24) \
                        if use_sparse else {}
                thr = self.profile.relevance_threshold
                kept = 0
                for h in base:
                    if kept >= 3:
                        break
                    rh = _to_hit(h)
                    if is_commentary_ref(rh.ref):      # the point of this floor is the base text
                        continue
                    if not use_sparse or bmap.get(rh.chunk_id, 0.0) >= thr:
                        rh.score = min(rh.score, 0.99)   # never masquerade as a named-ref anchor
                        hits.append(rh)
                        kept += 1
            except Exception:
                pass

        # Foundational-source floor: on thematic topics (חגים, מחשבה) derush/Chassidut saturates the
        # topic vocabulary and crowds out the terse foundational mechanics. Reserve a few slots for
        # foundational works (pasuk/Mishnah/Gemara/halacha), gently boosted, so the model always has a
        # grounding source available. Skipped when the query is already scoped to a work/commentator.
        if not query.work_ids and not query.commentator_ids:
            try:
                with _timed(t, "floors"):
                    found = self.store.search(self.profile.collection, hquery, top_k=6,
                                              filters={"work_id": list(_FOUNDATIONAL_WORKS)})
                for h in found:
                    rh = _to_hit(h)
                    rh.score = min(rh.score + 0.05, 0.99)   # boost, but never reach the anchor sentinel
                    hits.append(rh)
            except Exception:
                pass

        # Optional reranking (heavy in cloud / optional local)
        if self.reranker is not None and self.profile.rerank and hits:
            with _timed(t, "rerank"):
                hits = self.reranker.rerank(query.text, hits)

        # Optional link-based expansion (chain of transmission / supercommentary). This is an
        # ENRICHMENT step — if it fails (e.g. a Qdrant scroll timeout on the large collection) it
        # must degrade to the base hybrid hits, never crash the whole query.
        anchor_refs = self._anchor_refs(hits)
        if query.expand_links and self.link_expander is not None and anchor_refs:
            try:
                with _timed(t, "links"):
                    hits = hits + self.link_expander.expand(anchor_refs, query)
            except Exception as exc:
                logger.warning("link expansion failed (%s); serving base hits", exc)

        hits = self._dedup(hits)
        hits.sort(key=lambda h: h.score, reverse=True)
        hits = hits[:top_k]

        # Relevance / honesty gate. hits[0].score is never a clean cosine here (hybrid → RRF fusion
        # score; dense-only → possibly floor-boosted/capped), so both non-anchor branches probe the raw
        # top-1 dense cosine instead of trusting the ranked score. A genuine
        # named-ref anchor is always relevant — tracked by chunk_id in `anchored_ids` (NOT `score ≥ 1.0`,
        # which a boosted floor hit could trip and a reranker's sigmoid could erase).
        has_anchor = any(h.chunk_id in anchored_ids for h in hits)
        if not hits:
            is_empty = True
        elif has_anchor:
            is_empty = False
        elif use_sparse:
            # reuse the dense probe from the per-hit floor (max cosine = top-1 dense score); fall back
            # to a fresh top-1 probe only if the map is unavailable.
            top_dense = (max(dense_map.values()) if dense_map
                         else self.store.top_dense_score(self.profile.collection, emb.dense,
                                                         self._filters(query)))
            is_empty = top_dense < self.profile.relevance_threshold
        else:
            # dense-only: hits[0].score is NOT a clean cosine — the foundational floor boosts by +0.05
            # and the base-source floor caps at 0.99, either of which could lift an off-topic hit over
            # the threshold and flip is_empty to False dishonestly. Probe the true top-1 dense cosine.
            top_dense = self.store.top_dense_score(self.profile.collection, emb.dense,
                                                   self._filters(query))
            is_empty = top_dense < self.profile.relevance_threshold
        total = time.monotonic() - t_all
        # One line per retrieval. Generation was assumed to be what made a request slow; measuring
        # showed retrieval is a comparable share of it, and this is the breakdown that says which
        # store round-trip to attack.
        logger.info(
            "retrieval done total=%.1fs [%s] hits=%d empty=%s top_k=%d hybrid=%s",
            total,
            " ".join(f"{k}={v:.1f}s" for k, v in sorted(t.items(), key=lambda kv: -kv[1])),
            len(hits), is_empty, top_k, use_sparse,
        )
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
