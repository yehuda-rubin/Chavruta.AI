"""Unit tests for FallbackLLM (Gemini -> Nebius failover and circuit breaker)."""

from __future__ import annotations

from chavruta.llm.base import GroundedPrompt, LLMResult
from chavruta.llm.fallback import FallbackLLM


class FakeBackend:
    def __init__(self, model_id: str, fail: bool = False, fail_type: str = "transient"):
        self.model_id = model_id
        self.fail = fail
        self.fail_type = fail_type
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        if self.fail:
            if self.fail_type == "quota":
                raise RuntimeError("429 Resource_Exhausted: rate limit exceeded")
            else:
                raise TimeoutError("Connection timed out")
        return LLMResult(text=f"success from {self.model_id}", model_used=self.model_id)

    def stream(self, prompt, **kwargs):
        yield f"stream from {self.model_id}"

    def request(self, body_md, **kwargs):
        return (f"req from {self.model_id}", [])


def test_primary_succeeds():
    p1 = FakeBackend("gemini")
    p2 = FakeBackend("nebius")
    fb = FallbackLLM(p1, p2)
    res = fb.generate(
        GroundedPrompt(system="", sources=[], question="hello"),
        lang="he",
        max_tokens=100,
        temperature=0.1,
    )
    assert res.text == "success from gemini"
    assert res.model_used == "gemini"
    assert p1.calls == 1
    assert p2.calls == 0


def test_failover_on_timeout():
    p1 = FakeBackend("gemini", fail=True, fail_type="timeout")
    p2 = FakeBackend("nebius")
    fb = FallbackLLM(p1, p2)
    res = fb.generate(
        GroundedPrompt(system="", sources=[], question="hello"),
        lang="he",
        max_tokens=100,
        temperature=0.1,
    )
    assert res.text == "success from nebius"
    assert res.model_used == "nebius"
    assert p1.calls == 1
    assert p2.calls == 1


def test_circuit_breaker_on_quota():
    p1 = FakeBackend("gemini", fail=True, fail_type="quota")
    p2 = FakeBackend("nebius")
    fb = FallbackLLM(p1, p2, breaker_cooldown_s=60.0)

    # First call fails on primary, trips breaker, falls back to secondary
    res1 = fb.generate(
        GroundedPrompt(system="", sources=[], question="q1"),
        lang="he",
        max_tokens=100,
        temperature=0.1,
    )
    assert res1.model_used == "nebius"
    assert p1.calls == 1
    assert p2.calls == 1

    # Second call bypasses primary while breaker is open
    res2 = fb.generate(
        GroundedPrompt(system="", sources=[], question="q2"),
        lang="he",
        max_tokens=100,
        temperature=0.1,
    )
    assert res2.model_used == "nebius"
    assert p1.calls == 1  # Primary was not called again!
    assert p2.calls == 2
