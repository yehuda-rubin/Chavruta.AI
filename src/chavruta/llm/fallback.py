"""FallbackLLM — automatic primary -> fallback failover (Gemini -> Nebius).

Implements LLMBackend. Routes requests first to a high-quality/zero-cost primary model
(e.g. Gemini 3.1 Flash-Lite on Google AI Studio Free Tier). If the primary model fails
due to quota exhaustion (429 / RESOURCE_EXHAUSTED), temporary overload (503), or timeout,
the request is seamlessly and automatically failed over to a reliable secondary provider
(e.g. Nebius Qwen3-235B).

Includes a circuit breaker so that if the primary model's daily/hourly quota is exhausted,
subsequent requests bypass the primary model immediately to avoid adding unnecessary latency.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator

from chavruta.llm.base import GroundedPrompt, LLMBackend, LLMResult, SourceBlock
from chavruta.llm.cloud import LLMConfigError, LLMTransientError

_log = logging.getLogger("chavruta.llm.fallback")


class FallbackLLM:
    """Combines a primary and secondary LLMBackend with automatic failover and circuit breaker."""

    profile = "cloud"

    def __init__(
        self,
        primary: LLMBackend,
        secondary: LLMBackend,
        *,
        breaker_cooldown_s: float | None = None,
    ):
        self.primary = primary
        self.secondary = secondary
        self.last_model_used: str = ""
        self._source_fetcher: Callable[[list[str]], list[SourceBlock]] | None = None

        if breaker_cooldown_s is None:
            self.breaker_cooldown_s = float(
                os.environ.get("CHAVRUTA_LLM_FALLBACK_COOLDOWN_S", "900.0")
            )  # 15 minutes default
        else:
            self.breaker_cooldown_s = breaker_cooldown_s

        self._primary_open_until: float = 0.0
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        if self._is_primary_open():
            return getattr(self.secondary, "model_id", "fallback")
        return self.last_model_used or getattr(self.primary, "model_id", "primary")

    @property
    def source_fetcher(self) -> Callable[[list[str]], list[SourceBlock]] | None:
        return self._source_fetcher

    @source_fetcher.setter
    def source_fetcher(self, fn: Callable[[list[str]], list[SourceBlock]] | None) -> None:
        self._source_fetcher = fn
        if hasattr(self.primary, "source_fetcher"):
            self.primary.source_fetcher = fn
        if hasattr(self.secondary, "source_fetcher"):
            self.secondary.source_fetcher = fn

    def _is_primary_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._primary_open_until

    def _trip_primary_circuit(self, duration_s: float, reason: str = "") -> None:
        with self._lock:
            self._primary_open_until = time.monotonic() + duration_s
            _log.warning(
                "Primary LLM circuit OPENED for %.0fs (%s). Routing directly to fallback.",
                duration_s,
                reason or "provider error",
            )

    def _reset_primary_circuit(self) -> None:
        with self._lock:
            self._primary_open_until = 0.0

    def _handle_primary_failure(self, exc: Exception) -> None:
        err_msg = str(exc).lower()
        is_quota = (
            "resource_exhausted" in err_msg
            or "quota" in err_msg
            or "429" in err_msg
            or "rate limit" in err_msg
            or "too many requests" in err_msg
        )
        is_auth_or_config = (
            "authentication" in err_msg
            or "401" in err_msg
            or "403" in err_msg
            or "permission_denied" in err_msg
            or "invalid_api_key" in err_msg
            or isinstance(exc, LLMConfigError)
        )
        if is_quota:
            self._trip_primary_circuit(self.breaker_cooldown_s, reason=f"quota/rate-limit: {exc}")
        elif is_auth_or_config:
            self._trip_primary_circuit(self.breaker_cooldown_s, reason=f"auth/config error: {exc}")
        elif isinstance(exc, (LLMTransientError, TimeoutError, ConnectionError)):
            _log.warning("Primary transient failure: %s", exc)

    def generate(
        self,
        prompt: GroundedPrompt,
        *,
        lang: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResult:
        if not self._is_primary_open():
            try:
                res = self.primary.generate(
                    prompt, lang=lang, max_tokens=max_tokens, temperature=temperature
                )
                if not getattr(res, "model_used", ""):
                    res.model_used = getattr(self.primary, "model_id", "primary")
                self.last_model_used = res.model_used
                return res
            except Exception as exc:
                _log.warning(
                    "Primary LLM (%s) failed during generate (%s: %s). Falling back to secondary (%s).",
                    getattr(self.primary, "model_id", "primary"),
                    type(exc).__name__,
                    exc,
                    getattr(self.secondary, "model_id", "secondary"),
                )
                self._handle_primary_failure(exc)

        res = self.secondary.generate(
            prompt, lang=lang, max_tokens=max_tokens, temperature=temperature
        )
        if not getattr(res, "model_used", ""):
            res.model_used = getattr(self.secondary, "model_id", "secondary")
        self.last_model_used = res.model_used
        return res

    def stream(
        self,
        prompt: GroundedPrompt,
        *,
        lang: str,
        max_tokens: int,
        temperature: float,
    ) -> Iterator[str]:
        if not self._is_primary_open():
            try:
                it = self.primary.stream(
                    prompt, lang=lang, max_tokens=max_tokens, temperature=temperature
                )
                self.last_model_used = getattr(self.primary, "model_id", "primary")
                return it
            except Exception as exc:
                _log.warning("Primary LLM stream failed (%s). Falling back to secondary.", exc)
                self._handle_primary_failure(exc)

        self.last_model_used = getattr(self.secondary, "model_id", "secondary")
        return self.secondary.stream(
            prompt, lang=lang, max_tokens=max_tokens, temperature=temperature
        )

    def request(
        self,
        body_md: str,
        *,
        lang: str = "he",
        token_budget: int | None = None,
    ) -> tuple[str, list[SourceBlock]]:
        if not self._is_primary_open():
            try:
                ans, fetched = self.primary.request(body_md, lang=lang, token_budget=token_budget)
                from chavruta.llm.agentic import _CONFIG_MSG
                if ans and ans in _CONFIG_MSG.values():
                    raise LLMConfigError(f"Primary returned configuration error message: {ans}")
                self.last_model_used = getattr(self.primary, "model_id", "primary")
                return ans, fetched
            except Exception as exc:
                _log.warning("Primary LLM request failed (%s). Falling back to secondary.", exc)
                self._handle_primary_failure(exc)

        self.last_model_used = getattr(self.secondary, "model_id", "secondary")
        return self.secondary.request(body_md, lang=lang, token_budget=token_budget)
