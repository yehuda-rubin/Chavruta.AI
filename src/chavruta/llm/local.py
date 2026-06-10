"""LocalLLM — offline generation via Ollama (research D1).

Default model: DictaLM-2.0-Instruct Q4 (~4.4GB), Hebrew-specialized, fits the laptop RAM
budget. Model id is config-driven (swap to Q3 / a 3B model if RAM is tight). No external
knowledge or tools at generate time (offline, FR-017). `ollama` is imported lazily.
"""

from __future__ import annotations

from collections.abc import Iterator

from chavruta.llm.base import GroundedPrompt, LLMResult, render_messages


class LocalLLM:
    profile = "local"

    def __init__(self, model_id: str = "dictalm2.0-instruct:q4_k_m",
                 base_url: str = "http://localhost:11434"):
        self.model_id = model_id
        self.base_url = base_url
        self._client = None  # lazy

    def _client_(self):
        if self._client is None:
            import ollama  # lazy

            self._client = ollama.Client(host=self.base_url)
        return self._client

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        resp = self._client_().chat(
            model=self.model_id,
            messages=render_messages(prompt, lang),
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return LLMResult(text=resp["message"]["content"], finish_reason=resp.get("done_reason", "stop"))

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        for chunk in self._client_().chat(
            model=self.model_id,
            messages=render_messages(prompt, lang),
            options={"temperature": temperature, "num_predict": max_tokens},
            stream=True,
        ):
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece
