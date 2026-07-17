"""CloudLLM — scalable generation via an OpenAI-compatible API (research D2).

Points at the Token Factory by default; a stronger serverless model than a local one.
Same prompt + grounding rules across backends — interchangeable behind LLMBackend (Principle II).
`openai` is imported lazily.

Every call is bounded and reported: an explicit per-call timeout/retry budget (the SDK's own
defaults are 600s x 2 retries, which the agentic loop multiplies into hours), and one log line per
call carrying latency + the token counts the API already hands us. Token usage is the only
ground truth for what a request costs — it used to be read off the response and thrown away.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from chavruta.llm.base import GroundedPrompt, LLMResult, render_messages

_log = logging.getLogger("chavruta.llm.cloud")


class LLMConfigError(RuntimeError):
    """The call can never succeed as configured — bad key, bad model, no credit. Retrying is futile.

    Separated from transient failures so callers can stop presenting "try again" for a wrong API
    key, and so operators see the difference in the logs.
    """


class LLMTransientError(RuntimeError):
    """The call failed but could plausibly succeed later — rate limit, timeout, 5xx, connection."""


def _classify(exc: Exception) -> Exception:
    """Map an SDK exception onto our two-way split.

    Deliberately matches on class name rather than importing openai's exception tree: `openai` is a
    lazy import here, and the tree has been reorganised across major versions. A name check keeps
    this working across upgrades instead of silently falling through to "transient".
    """
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)

    if name in {"AuthenticationError", "PermissionDeniedError", "NotFoundError"} or status in {401, 403, 404}:
        return LLMConfigError(f"{name}: {exc}")
    # 400 is usually a malformed request (bad model id, context overflow) — retrying won't fix it.
    if name in {"BadRequestError", "UnprocessableEntityError"} or status in {400, 422}:
        return LLMConfigError(f"{name}: {exc}")
    return LLMTransientError(f"{name}: {exc}")


class CloudLLM:
    profile = "cloud"
    source_fetcher = None       # injected by the pipeline for agentic retrieval

    def __init__(self, model_id: str, base_url: str, api_key: str,
                 timeout_s: float = 180.0, max_retries: int = 1):
        self.model_id = model_id
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._client = None  # lazy

    def request(self, body_md: str, *, lang: str = "he"):
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path. Runs the same agentic
        ===NEED_SOURCES=== loop as the bridge, over completion calls. Returns (answer, fetched)."""
        from chavruta.llm.agentic import agentic_request

        return agentic_request(self, body_md, lang=lang)

    def _client_(self):
        if self._client is None:
            from openai import OpenAI  # lazy

            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout_s,
                max_retries=self.max_retries,
            )
        return self._client

    def _complete(self, messages, *, max_tokens: int, temperature: float, what: str):
        """One bounded, reported completion call. Raises LLMConfigError / LLMTransientError."""
        t0 = time.monotonic()
        try:
            resp = self._client_().chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            mapped = _classify(exc)
            _log.error(
                "llm call FAILED what=%s model=%s elapsed=%.1fs kind=%s: %s",
                what, self.model_id, time.monotonic() - t0,
                type(mapped).__name__, exc, exc_info=True,
            )
            raise mapped from exc

        elapsed = time.monotonic() - t0
        usage = getattr(resp, "usage", None)
        choice = resp.choices[0]
        _log.info(
            "llm call ok what=%s model=%s elapsed=%.1fs prompt_tokens=%s completion_tokens=%s "
            "total_tokens=%s finish=%s",
            what, self.model_id, elapsed,
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
            choice.finish_reason,
        )
        return choice

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        choice = self._complete(
            render_messages(prompt, lang),
            max_tokens=max_tokens, temperature=temperature, what="generate",
        )
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
