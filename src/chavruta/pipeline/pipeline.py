"""ChavrutaPipeline (contracts/pipeline-query.md) — task T019.

The single entry point the UI/CLI call. Builds every backend from the `Profile` (Principle
II — config-only difference between local and cloud) and orchestrates the grounding flow:

    detect → retrieve → (is_empty? honest no-source) → grounded prompt → generate →
    enforce citations → Answer

Grounding is enforced here and in `generation.grounded`, never trusted to the model alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from chavruta.config.profile import Profile
from chavruta.corpus.links import LinkGraph
from chavruta.corpus.refs import canon_corpus_ref, with_ref_variants
from chavruta.corpus.registry import CorpusRegistry, default_registry
from chavruta.corpus.schema import Answer, Intent, Query, Turn
from chavruta.generation import grounded
from chavruta.retrieval.hybrid import HybridRetriever


def _detect_lang(text: str) -> str:
    """Hebrew if it contains Hebrew letters, else English (FR-010)."""
    return "he" if any("֐" <= ch <= "׿" for ch in text) else "en"


# Per-intent generation budgets (user decision 2026-06-18): lessons need room for a full
# scaffold, comparisons are medium, regular Q&A / explanations stay tight. Falls back to
# the profile's llm_max_tokens for any other intent.
_INTENT_MAX_TOKENS = {
    Intent.QA: 3000,
    Intent.EXPLAIN: 3000,
    Intent.LESSON: 30000,
    Intent.COMPARE: 10000,
    Intent.HALACHA: 12000,     # a teshuva: source → poskim → pesak, can be substantial
}


def _max_tokens_for(intent, profile: Profile) -> int:
    return _INTENT_MAX_TOKENS.get(intent, profile.llm_max_tokens)


# Per-intent retrieval breadth (user decision 2026-06-20): the number of chunks sent to the
# model is DYNAMIC, not fixed. The corpus is stored at fine segment granularity (precise but
# small per chunk), so a lesson spanning a whole sugya needs many more chunks than a short
# Q&A. Falls back to the profile's top_k for any other intent.
_INTENT_TOP_K = {
    Intent.QA: 8,
    Intent.EXPLAIN: 16,
    Intent.COMPARE: 24,
    Intent.LESSON: 48,
    Intent.HALACHA: 32,        # responsa pulls a wide net of sources + poskim
}


def _top_k_for(intent, profile: Profile) -> int:
    return _INTENT_TOP_K.get(intent, profile.top_k)


def _dedup_hits(hits):
    """De-duplicate hits by chunk, keeping the highest-scoring occurrence (anchored/source
    material outranks the same chunk arriving as a low-scored link-expanded duplicate)."""
    best: dict = {}
    for h in hits:
        cur = best.get(h.chunk_id)
        if cur is None or h.score > cur.score:
            best[h.chunk_id] = h
    return list(best.values())


def build_backends(profile: Profile):
    """Construct embedding, store, llm, optional reranker, link graph, and retriever."""
    from chavruta.embedding.bge_m3 import BgeM3Embedding
    from chavruta.store.qdrant_store import QdrantStore

    embedding = BgeM3Embedding(model_id=profile.embedding_model, device=profile.embedding_device,
                               use_sparse=profile.hybrid)
    store = QdrantStore(mode=profile.qdrant_mode, path=profile.qdrant_path,
                        url=profile.qdrant_url, api_key=profile.qdrant_api_key)

    # Two backends only: 'nebius' (the API — DEFAULT) and 'bridge' (Claude answers in-session, no
    # external API). The local DictaLM/Ollama backend was removed by product decision.
    if profile.llm_backend == "nebius":
        from chavruta.llm.cloud import CloudLLM

        llm = CloudLLM(profile.llm_model, profile.llm_base_url, profile.llm_api_key)
    elif profile.llm_backend == "bridge":
        from chavruta.llm.bridge import BridgeLLM

        llm = BridgeLLM()
    else:
        raise ValueError(
            f"unknown CHAVRUTA_LLM_BACKEND={profile.llm_backend!r}. Supported: 'nebius' (the API — "
            f"default) or 'bridge' (Claude in-session, no external API). The local DictaLM/Ollama "
            f"backend has been removed."
        )

    reranker = None
    if profile.rerank:
        from chavruta.retrieval.rerank import Reranker

        reranker = Reranker(profile.rerank_model, device=profile.embedding_device)

    # Prefer the corpus-derived, corpus-aligned graph on disk (LinkStore + ref index — O(1) RAM);
    # fall back to the legacy in-memory links.jsonl if it isn't built yet.
    from pathlib import Path as _Path
    _data = _Path(profile.qdrant_path).parent
    _graph_db, _ref_db = _data / "links_corpus.db", _data / "ref_index.db"
    ref_resolver = None
    if _graph_db.exists() and _ref_db.exists():
        from chavruta.corpus.links import LinkStore
        from chavruta.corpus.ref_index import RefIndex

        link_graph = LinkStore(_graph_db)
        ref_resolver = RefIndex(_ref_db)
    else:
        link_graph = LinkGraph.load(f"{profile.qdrant_path}/../links.jsonl")
    link_expander = None
    if len(link_graph) > 0:
        from chavruta.retrieval.link_expand import LinkExpander

        link_expander = LinkExpander(store, link_graph, profile, ref_resolver=ref_resolver)

    retriever = HybridRetriever(
        embedding, store, profile, reranker=reranker, link_expander=link_expander
    )
    return embedding, store, llm, retriever


class ChavrutaPipeline:
    def __init__(self, profile: Profile | None = None, *, router=None,
                 registry: CorpusRegistry | None = None):
        self.profile = profile or Profile.from_env()
        self.embedding, self.store, self.llm, self.retriever = build_backends(self.profile)
        self.registry = registry or default_registry()
        if router is None:
            from chavruta.intents.router import Router

            planner = None
            if self.profile.query_planner == "llm":
                from chavruta.intents.llm_planner import LLMQueryPlanner

                planner = LLMQueryPlanner(
                    self.profile.llm_model, self.profile.llm_base_url, self.profile.llm_api_key
                )
            router = Router(planner=planner)
        self.router = router
        self._wire_bridge_source_fetcher()

    @classmethod
    def from_backends(cls, profile: Profile, *, embedding, store, llm, retriever,
                      router=None, registry: CorpusRegistry | None = None):
        """Construct with injected backends (tests, embedding-free environments)."""
        self = cls.__new__(cls)
        self.profile = profile
        self.embedding, self.store, self.llm, self.retriever = embedding, store, llm, retriever
        self.registry = registry or default_registry()
        if router is None:
            from chavruta.intents.router import Router

            router = Router()
        self.router = router
        self._wire_bridge_source_fetcher()
        return self

    def _wire_bridge_source_fetcher(self) -> None:
        """Give the bridge LLM a way to pull more sources on its own: when the model replies with a
        ===NEED_SOURCES=== block, these follow-up queries are retrieved and appended to the job. Only
        applies to a backend that exposes `source_fetcher` (BridgeLLM); a no-op otherwise."""
        llm = getattr(self, "llm", None)
        if llm is None or not hasattr(llm, "source_fetcher"):
            return
        from chavruta.llm.base import SourceBlock

        def fetch(queries: list[str]) -> list[SourceBlock]:
            out: list[SourceBlock] = []
            seen: set[str] = set()
            for q in (queries or [])[:5]:
                if not (q or "").strip():
                    continue
                try:
                    rq = self._resolve_query(Query(text=q, intent=Intent.QA))
                    hits = self.retriever.retrieve(rq, top_k=8).hits
                except Exception:
                    continue
                for h in hits:
                    ref = getattr(h, "ref", "") or ""
                    if ref and ref not in seen:
                        seen.add(ref)
                        out.append(SourceBlock(marker="", ref=ref,
                                               commentator_id=getattr(h, "commentator_id", None),
                                               text=getattr(h, "text", "") or ""))
                if len(out) >= 24:
                    break
            return out[:24]

        llm.source_fetcher = fetch

    def _resolve_query(self, request: Query) -> Query:
        if request.lang is None or request.lang == "":
            request.lang = _detect_lang(request.text)
        if self.router is not None:
            return self.router.route(request)
        return request

    def _agentic_selffetch(self, query: Query, history) -> Answer | None:
        """When retrieval returned NOTHING, give the model one chance to pull its own sources via the
        agentic ===NEED_SOURCES=== loop (the same mechanism the lesson/chavruta paths use). Returns a
        grounded Answer if it fetched sources and cited them; None otherwise (the caller then falls
        back to the honest no-source answer, so Principle I is never violated)."""
        llm = self.llm
        if not getattr(llm, "source_fetcher", None) or not hasattr(llm, "request"):
            return None                                   # backend has no self-fetch capability
        from chavruta.llm.agentic import SOURCE_REQUEST_INSTRUCTION, is_degrade_message

        lang = query.lang or "he"
        job = "\n".join([
            f"lang: {lang}", "", "## QUESTION", query.text.strip(), "",
            "## SOURCES", "(nothing was retrieved for this question — fetch what you need)", "",
            "## INSTRUCTIONS",
            "Answer ONLY from SOURCES you fetch; cite every claim by its [S#] marker; match the "
            "question's language. If after fetching you STILL have nothing relevant, say so plainly "
            "and do not invent.",
            SOURCE_REQUEST_INSTRUCTION,
        ])
        try:
            raw, fetched = llm.request(job, lang=lang)
        except Exception:
            return None
        if not fetched or is_degrade_message(raw):
            return None                                   # nothing fetched, or a timeout/no-fetch degrade
        marker_map = {f"S{i}": s for i, s in enumerate(fetched, 1)}
        text, citations, is_grounded = grounded.enforce_citations(raw, marker_map)
        if not is_grounded:
            return None                                   # model didn't actually cite a fetched source
        return Answer(text=text, citations=citations, grounded=True, no_source=False,
                      intent=query.intent)

    def ask(self, request: Query, *, history: list[Turn] | None = None) -> Answer:
        query = self._resolve_query(request)

        # Out-of-corpus work honesty (spec edge case): the question explicitly asks about
        # a body of work that is not loaded → say so; never substitute similar-sounding
        # material from another work as if it were the requested source (Principle I).
        if query.requested_works:
            missing_works = [w for w in query.requested_works if not self.registry.has(w)]
            loaded_requested = [w for w in query.requested_works if self.registry.has(w)]
            if missing_works and not loaded_requested:
                return grounded.work_not_loaded_answer(query.lang, missing_works, query.intent)

        result = self.retriever.retrieve(query, top_k=_top_k_for(query.intent, self.profile))

        if result.is_empty:
            # Retrieval found nothing — for ANY intent (Q&A, explain, compare, halacha) give the model
            # ONE chance to pull its own sources via the agentic ===NEED_SOURCES=== loop before we
            # honestly give up (Principle I is preserved: a self-fetch that still comes back empty
            # falls through to the honest answer below).
            selffetched = self._agentic_selffetch(query, history)
            if selffetched is not None:
                return selffetched
            if query.intent in (Intent.EXPLAIN, Intent.COMPARE) and query.commentator_ids:
                # …and the self-fetch still found nothing: the requested commentator has no comment here.
                return grounded.no_commentator_answer(
                    query.lang, list(query.commentator_ids), query.intent
                )
            return grounded.no_source_answer(query.lang, query.intent)

        # Explain/compare honesty (FR-006/007): a requested commentator with no retrieved
        # comment must be reported as absent, never invented (Principle I).
        missing_note = None
        if query.intent in (Intent.EXPLAIN, Intent.COMPARE) and query.commentator_ids:
            present = {h.commentator_id for h in result.hits if h.commentator_id}
            missing = [c for c in query.commentator_ids if c not in present]
            if missing and len(missing) == len(query.commentator_ids):
                return grounded.no_commentator_answer(query.lang, missing, query.intent)
            if missing:
                missing_note = grounded.missing_commentator_note(query.lang, missing)

        # A lesson — and a responsa (שו"ת) — is delivered as a full walkthrough (the "מהלך")
        # that follows its arc and keeps only the sources it actually uses. Both run the same
        # machine; HALACHA just selects the separate responsa template set (shared corpus).
        if query.intent in (Intent.LESSON, Intent.HALACHA):
            return self._lesson_answer(query, result)

        prompt, marker_map = grounded.build_prompt(
            query.text, result.hits, intent=query.intent, history=history, lang=query.lang
        )
        llm_out = self.llm.generate(
            prompt, lang=query.lang,
            max_tokens=_max_tokens_for(query.intent, self.profile),
            temperature=self.profile.llm_temperature,
        )
        # Agentic retrieval may have appended sources during generation; extend the marker map
        # (continuing the S# numbering) so their [S#] citations resolve instead of being dropped as
        # fabricated. Read them off the per-call result (no shared state). No-op if none were fetched.
        for i, s in enumerate(getattr(llm_out, "fetched_sources", None) or [], len(marker_map) + 1):
            marker_map.setdefault(f"S{i}", s)
        text, citations, is_grounded = grounded.enforce_citations(llm_out.text, marker_map)
        answer = Answer(
            text=text, citations=citations, grounded=is_grounded,
            no_source=not is_grounded, intent=query.intent,
        )
        if missing_note:
            answer.caveats.append(missing_note)
        # An answer that produced no valid [S#] markers isn't citation-enforced — flag it explicitly
        # rather than presenting it as a normal grounded answer (Principle I: every claim cited).
        if not is_grounded and text.strip():
            answer.caveats.append("הערה: תשובה זו אינה מעוגנת במקור מצוטט — יש לאמתה."
                                  if query.lang != "en" else
                                  "Note: this answer is not tied to a cited source — verify it.")
        # Citation-faithfulness: any verbatim quote not found in the retrieved sources is flagged.
        bad_q = grounded.unverified_quotes(text, result.hits)
        if bad_q:
            answer.caveats.append(("הערה: ציטוט/ים שלא נמצאו במקורות שנשלפו: «" + "», «".join(bad_q[:2]) + "» — יש לאמת.")
                                  if query.lang != "en" else
                                  ("Note: quote(s) not found in the retrieved sources: «" + "», «".join(bad_q[:2]) + "» — verify."))
        return grounded.maybe_halacha_caveat(answer, query.lang)

    def _lesson_answer(self, query, result):
        """Generate the lesson — or responsa (שו"ת) — as a flowing walkthrough that follows
        the arc (opening → branches → convergence), then keep in each section only the sources
        the walkthrough actually cited. HALACHA uses the responsa template set + voice."""
        is_shut = query.intent is Intent.HALACHA
        plan = self._build_lesson(query, result)
        if plan.sections:
            prompt, marker_map = grounded.build_lesson_walkthrough_prompt(
                plan, query.text, lang=query.lang, shut=is_shut)
        else:
            prompt, marker_map = grounded.build_prompt(
                query.text, result.hits, intent=query.intent, lang=query.lang)
        llm_out = self.llm.generate(
            prompt, lang=query.lang,
            max_tokens=_max_tokens_for(query.intent, self.profile),
            temperature=self.profile.llm_temperature,
        )
        # Agentic retrieval may have appended sources during generation (bridge runs the loop inside
        # generate) — extend the marker map so a responsa/lesson that fetched its own sources keeps
        # those [S#] citations (and prune_lesson_to_cited doesn't then delete the sections citing them).
        for i, s in enumerate(getattr(llm_out, "fetched_sources", None) or [], len(marker_map) + 1):
            marker_map.setdefault(f"S{i}", s)
        text, citations, is_grounded = grounded.enforce_citations(llm_out.text, marker_map)
        if plan.sections:
            plan = grounded.prune_lesson_to_cited(plan, citations)
        answer = Answer(text=text, citations=citations, grounded=is_grounded,
                        no_source=not is_grounded, intent=query.intent)
        answer.lesson_plan = plan
        return grounded.maybe_halacha_caveat(answer, query.lang)

    def _template_index(self, intent=None):
        """Lazily load the template index for the intent — the responsa (שו"ת) set for HALACHA,
        the lesson set otherwise. Both are built once from this pipeline's embedding."""
        from chavruta.lessons.templates import SHUT_PATH, TemplateIndex, load_templates

        key = "_tmpl_shut" if intent is Intent.HALACHA else "_tmpl_lesson"
        if not hasattr(self, key):
            try:
                templates = load_templates(SHUT_PATH if intent is Intent.HALACHA else None)
                setattr(self, key, TemplateIndex(templates, self.embedding) if templates else None)
            except Exception:
                setattr(self, key, None)
        return getattr(self, key)

    def _build_lesson(self, query, result):
        topic = query.text
        search = query.search_text or topic
        hits = list(result.hits)
        anchor_refs = result.anchor_refs
        idx = self._template_index(query.intent)
        if idx is not None:
            template = idx.select(search)
            if template is not None:
                from chavruta.lessons.builder import build_lesson_from_template, hit_kind

                opening = template.opening
                # Stage-aware opening (spec 003 Phase 4): a lesson must START at the sugya's
                # primary source. If the main retrieval surfaced only commentaries, prepend the
                # base source(s) for the resolved refs (canonicalised to the corpus ref format).
                if opening and not any(hit_kind(h) in opening.source_kinds for h in hits):
                    have = {h.ref for h in hits}
                    base = [b for b in self.base_sources_for_refs(list(query.named_refs or []) +
                                                                  list(anchor_refs or [])) if b.ref not in have]
                    if base:
                        hits = [*base, *hits]
                        if not anchor_refs:
                            anchor_refs = [base[0].anchor_ref or base[0].ref]

                # Pull the connected meforshim (and their supercommentaries) of EVERY primary
                # source we have, via the links graph up to query.expand_depth (2 for lessons)
                # — focused, on-topic material rather than broad similarity. Each source IS
                # linked to its commentaries.
                source_anchors: list[str] = []
                for h in hits:
                    if h.commentator_id is None:                # a primary source (not a commentary)
                        ref = h.anchor_ref or h.ref
                        if ref and ref not in source_anchors:
                            source_anchors.append(ref)
                if source_anchors:
                    hits = hits + self._expand_from(source_anchors, query)

                return build_lesson_from_template(topic, template, _dedup_hits(hits), anchor_refs)
        return grounded.build_lesson_plan(topic, hits)

    def _expand_from(self, refs, query):
        """Commentaries/supercommentaries connected to `refs` in the links graph (depth from
        query.expand_depth). Returns [] if expansion is off or unavailable."""
        le = getattr(self.retriever, "link_expander", None)
        if le is None or not query.expand_links:
            return []
        try:
            return le.expand([r for r in refs if r], query)
        except Exception:
            return []

    # kept as a thin delegate so callers/tests have one name; the canonical implementation lives in
    # corpus.refs (shared with the retriever's anchoring path).
    _canon_corpus_ref = staticmethod(canon_corpus_ref)

    def base_sources_for_refs(self, refs):
        """The primary-source chunks (unit_type=source) for explicit refs — so a lesson leads from
        its base pasuk/daf/mishnah, not only its commentaries. Uses the indexed `ref` field (fast,
        no scan) and the SAME `with_ref_variants` normaliser as the retriever's anchoring path (dot↔
        space, chapter→opening-verse, Talmud amud→corpus) so the two never disagree on which refs
        resolve. Returns RankedHits (score 1.0 — a resolved base source is certain)."""
        from chavruta.retrieval.hybrid import _to_hit

        out, seen = [], set()
        for r in (refs or []):
            if not r:
                continue
            for c in with_ref_variants([r]):             # first variant that resolves wins
                try:
                    raw = self.store.fetch_by_refs(self.profile.collection, [c],
                                                   filters={"unit_type": "source"})
                except Exception:
                    raw = []
                if raw:
                    for h in raw:
                        hit = _to_hit(h)
                        if hit.ref and hit.ref not in seen:
                            seen.add(hit.ref)
                            hit.score = 1.0
                            out.append(hit)
                    break
        return out

    def ask_stream(self, request: Query, *, history: list[Turn] | None = None) -> Iterator[str]:
        query = self._resolve_query(request)
        result = self.retriever.retrieve(query, top_k=_top_k_for(query.intent, self.profile))
        if result.is_empty:
            yield grounded.no_source_answer(query.lang, query.intent).text
            return
        prompt, _ = grounded.build_prompt(
            query.text, result.hits, intent=query.intent, history=history, lang=query.lang
        )
        yield from self.llm.stream(
            prompt, lang=query.lang,
            max_tokens=_max_tokens_for(query.intent, self.profile),
            temperature=self.profile.llm_temperature,
        )
