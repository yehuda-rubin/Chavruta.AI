import os
from unittest.mock import MagicMock
import pytest

from app import db
from chavruta.llm.base import GroundedPrompt
from chavruta.llm.fallback import FallbackLLM


@pytest.fixture(autouse=True)
def reset_budget_before_and_after():
    db.reset_mistral_budget()
    yield
    db.reset_mistral_budget()


def test_mistral_budget_initial_state():
    status = db.get_mistral_budget_status()
    assert status["budget_limit_usd"] == 9.0
    assert status["spent_usd"] == 0.0
    assert status["remaining_usd"] == 9.0
    assert status["is_exceeded"] is False
    assert status["prompt_tokens"] == 0
    assert status["completion_tokens"] == 0


def test_mistral_cost_calculation_and_recording():
    # 1M prompt tokens @ $0.50/1M = $0.50
    # 1M completion tokens @ $1.50/1M = $1.50
    # Total for 1M each = $2.00
    status = db.record_mistral_usage(1_000_000, 1_000_000)
    assert status["spent_usd"] == 2.0
    assert status["remaining_usd"] == 7.0
    assert status["is_exceeded"] is False

    # Another 2M completion tokens = 2 * $1.50 = $3.00
    status = db.record_mistral_usage(0, 2_000_000)
    assert status["spent_usd"] == 5.0
    assert status["remaining_usd"] == 4.0
    assert status["is_exceeded"] is False


def test_mistral_budget_exceeded_threshold():
    # Record usage that totals exactly $9.00
    # 6M prompt tokens ($3.00) + 4M completion tokens ($6.00) = $9.00
    status = db.record_mistral_usage(6_000_000, 4_000_000)
    assert status["spent_usd"] == 9.0
    assert status["remaining_usd"] == 0.0
    assert status["is_exceeded"] is True
    assert db.is_mistral_budget_exceeded() is True


def test_fallback_llm_routes_to_nebius_when_budget_exceeded():
    # Exhaust the $9 budget
    db.record_mistral_usage(6_000_000, 4_000_000)
    assert db.is_mistral_budget_exceeded() is True

    primary = MagicMock()
    primary.model_id = "mistral-large-2512"

    secondary = MagicMock()
    secondary.model_id = "nebius-qwen"
    secondary.stream.return_value = iter(["תשובה", " מנביוס"])
    mock_res = MagicMock()
    mock_res.text = "תשובה מנביוס"
    mock_res.model_used = "nebius-qwen"
    secondary.generate.return_value = mock_res

    fallback = FallbackLLM(primary=primary, secondary=secondary)
    prompt = GroundedPrompt(system="sys", sources=[], question="שאלה")

    # 1. Test streaming failover due to budget limit
    tokens = list(fallback.stream(prompt, lang="he", max_tokens=100, temperature=0.2))
    assert tokens == ["תשובה", " מנביוס"]
    # Primary should never have been called!
    assert primary.stream.call_count == 0
    assert secondary.stream.call_count == 1

    # 2. Test generate failover due to budget limit
    res = fallback.generate(prompt, lang="he", max_tokens=100, temperature=0.2)
    assert res.text == "תשובה מנביוס"
    assert primary.generate.call_count == 0
    assert secondary.generate.call_count == 1
