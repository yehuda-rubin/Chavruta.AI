"""Token metering — the mechanism the token-denominated quota rests on.

If this under-counts, users get compute for free; if it leaks between requests, one account is
charged for another's work. Both failures are silent, so they are pinned here.
"""

from __future__ import annotations

import threading

from chavruta.llm import metering


def test_records_inside_a_meter():
    with metering.meter() as usage:
        metering.record(1000, 200)
        metering.record(500, 100)
    assert usage == {"prompt_tokens": 1500, "completion_tokens": 300, "calls": 2}


def test_recording_outside_a_meter_is_a_no_op():
    """CLI and test use run unmetered; that must not raise or leak into the next request."""
    metering.record(999, 999)
    assert metering.current() is None


def test_meter_does_not_leak_after_the_block():
    with metering.meter():
        metering.record(10, 10)
    assert metering.current() is None


def test_nested_meters_restore_the_outer_one():
    with metering.meter() as outer:
        metering.record(100, 0)
        with metering.meter() as inner:
            metering.record(50, 0)
        assert inner["prompt_tokens"] == 50
        metering.record(1, 0)
    assert outer["prompt_tokens"] == 101       # the inner block's spend is NOT double-counted


def test_concurrent_requests_do_not_mix():
    """Each request must be billed its own tokens. A shared module-level tally would fail this —
    which is why the tally lives in a ContextVar."""
    totals: dict[int, int] = {}
    lock = threading.Lock()

    def work(n: int) -> None:
        with metering.meter() as usage:
            for _ in range(20):
                metering.record(n, 0)
            with lock:
                totals[n] = usage["prompt_tokens"]

    threads = [threading.Thread(target=work, args=(i,)) for i in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert totals == {i: i * 20 for i in range(1, 9)}


def test_negative_and_none_are_ignored():
    """A provider that omits usage must not corrupt the tally."""
    with metering.meter() as usage:
        metering.record(None, None)        # type: ignore[arg-type]
        metering.record(-5, 10)
    assert usage["prompt_tokens"] == 0 and usage["completion_tokens"] == 10


# ── The normalized unit ───────────────────────────────────────────────────────
def test_completion_tokens_cost_more_than_prompt_tokens():
    """Output is several times the price of input everywhere, so a raw sum would bill a long paste
    like a long answer."""
    from app import plans

    assert plans.normalized_tokens(1000, 0) == 1000
    assert plans.normalized_tokens(0, 1000) == 3000
    assert plans.normalized_tokens(1000, 1000) == 4000


def test_normalized_tokens_survives_missing_usage():
    from app import plans

    assert plans.normalized_tokens(0, 0) == 0
    assert plans.normalized_tokens(-10, -10) == 0


def test_normalized_tokens_distiller_model():
    """Distiller models: Gemma-3-27B (0.50/1.50) and Llama-3.3-70B (0.65/2.0)."""
    from app import plans

    gemma_model = "google/gemma-3-27b-it"
    # 1000 * 0.50 + 0 * 1.50 = 500
    assert plans.normalized_tokens(1000, 0, model=gemma_model) == 500
    # 0 * 0.50 + 1000 * 1.50 = 1500
    assert plans.normalized_tokens(0, 1000, model=gemma_model) == 1500
    # 1000 * 0.50 + 200 * 1.50 = 500 + 300 = 800
    assert plans.normalized_tokens(1000, 200, model=gemma_model) == 800
    assert plans.billed_tokens_for_model(1000, 200, gemma_model) == 800

    llama_model = "meta-llama/Llama-3.3-70B-Instruct"
    # 1000 * 0.65 + 0 * 2.0 = 650
    assert plans.normalized_tokens(1000, 0, model=llama_model) == 650
    # 0 * 0.65 + 1000 * 2.0 = 2000
    assert plans.normalized_tokens(0, 1000, model=llama_model) == 2000
    # 1000 * 0.65 + 200 * 2.0 = 650 + 400 = 1050
    assert plans.normalized_tokens(1000, 200, model=llama_model) == 1050
    assert plans.billed_tokens_for_model(1000, 200, llama_model) == 1050

    # Case insensitivity and substring matching ("llama-3.3-70b" or "70b")
    assert plans.normalized_tokens(100, 50, model="meta-llama/llama-3.3-70b-instruct") == round(100 * 0.65 + 50 * 2.0)
    assert plans.normalized_tokens(100, 50, model="deepseek-ai/DeepSeek-R1-Distill-Llama-70B") == round(100 * 0.65 + 50 * 2.0)
    assert plans.normalized_tokens(100, 50, model="google/gemma-3-27b-it") == round(100 * 0.50 + 50 * 1.50)

    # Gemini model: $0.30 input / $3.00 output vs baseline $0.20 -> 1.50x prompt, 15.0x completion
    # 1000 * 1.50 + 200 * 15.0 = 1500 + 3000 = 4500
    assert plans.normalized_tokens(1000, 200, model="gemini-3.1-flash-lite-preview") == 4500
    assert plans.normalized_tokens(1000, 200, model="gemini-2.5-flash") == 4500
    assert plans.normalized_tokens(1000, 0, model="gemini-3.5-flash-lite") == 1500
    assert plans.normalized_tokens(0, 100, model="gemini-3.5-flash-lite") == 1500

    # Baseline / unknown model falls back to prompt + 3 * completion
    assert plans.normalized_tokens(1000, 200, model="Qwen/Qwen3-235B-A22B-Instruct-2507") == 1600
    assert plans.normalized_tokens(1000, 200, model="") == 1600

    # Reranker model: priced at 1 cent per 1M tokens ($0.01 vs baseline $0.20 -> 0.05x)
    assert plans.normalized_tokens(1000, 0, model="BAAI/bge-reranker-v2-m3") == 50
    assert plans.normalized_tokens(1000, 0, model="@cf/baai/bge-reranker-base") == 50
    assert plans.normalized_tokens(2000, 0, model="reranker") == 100


def test_metering_record_with_model():
    """metering.record records model and tracks billed_tokens accordingly."""
    with metering.meter() as usage:
        metering.record(100, 20, model="meta-llama/Llama-3.3-70B-Instruct")
        metering.record(1000, 200, model="Qwen/Qwen3-235B-A22B-Instruct-2507")
        metering.record(1000, 0, model="BAAI/bge-reranker-v2-m3")
    assert usage["prompt_tokens"] == 2100
    assert usage["completion_tokens"] == 220
    assert usage["calls"] == 3
    # Distiller: round(100 * 0.65 + 20 * 2.0) = 105
    # Baseline: 1000 + 3 * 200 = 1600
    # Reranker: round(1000 * 0.05) = 50
    # Total billed_tokens: 1755
    assert usage["billed_tokens"] == 1755

