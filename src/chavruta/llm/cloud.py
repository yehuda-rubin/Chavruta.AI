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

from chavruta.llm import metering
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


class LLMEmptyAnswerError(RuntimeError):
    """The call SUCCEEDED and returned no answer.

    Its own class because it is neither of the two above and behaves like neither. A reasoning model
    can spend an entire output budget on `reasoning_content` and return `content` = "" with
    finish_reason "length" — an HTTP 200 carrying nothing. Measured on Macaron V1 Venti (Novita)
    on 2026-07-27: ~86,000 characters of reasoning and an empty answer at a 24,000-token budget; the
    same prompt completed normally at 96,000.

    Before this existed, `content or ""` handed that empty string on as if it were an answer, and the
    grounding gate downstream reported "no sources" — a wrong diagnosis of a budget problem, which is
    the kind of bug that costs a day. Raising here names it, and the message says what to change.
    """


def _answer_text(choice) -> str:
    """The answer from a completion choice, or raise if the model produced none.

    `reasoning_content` (Novita/DeepSeek/GLM-family) and `thinking` are the model's scratchpad, NOT
    the answer: they are excluded deliberately, because putting a chain of thought in front of a user
    who asked about a sugya would be both wrong and, on some of these models, in Chinese.
    """
    msg = getattr(choice, "message", None)
    text = (getattr(msg, "content", None) or "").strip()
    if text:
        return text

    reasoning = ""
    for attr in ("reasoning_content", "reasoning", "thinking"):
        raw = getattr(msg, attr, None)
        if isinstance(raw, str) and raw.strip():
            reasoning = raw.strip()
            break
    finish = getattr(choice, "finish_reason", "") or "?"
    if reasoning:
        raise LLMEmptyAnswerError(
            f"the model returned only reasoning and no answer ({len(reasoning)} chars of "
            f"reasoning, finish_reason={finish}). Its thinking used the whole output budget — "
            f"raise CHAVRUTA_LLM_MIN_OUTPUT_TOKENS (or the per-intent budget) for this model."
        )
    raise LLMEmptyAnswerError(f"the model returned an empty answer (finish_reason={finish})")


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


def list_models(base_url: str, api_key: str, *, timeout_s: float = 15.0) -> list[str]:
    """The model ids an OpenAI-compatible provider actually serves at `base_url` for this key — used
    to validate a BYOK caller's requested model name (app/api.py::/byok/check) before ever wiring it
    into a real generation call, and to offer a pick-list when the requested one isn't there. Pricing
    is deliberately NOT attempted here: the OpenAI `models.list()` shape carries no cost field, and
    providers differ too much for a generic guess to be honest — the caller states that plainly
    rather than inventing a number."""
    from openai import OpenAI  # lazy — see CloudLLM._client_

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)
    return sorted(m.id for m in client.models.list().data)


def _cached_prompt_tokens(usage) -> int:
    """How many prompt tokens the provider served from its own cache, or 0 if it doesn't say.

    Answers a question that can't be settled from documentation: whether this provider does prompt
    caching at all, and if so how much of our prompt actually hits. Our message order is already the
    cache-friendly one — a stable system prompt, then history, then the retrieved sources and the
    question last — and the agentic loop re-sends a strictly growing prefix on every extra round,
    which is exactly the shape caching pays off on. The field is OpenAI's
    `usage.prompt_tokens_details.cached_tokens`; a provider that doesn't implement it simply omits
    it, so a steady 0 in the logs is itself the answer. Reading it costs nothing — it rides along on
    responses we already make.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    got = getattr(details, "cached_tokens", None)
    if got is None and isinstance(details, dict):
        got = details.get("cached_tokens")
    try:
        return max(0, int(got or 0))
    except (TypeError, ValueError):
        return 0


class CloudLLM:
    profile = "cloud"
    source_fetcher = None       # injected by the pipeline for agentic retrieval

    def __init__(self, model_id: str, base_url: str, api_key: str,
                 timeout_s: float = 180.0, max_retries: int = 1,
                 min_output_tokens: int = 0):
        self.model_id = model_id
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        # A floor under every output budget, for models that think before they answer. The per-intent
        # budgets (QA 3,000; LESSON 30,000) were sized for a model that answers directly; a reasoning
        # model can burn 3,000 tokens before it writes a word, so on those the floor is what stands
        # between a working deployment and every short answer coming back empty. 0 = no floor, which
        # is right for a non-reasoning model and is the default.
        self.min_output_tokens = max(0, int(min_output_tokens or 0))
        self._client = None  # lazy

    def request(self, body_md: str, *, lang: str = "he", token_budget: int | None = None):
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path. Runs the same agentic
        ===NEED_SOURCES=== loop as the bridge, over completion calls. Returns (answer, fetched).

        Token spend needs no plumbing here: every round goes through _complete, which meters."""
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
        max_tokens = max(int(max_tokens), self.min_output_tokens)
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
            "total_tokens=%s cached_tokens=%s finish=%s",
            what, self.model_id, elapsed,
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
            _cached_prompt_tokens(usage),
            choice.finish_reason,
        )
        # The single metering point for this backend: every provider call passes through here, so the
        # agentic loop's extra rounds are counted without any caller having to know they happened.
        metering.record(getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
        return choice, usage

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        choice, usage = self._complete(
            render_messages(prompt, lang),
            max_tokens=max_tokens, temperature=temperature, what="generate",
        )
        return LLMResult(
            text=_answer_text(choice),
            finish_reason=choice.finish_reason or "stop",
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        """UNMETERED, and unreachable today — its only caller, Pipeline.ask_stream, has no callers.

        `generate()` above records into `metering` from the usage block the provider returns once the
        answer is complete. A stream has no such block until it ends, so nothing here counts anything:
        wiring this to an endpoint as-is would serve tokens that no quota debits and no invoice line
        explains. Whoever enables streaming must add `stream_options={"include_usage": True}` and
        record the final usage chunk before this becomes a live path.
        """
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
