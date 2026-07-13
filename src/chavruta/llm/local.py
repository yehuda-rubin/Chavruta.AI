"""LocalLLM — offline generation via Ollama (research D1).

Default model: DictaLM-3.0-1.7B-Thinking Q8 (Hebrew-specialized; overridden by CHAVRUTA_LLM_MODEL /
budget. Model id is config-driven (swap to Q3 / a 3B model if RAM is tight). No external
knowledge or tools at generate time (offline, FR-017). `ollama` is imported lazily.
"""

from __future__ import annotations

from collections.abc import Iterator

from chavruta.llm.base import GroundedPrompt, LLMResult, render_messages


class LocalLLM:
    profile = "local"
    source_fetcher = None       # injected by the pipeline for agentic retrieval

    def __init__(self, model_id: str = "hf.co/dicta-il/DictaLM-3.0-1.7B-Thinking-GGUF:Q8_0",
                 base_url: str = "http://localhost:11434"):
        self.model_id = model_id
        self.base_url = base_url
        self._client = None  # lazy

    def request(self, body_md: str, *, lang: str = "he"):
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path. Runs the same agentic
        ===NEED_SOURCES=== loop as the bridge, over local completion calls. Returns (answer, fetched)."""
        from chavruta.llm.agentic import agentic_request

        return agentic_request(self, body_md, lang=lang)

    def _client_(self):
        if self._client is None:
            import ollama  # lazy

            self._client = ollama.Client(host=self.base_url)
        return self._client

    def _chat_kwargs(self, prompt: GroundedPrompt, lang: str, max_tokens: int,
                     temperature: float) -> dict:
        return {
            "model": self.model_id,
            "messages": render_messages(prompt, lang),
            # repeat_penalty guards small models against degenerate repetition loops
            # (observed with the 1.7B); num_predict bounds latency on CPU.
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "repeat_penalty": 1.15,
            },
            # Thinking-variant models (DictaLM-3.0 Thinking) burn the token budget on a
            # separate `thinking` channel and leave `content` empty — disable it; the RAG
            # answer must be direct and grounded, not a reasoning trace.
            "think": False,
        }

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        kwargs = self._chat_kwargs(prompt, lang, max_tokens, temperature)
        try:
            resp = self._client_().chat(**kwargs)
        except Exception:
            # Older Ollama / non-thinking model: retry without the think flag.
            kwargs.pop("think", None)
            resp = self._client_().chat(**kwargs)
        text = resp["message"]["content"] or getattr(resp["message"], "thinking", "") or ""
        return LLMResult(text=text, finish_reason=resp.get("done_reason", "stop"))

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        kwargs = self._chat_kwargs(prompt, lang, max_tokens, temperature)
        kwargs["stream"] = True
        try:
            chunks = self._client_().chat(**kwargs)
        except Exception:
            kwargs.pop("think", None)
            chunks = self._client_().chat(**kwargs)
        for chunk in chunks:
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece
