"""CloudLLM — scalable generation via an OpenAI-compatible API (research D2).

Points at Nebius Token Factory by default; a stronger serverless model than the local one.
Same prompt + grounding rules as LocalLLM — interchangeable behind LLMBackend (Principle II).
`openai` is imported lazily.
"""

from __future__ import annotations

from collections.abc import Iterator

from chavruta.llm.base import GroundedPrompt, LLMResult, render_messages


class CloudLLM:
    profile = "cloud"
    source_fetcher = None       # injected by the pipeline for agentic retrieval
    fetched_sources: list = []

    def __init__(self, model_id: str, base_url: str, api_key: str):
        self.model_id = model_id
        self.base_url = base_url
        self.api_key = api_key
        self._client = None  # lazy

    def request(self, body_md: str, *, lang: str = "he") -> str:
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path. Runs the same agentic
        ===NEED_SOURCES=== retrieval loop as the bridge, over completion calls."""
        from chavruta.llm.agentic import agentic_request

        return agentic_request(self, body_md, lang=lang)

    def _client_(self):
        if self._client is None:
            from openai import OpenAI  # lazy

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        resp = self._client_().chat.completions.create(
            model=self.model_id,
            messages=render_messages(prompt, lang),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        return LLMResult(text=choice.message.content or "", finish_reason=choice.finish_reason or "stop")

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        stream = self._client_().chat.completions.create(
            model=self.model_id,
            messages=render_messages(prompt, lang),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            piece = chunk.choices[0].delta.content
            if piece:
                yield piece
