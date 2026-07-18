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
import os
import threading
import time
from collections.abc import Iterator

from chavruta.llm.base import GroundedPrompt, LLMResult, render_messages

_log = logging.getLogger("chavruta.llm.cloud")


class _CircuitBreaker:
    """Fail fast when the LLM API is down. Without it, every request waits out the full timeout and
    pins a worker thread — so a provider outage backs the whole API up (the audit's C4). After N
    consecutive transient failures the circuit OPENS: calls raise immediately for a cooldown, then
    one trial (half-open) decides whether to close again. Config errors don't trip it — they're a
    misconfiguration, not an outage, and are handled separately.
    """

    def __init__(self, fails: int, cooldown_s: float):
        self.fails = fails
        self.cooldown = cooldown_s
        self._consecutive = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def before(self, now: float) -> None:
        with self._lock:
            if self._open_until and now < self._open_until:
                raise LLMTransientError(
                    f"LLM circuit open — provider failing; retry in {self._open_until - now:.0f}s")

    def on_success(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._open_until = 0.0

    def on_failure(self, now: float) -> None:
        with self._lock:
            self._consecutive += 1
            if self._consecutive >= self.fails:
                self._open_until = now + self.cooldown
                _log.error("LLM circuit OPEN after %d consecutive failures — pausing calls for %.0fs",
                           self._consecutive, self.cooldown)


_BREAKER = _CircuitBreaker(
    fails=int(os.environ.get("CHAVRUTA_LLM_BREAKER_FAILS", "5")),
    cooldown_s=float(os.environ.get("CHAVRUTA_LLM_BREAKER_COOLDOWN_S", "30")),
)


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

    def request(self, body_md: str, *, lang: str = "he", token_budget: int | None = None):
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path. Runs the same agentic
        ===NEED_SOURCES=== loop as the bridge, over completion calls. Returns (answer, fetched)."""
        from chavruta.llm.agentic import agentic_request

        return agentic_request(self, body_md, lang=lang, token_budget=token_budget)

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
        """One bounded, reported completion call. Returns (choice, usage).

        Raises LLMConfigError / LLMTransientError.
        """
        t0 = time.monotonic()
        _BREAKER.before(t0)     # fail fast if the provider is currently flagged down
        try:
            resp = self._client_().chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            mapped = _classify(exc)
            # Only transient failures (timeout/429/5xx/connection) count toward the breaker — a
            # config error is a misconfiguration, not an outage.
            if isinstance(mapped, LLMTransientError):
                _BREAKER.on_failure(time.monotonic())
            _log.error(
                "llm call FAILED what=%s model=%s elapsed=%.1fs kind=%s: %s",
                what, self.model_id, time.monotonic() - t0,
                type(mapped).__name__, exc, exc_info=True,
            )
            raise mapped from exc

        _BREAKER.on_success()
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
        return choice, usage

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        choice, usage = self._complete(
            render_messages(prompt, lang),
            max_tokens=max_tokens, temperature=temperature, what="generate",
        )
        return LLMResult(
            text=choice.message.content or "",
            finish_reason=choice.finish_reason or "stop",
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

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
