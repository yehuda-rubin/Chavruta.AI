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


def build_backends(profile: Profile):
    """Construct embedding, store, llm, optional reranker, link graph, and retriever."""
    from chavruta.embedding.bge_m3 import BgeM3Embedding
    from chavruta.store.qdrant_store import QdrantStore

    embedding = BgeM3Embedding(model_id=profile.embedding_model, device=profile.embedding_device)
    store = QdrantStore(mode=profile.qdrant_mode, path=profile.qdrant_path, url=profile.qdrant_url)

    if profile.llm_backend == "nebius":
        from chavruta.llm.cloud import CloudLLM

        llm = CloudLLM(profile.llm_model, profile.llm_base_url, profile.llm_api_key)
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

            router = Router()
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

        result = self.retriever.retrieve(query, top_k=self.profile.top_k)

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

        prompt, marker_map = grounded.build_prompt(
            query.text, result.hits, intent=query.intent, history=history
        )
        llm_out = self.llm.generate(
            prompt, lang=query.lang,
            max_tokens=self.profile.llm_max_tokens, temperature=self.profile.llm_temperature,
        )
        text, citations, is_grounded = grounded.enforce_citations(llm_out.text, marker_map)
        answer = Answer(
            text=text, citations=citations, grounded=is_grounded,
            no_source=not is_grounded, intent=query.intent,
        )
        if missing_note:
            answer.caveats.append(missing_note)
        if query.intent is Intent.LESSON:
            # Structured scaffold alongside the narrative: sources grouped per anchor,
            # ordered along the chain of transmission, every section cited (FR-008/008a).
            answer.lesson_plan = grounded.build_lesson_plan(query.text, result.hits)
        return grounded.maybe_halacha_caveat(answer, query.lang)

    def ask_stream(self, request: Query, *, history: list[Turn] | None = None) -> Iterator[str]:
        query = self._resolve_query(request)
        result = self.retriever.retrieve(query, top_k=self.profile.top_k)
        if result.is_empty:
            yield grounded.no_source_answer(query.lang, query.intent).text
            return
        prompt, _ = grounded.build_prompt(
            query.text, result.hits, intent=query.intent, history=history
        )
        yield from self.llm.stream(
            prompt, lang=query.lang,
            max_tokens=self.profile.llm_max_tokens, temperature=self.profile.llm_temperature,
        )
