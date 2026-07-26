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
