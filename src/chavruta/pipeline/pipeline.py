"""ChavrutaPipeline (contracts/pipeline-query.md) — task T019.

The single entry point the UI/CLI call. Builds every backend from the `Profile` (Principle
II — config-only difference between local and cloud) and orchestrates the grounding flow:

    detect → retrieve → (is_empty? honest no-source) → grounded prompt → generate →
    enforce citations → Answer

Grounding is enforced here and in `generation.grounded`, never trusted to the model alone.
"""

from __future__ import annotations

from collections.abc import Iterator

from chavruta.config.profile import Profile
from chavruta.corpus.links import LinkGraph
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

    if profile.llm_backend == "nebius":
        from chavruta.llm.cloud import CloudLLM

        llm = CloudLLM(profile.llm_model, profile.llm_base_url, profile.llm_api_key)
    elif profile.llm_backend == "bridge":
        from chavruta.llm.bridge import BridgeLLM

        llm = BridgeLLM()
    else:
        from chavruta.llm.local import LocalLLM

        llm = LocalLLM(profile.llm_model, profile.llm_base_url)

    reranker = None
    if profile.rerank:
        from chavruta.retrieval.rerank import Reranker

        reranker = Reranker(profile.rerank_model, device=profile.embedding_device)

    link_graph = LinkGraph.load(f"{profile.qdrant_path}/../links.jsonl")
    link_expander = None
    if len(link_graph._adj) > 0:
        from chavruta.retrieval.link_expand import LinkExpander

        link_expander = LinkExpander(store, link_graph, profile)

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
        return self

    def _resolve_query(self, request: Query) -> Query:
        if request.lang is None or request.lang == "":
            request.lang = _detect_lang(request.text)
        if self.router is not None:
            return self.router.route(request)
        return request

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
            if query.intent in (Intent.EXPLAIN, Intent.COMPARE) and query.commentator_ids:
                # Empty because the requested commentator(s) have no comment here.
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
        text, citations, is_grounded = grounded.enforce_citations(llm_out.text, marker_map)
        answer = Answer(
            text=text, citations=citations, grounded=is_grounded,
            no_source=not is_grounded, intent=query.intent,
        )
        if missing_note:
            answer.caveats.append(missing_note)
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
                # primary source. If the main retrieval surfaced only commentaries, fetch the
                # primary source (unit_type=source) for the topic and lead with it.
                if opening and not any(hit_kind(h) in opening.source_kinds for h in hits):
                    src = self._retrieve_opening_source(search, opening.source_kinds)
                    if src is not None:
                        hits = [src, *hits]
                        if not anchor_refs:
                            anchor_refs = [src.anchor_ref or src.ref]

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

    # Map a template's opening source_kinds → the corpus work_ids that hold those sources,
    # so the opening retrieval looks in the RIGHT books (a gemara sugya opens from
    # mishnah/talmud, not from a semantically-near Tanakh verse).
    _KIND_WORK = {"pasuk": "tanakh", "mishnah": "mishnah", "gemara": "talmud_bavli",
                  "midrash": "midrash"}

    def _retrieve_opening_source(self, topic, source_kinds=None):
        """Targeted retrieval of the primary source (the sugya's start) for a lesson opening,
        scoped to the works that match the opening stage's kinds.

        A named sugya's topic IS its opening words ("שניים אוחזין" = Mishnah BM 1.1), so we
        first try a nikud/ktiv-insensitive full-text match (search_he) — which the diluted
        dense/sparse vectors miss — and fall back to vector search when there's no literal hit.
        """
        from chavruta.corpus.normalize import normalize_he

        works = [self._KIND_WORK[k] for k in (source_kinds or []) if k in self._KIND_WORK]
        norm = normalize_he(topic)

        # Try each preferred work IN ORDER (a talmudic sugya opens from its MISHNA, not from
        # a gemara segment that merely quotes it), lexical-first: a literal nikud/ktiv match on
        # the opening words beats the diluted vectors. Fall back to vector over all works.
        for w in works:
            if norm:
                hit = self._search_source(topic, {"unit_type": "source", "work_id": [w],
                                                  "search_he": {"$text": norm}})
                if hit is not None:
                    return hit
        base = {"unit_type": "source"}
        if works:
            base["work_id"] = works
        return self._search_source(topic, base)

    def _search_source(self, topic, filters):
        """Hybrid search for one source under `filters`; best hit or None."""
        try:
            from chavruta.retrieval.hybrid import _to_hit
            from chavruta.store.base import HybridQuery

            emb = self.embedding.embed_query(topic)
            sparse = emb.sparse if (self.profile.hybrid and emb.sparse) else None
            raw = self.store.search(
                self.profile.collection, HybridQuery(dense=emb.dense, sparse=sparse),
                top_k=4, filters=filters,
            )
            return _to_hit(raw[0]) if raw else None
        except Exception:
            return None

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
