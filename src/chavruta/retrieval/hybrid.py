"""HybridRetriever (research D5) — task T016.

Embeds the query (dense + sparse via bge-m3), searches Qdrant with RRF fusion, scopes by
work / biases by named commentator, optionally reranks, optionally expands along links, then
dedups, anchors to pesukim, and applies a relevance threshold → `is_empty` (the honest
no-source signal that protects Principle I).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import replace

from chavruta.corpus.normalize import deuphemize_he, quote_windows
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

# ── Tunable constants ─────────────────────────────────────────────────────────────────────────
#
# Every number below was chosen by judgement, not measurement — there was no eval set large enough
# to tell a real 3% gain from noise (three consecutive retrieval changes all measured 52%). They are
# named module constants rather than inline literals SO THAT they can be measured:
# scripts/tune_retrieval.py sets them and scores the result against harvested ground truth, with the
# human-written eval sets held back as a veto. Read them at call time; do not copy into locals.

# How many slots of a result set are kept for base texts when the ranking would otherwise return
# commentary only. Small on purpose: the commentary IS usually what answers the question — the base
# text is what makes the answer checkable, and one or two of them is enough for that.
_BASE_SLOTS = 2

# …and what it takes to actually KEEP one. This floor was the only one of the three that appended
# its candidates and then gave them nothing, so they went back into the same score sort and lost:
# a pasuk at 0.30 does not survive next to a commentary at 0.66, and "reserved slot" described an
# intention the code never carried out. Reported from the other end on 2026-08-14 — a user asked for
# the source of a well-known idea, got a stack of works nobody has heard of, and said so: "אולי כדאי
# שיהיה לו סדר עדיפויות ושיביא קודם כל מהמקורות המוסמכים/קדומים/מוכרים יותר". His top-8 contained
# not one base text.
#
# Sized level with the foundational floor rather than above it, and capped below the named-ref
# anchor: a base text the user did not ask for by name must not outrank one they did. Like every
# constant here it is a judgement, and like every constant here it is a KNOB in
# scripts/tune_retrieval.py so the nightly run can replace the judgement with a measurement.
_BASE_BOOST = 0.05

# The foundational-works floor: how many candidates to pull, and how hard to lift them. The boost is
# capped below the named-ref anchor sentinel so a floor hit can never masquerade as something the
# user pointed at by name.
_FOUNDATIONAL_TOP_K = 6
_FOUNDATIONAL_BOOST = 0.05

# The named-tractate floor. Same shape, but capped lower still: naming a masechet is weaker evidence
# than naming a ref, and the ranking must keep saying so.
_TRACTATE_TOP_K = 6
_TRACTATE_BOOST = 0.05

# The quotation floor. A user who quotes a pasuk inside a sentence does not get the pasuk back: the
# frame around it dominates the embedding, and the source is never even a candidate for re-ranking
# to reach. Measured 2026-08-14 — "חלק אלוה ממעל" finds Iyov 31:2 at rank 2, the same three words
# inside "מה המקור לכך שהנשמה היא חלק אלוה ממעל?" find it nowhere in the top ten, and adding one
# word loses it again. So the phrase is searched on its own.
#
# `_QUOTE_WINDOWS` is a COST bound: each window is one search (cheap — measured at ~0ms against the
# on-disk collection) but all of them share ONE embedding batch, because embedding is the part that
# actually costs (~0.2s of a 0.5s retrieval). Four windows, one extra forward pass.
_QUOTE_WINDOWS = 4
_QUOTE_TOP_K = 3
_QUOTE_BOOST = 0.05

# `retrieve()` is the ONLY place in a request that touches the CPU-bound work — bge-m3 embedding
# and the Qdrant round-trips (both floors and the quote windows). Measured live 2026-08-19: a call
# takes 0.6-1.6s typically, up to ~8.7s under contention, against a total request time of 30-100s+
# — the rest is waiting on the LLM API over the network, which holds no CPU at all. Before this,
# app/api.py's one semaphore covered the WHOLE request (CPU work + that network wait) and gated
# concurrency at 6, so five sixths of a "busy" system was actually idle CPU sitting behind requests
# that were just waiting on Nebius.
#
# So the gate belongs HERE, scoped to only the part that is actually CPU-bound, not around the
# whole request — that lets app/api.py raise its OWN semaphore (how many requests may be in flight
# at once, mostly waiting on the network) much higher without raising how many are actually
# computing on the box at once. Separate from app/api.py's `_generation_semaphore` on purpose: this
# module has callers besides the API (scripts/, eval/), and none of them should be silently gated
# by a limit that exists to protect a live server's shared cores.
#
# No thread-count cap is applied to torch/BLAS here (unlike scripts/nightly_eval.py, which pins its
# own subprocess) — bge-m3 is free to use multiple cores per call, so this stays conservative
# relative to the 8-core box it currently runs on rather than assuming each call is single-threaded.
_MAX_CONCURRENT_RETRIEVALS = int(os.environ.get("CHAVRUTA_MAX_CONCURRENT_RETRIEVALS", "4"))


class _PriorityGate:
    """A capacity-N gate where a `priority=True` acquire jumps ahead of ordinary ones, and is
    first-come-first-served against other priority acquires (never starves one against another).

    Why: a request already mid-conversation — the model replied ===NEED_SOURCES=== and is waiting
    on a follow-up retrieval to CONTINUE an answer it already spent real time and tokens producing
    — must not queue behind a brand-new question's very first retrieval, which has no sunk cost at
    all. By the operator's explicit decision (2026-08-19): finishing what is already in flight
    outranks starting something new when both want the same scarce slot.

    Plain `threading.Semaphore` cannot express this — waiters are released in an unspecified order.
    An earlier version of this class used one `threading.Condition` with `notify_all()` and a
    priority-vs-normal predicate; it correctly let priority jump ahead of normal, but a test
    (test_retrieval_priority_gate.py) caught that ordering AMONG two priority waiters was not
    actually FIFO — `notify_all()` wakes every waiter, and which one re-acquires the lock first is
    an OS scheduling detail, not a guarantee. This version keeps an explicit FIFO queue per tier
    instead and hands a released slot directly to the head of the priority queue (falling back to
    the normal queue), so ordering among equals is an invariant of the data structure, not a hope
    about wakeup order.
    """

    def __init__(self, capacity: int):
        self._capacity = capacity
        self._in_use = 0
        self._lock = threading.Lock()
        self._priority_queue: deque[threading.Event] = deque()
        self._normal_queue: deque[threading.Event] = deque()

    @contextmanager
    def acquire(self, *, priority: bool = False):
        my_turn = threading.Event()
        with self._lock:
            # Only take the fast path when NOTHING is queued — otherwise a slot that frees up would
            # be grabbed by whichever new thread happens to reach this lock first, skipping over
            # waiters who arrived earlier and were promised FIFO-among-equals.
            if self._in_use < self._capacity and not self._priority_queue and not self._normal_queue:
                self._in_use += 1
                granted = True
            else:
                granted = False
                queue = self._priority_queue if priority else self._normal_queue
                queue.append(my_turn)
        if not granted:
            try:
                my_turn.wait()
            except BaseException:
                # Interrupted while still queued (never reached the try/finally below, so our own
                # _release() will never run). If we leave `my_turn` sitting in the queue, a LATER
                # holder's _release() still pops it and .set()s it — nobody is listening any more —
                # and increments `_in_use` for a grant that is now permanently unmatched, quietly
                # shrinking the gate's real capacity by one every time this happens. Remove ourselves
                # instead; if we're no longer in either queue, a concurrent _release() already popped
                # and granted us in the race between the exception and taking this lock — that grant
                # is real capacity and must go through the normal release path (which may hand it
                # straight to the next waiter), not be dropped silently.
                already_granted = False
                with self._lock:
                    if my_turn in self._priority_queue:
                        self._priority_queue.remove(my_turn)
                    elif my_turn in self._normal_queue:
                        self._normal_queue.remove(my_turn)
                    else:
                        already_granted = True
                if already_granted:
                    self._release()
                raise
        try:
            yield
        finally:
            self._release()

    def _release(self) -> None:
        with self._lock:
            self._in_use -= 1
            queue = self._priority_queue or self._normal_queue
            if queue:
                # Hand the slot directly to the next waiter instead of just freeing capacity and
                # letting everyone race for the lock — that race is exactly what broke FIFO before.
                self._in_use += 1
                queue.popleft().set()


_retrieval_gate = _PriorityGate(_MAX_CONCURRENT_RETRIEVALS)


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

    def retrieve(self, query: Query, *, top_k: int, priority: bool = False) -> RetrievalResult:
        """Entry point. The CPU-bound work (embedding + Qdrant round-trips) is bounded by
        `_retrieval_gate`, held only for this call — never for the LLM generation that follows it
        in a real request. See `_MAX_CONCURRENT_RETRIEVALS` above for why.

        `priority` is for a request already mid-conversation asking to CONTINUE (an agentic
        ===NEED_SOURCES=== follow-up — see pipeline.py::_build_source_fetcher) — never for a fresh
        turn's first retrieval, which has no completed work at stake yet."""
        with _retrieval_gate.acquire(priority=priority):
            return self._retrieve_impl(query, top_k=top_k)

    def _retrieve_impl(self, query: Query, *, top_k: int) -> RetrievalResult:
        t_all = time.monotonic()
        t: dict[str, float] = {}
        with _timed(t, "embed"):
            # The reverent spelling is rewritten for the SEARCH text only — the user's own words are
            # never altered anywhere they are shown. Someone who writes "חלק אלוק ממעל" is quoting
            # Iyov 31:2, and until this ran the pasuk did not appear in the top ten of its own
            # quotation; with the one letter restored it comes back second. See
            # corpus/normalize.py::deuphemize_he.
            search_text = deuphemize_he(query.search_text or query.text)
            emb = self.embedding.embed_query(search_text)
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
                        # Lift it, then cap below the named-ref anchor (0.99). Without the lift this
                        # whole block only widened the candidate pool — see _BASE_BOOST.
                        rh.score = min(rh.score + _BASE_BOOST, 0.98)
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
                    found = self.store.search(self.profile.collection, hquery,
                                              top_k=_FOUNDATIONAL_TOP_K,
                                              filters={"work_id": list(_FOUNDATIONAL_WORKS)})
                for h in found:
                    rh = _to_hit(h)
                    # boost, but never reach the anchor sentinel
                    rh.score = min(rh.score + _FOUNDATIONAL_BOOST, 0.99)
                    hits.append(rh)
            except Exception:
                pass

        # Named-tractate floor: the question said which masechet ("במסכת סוכה", "סוכה מא") but not
        # enough to build a ref. Free-text similarity alone routinely misses inside it — a sugya
        # states its point in its own words, not the querier's — so search again scoped to refs
        # carrying that tractate name. This is the difference between answering "what does Rashi say
        # in Sukkah" from Sukkah and answering it from wherever the embedding happened to land.
        for tractate in (query.tractates or [])[:2]:
            try:
                # `ref` only carries a KEYWORD payload index (exact-match, for fetch_by_refs), not a
                # TEXT one — a MatchText filter against it is rejected by Qdrant with a 400 and used
                # to be swallowed here silently, so this floor never actually scoped anything. Over-
                # fetch unfiltered and filter for the tractate name in Python instead; refs are the
                # dotted form ("Sukkah.41a.1", "Rashi_on_Sukkah.41a.1.2") so substring containment is
                # equivalent to the word-level match this was meant to do.
                with _timed(t, "tractate"):
                    scoped = self.store.search(self.profile.collection, hquery,
                                               top_k=_TRACTATE_TOP_K * 8)
                kept = 0
                for h in scoped:
                    if kept >= _TRACTATE_TOP_K:
                        break
                    rh = _to_hit(h)
                    if tractate not in rh.ref:
                        continue
                    # Below the named-ref anchor sentinel: the question named a tractate, not a ref,
                    # so this must not masquerade as something the user pointed at exactly.
                    rh.score = min(rh.score + _TRACTATE_BOOST, 0.98)
                    hits.append(rh)
                    kept += 1
            except Exception as exc:
                logger.warning("tractate-scoped search failed for %s (%s)", tractate, exc)

        # Quotation floor — see _QUOTE_WINDOWS. Skipped when the question already names a ref, a work
        # or a commentator: those are stronger statements of intent than a guessed phrase, and
        # anchoring already serves them.
        if not query.named_refs and not query.work_ids and not query.commentator_ids:
            phrases = quote_windows(search_text, limit=_QUOTE_WINDOWS)
            if phrases:
                try:
                    with _timed(t, "quotes"):
                        embs = self.embedding.embed_batch(phrases)
                        for pe in embs:
                            pq = HybridQuery(dense=pe.dense,
                                             sparse=pe.sparse if use_sparse else None)
                            for h in self.store.search(self.profile.collection, pq,
                                                       top_k=_QUOTE_TOP_K):
                                rh = _to_hit(h)
                                # Level with the tractate floor and capped below the named-ref
                                # anchor: a phrase we GUESSED was a quotation is weaker evidence
                                # than one the user spelled out.
                                rh.score = min(rh.score + _QUOTE_BOOST, 0.98)
                                hits.append(rh)
                except Exception as exc:
                    logger.warning("quotation floor failed (%s)", exc)

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
        # Actually RESERVE the base-text slots, rather than hoping they rank.
        #
        # The floor above finds the base source and appends it at its own score, which is usually
        # low precisely because commentary discusses a topic in the querier's words while the sugya
        # states it in its own. The sort then drops it: for "מה זה יאוש שלא מדעת", Bava_Metzia.42.1
        # sat at 0.211 behind nine commentaries and fell outside top_k — the base text losing to its
        # own commentaries, which is the exact thing this floor exists to prevent. Capping the score
        # (min(score, 0.99)) never helped: it bounds from ABOVE, and the problem is from below.
        #
        # So take the top slots by score, then give back up to _BASE_SLOTS of them to base texts that
        # made the candidate pool. No score is invented — the ordering the caller sees is still by
        # score; only the membership of the final list is adjusted.
        chosen = hits[:top_k]
        if len(hits) > top_k and not query.work_ids and not query.commentator_ids:
            # Fires when base texts are UNDER-REPRESENTED, not only when absent. Gating on "none at
            # all" was useless in practice: with eight slots over this corpus some base text nearly
            # always sneaks in, so the gate never opened while the base text that mattered stayed out.
            have = sum(1 for h in chosen if not is_commentary_ref(h.ref))
            want = max(0, _BASE_SLOTS - have)
            if want:
                spare = [h for h in hits[top_k:] if not is_commentary_ref(h.ref)][:want]
                if spare:
                    # Drop the lowest-scoring COMMENTARY to make room; never evict a base text.
                    keep = [h for h in chosen if not is_commentary_ref(h.ref)]
                    comm = [h for h in chosen if is_commentary_ref(h.ref)]
                    chosen = keep + comm[:max(0, top_k - len(keep) - len(spare))] + spare
                    chosen.sort(key=lambda h: h.score, reverse=True)
        hits = chosen

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
