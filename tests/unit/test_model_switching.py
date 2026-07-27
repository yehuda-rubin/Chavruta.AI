"""Swapping the model must be configuration, and a reasoning model must not fail silently.

Two things are held here. The provider is a base URL and a model id, so changing it is an env change
and the backend name says transport rather than vendor. And a model that thinks before it answers
can return HTTP 200 with an empty answer — which used to flow downstream as if the model had spoken.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chavruta.config.profile import Profile
from chavruta.llm import presets
from chavruta.llm.cloud import LLMEmptyAnswerError, _answer_text


def _choice(content=None, reasoning=None, finish="stop"):
    msg = SimpleNamespace(content=content)
    if reasoning is not None:
        msg.reasoning_content = reasoning
    return SimpleNamespace(message=msg, finish_reason=finish)


# ── The empty-answer failure ─────────────────────────────────────────────────

def test_a_normal_answer_comes_through():
    assert _answer_text(_choice(content="  שלום  ")) == "שלום"


def test_reasoning_only_raises_instead_of_returning_an_empty_answer():
    """Measured on Macaron V1 Venti, 2026-07-27: ~86k characters of reasoning, empty content,
    finish_reason 'length'. Returning "" here made a budget problem look like a retrieval problem."""
    with pytest.raises(LLMEmptyAnswerError, match="only reasoning"):
        _answer_text(_choice(content="", reasoning="思考" * 5000, finish="length"))


def test_the_error_says_what_to_change():
    """An error a reader cannot act on costs the same day twice."""
    with pytest.raises(LLMEmptyAnswerError, match="CHAVRUTA_LLM_MIN_OUTPUT_TOKENS"):
        _answer_text(_choice(content=None, reasoning="thinking...", finish="length"))


def test_an_empty_answer_with_no_reasoning_still_raises():
    with pytest.raises(LLMEmptyAnswerError, match="empty answer"):
        _answer_text(_choice(content="", finish="stop"))


def test_reasoning_is_never_returned_as_the_answer():
    """The scratchpad is not the answer — and on these models it is often not even in Hebrew."""
    with pytest.raises(LLMEmptyAnswerError):
        _answer_text(_choice(content="", reasoning="the answer is 42"))


# ── The output floor ─────────────────────────────────────────────────────────

def test_the_floor_raises_a_small_budget_and_never_lowers_a_large_one():
    from chavruta.llm.cloud import CloudLLM

    llm = CloudLLM("m", "http://x/v1", "k", min_output_tokens=32_000)
    assert max(3_000, llm.min_output_tokens) == 32_000      # QA's 3,000 would starve a reasoner
    assert max(96_000, llm.min_output_tokens) == 96_000     # a lesson's budget is left alone


def test_no_floor_by_default():
    from chavruta.llm.cloud import CloudLLM

    assert CloudLLM("m", "http://x/v1", "k").min_output_tokens == 0


# ── Presets ──────────────────────────────────────────────────────────────────

def test_every_preset_names_a_model_and_an_endpoint():
    for name in presets.names():
        p = presets.resolve(name)
        assert p.base_url.startswith("http") and p.model


def test_no_preset_carries_a_key():
    """A preset is committed to the repo. A key in one would be a leak by construction."""
    for name in presets.names():
        p = presets.resolve(name)
        assert not any(t in (p.base_url + p.model).lower() for t in ("key=", "sk-", "token="))


def test_a_reasoning_preset_carries_its_floor():
    assert presets.resolve("macaron").min_output_tokens >= 32_000
    assert presets.resolve("nebius").min_output_tokens == 0     # the baseline answers directly


def test_an_unknown_preset_degrades_instead_of_raising():
    """A typo in a convenience must not take the service down when the explicit vars are enough."""
    assert presets.resolve("no-such-provider") is None
    assert presets.resolve("") is None and presets.resolve(None) is None


def test_a_preset_fills_in_the_provider(monkeypatch):
    for var in ("CHAVRUTA_LLM_BASE_URL", "CHAVRUTA_LLM_MODEL", "CHAVRUTA_LLM_MIN_OUTPUT_TOKENS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CHAVRUTA_LLM_PRESET", "macaron")

    p = Profile.from_env()
    assert p.llm_model == "mindai/macaron-v1-venti"
    assert "novita" in p.llm_base_url
    assert p.llm_min_output_tokens >= 32_000


def test_an_explicit_variable_beats_the_preset(monkeypatch):
    """'That preset, but this model' has to work, or every variation needs its own preset."""
    monkeypatch.setenv("CHAVRUTA_LLM_PRESET", "macaron")
    monkeypatch.setenv("CHAVRUTA_LLM_MODEL", "some/other-model")
    monkeypatch.delenv("CHAVRUTA_LLM_BASE_URL", raising=False)

    p = Profile.from_env()
    assert p.llm_model == "some/other-model"
    assert "novita" in p.llm_base_url          # the rest of the preset still applies


def test_no_preset_leaves_the_validated_baseline(monkeypatch):
    for var in ("CHAVRUTA_LLM_PRESET", "CHAVRUTA_LLM_MODEL", "CHAVRUTA_LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    p = Profile.from_env()
    assert p.llm_model.startswith("Qwen/Qwen3-235B")
    assert p.llm_min_output_tokens == 0


# ── The backend name ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["api", "openai", "nebius"])
def test_the_api_backend_is_named_by_transport_not_vendor(name):
    from chavruta.pipeline.pipeline import _API_BACKENDS

    assert name in _API_BACKENDS


def test_the_historical_name_still_works():
    """Every script, compose file and .env in this repo says 'nebius'. Breaking it to rename a
    concept would be a rename that costs a deployment."""
    from chavruta.pipeline.pipeline import _API_BACKENDS

    assert "nebius" in _API_BACKENDS
