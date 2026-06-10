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
    def __init__(self, profile: Profile | None = None, *, router=None):
        self.profile = profile or Profile.from_env()
        self.embedding, self.store, self.llm, self.retriever = build_backends(self.profile)
        self.router = router  # set by US1 (intents.router) for richer intent/ref detection

    def _resolve_query(self, request: Query) -> Query:
        if request.lang is None or request.lang == "":
            request.lang = _detect_lang(request.text)
        if self.router is not None:
            return self.router.route(request)
        return request

    def ask(self, request: Query, *, history: list[Turn] | None = None) -> Answer:
        query = self._resolve_query(request)
        result = self.retriever.retrieve(query, top_k=self.profile.top_k)

        if result.is_empty:
            return grounded.no_source_answer(query.lang, query.intent)

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
