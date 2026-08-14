"""Token metering across thread pools — the leak that showed up on an invoice.

metering.record() adds to a tally held in a ContextVar and returns silently when there is none,
because "outside a metered block" is a legitimate state: the CLI and the tests run that way. That
same branch is what made this invisible.

`concurrent.futures` gives every worker thread a FRESH context. So a bare `pool.map(fn, xs)` around
anything that reaches the provider loses the tally, and those calls are billed by the provider while
being counted by nobody — not the usage figures, not the user's quota. Found on 2026-08-13 by
reconciling our own totals against a real Nebius invoice: 4.81M input tokens recorded, 6.69M charged.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import app.api as api

from chavruta.llm import metering


def test_a_bare_pool_loses_the_tally():
    """The behaviour itself, pinned. Not a bug to fix in concurrent.futures — a property to design
    around, and the reason run_in_context exists."""
    with metering.meter() as tally:
        metering.record(100, 10)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: metering.record(1000, 100), range(3)))
    assert tally["prompt_tokens"] == 100, "a bare pool suddenly counting would mean the fix is moot"


def test_run_in_context_carries_the_tally_into_workers():
    with metering.meter() as tally:
        metering.record(100, 10)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(metering.run_in_context(lambda _: metering.record(1000, 100)), range(3)))
    assert tally == {"prompt_tokens": 3100, "completion_tokens": 310, "calls": 4}


class _CountingLLM:
    """Stands in for the provider: records usage exactly where CloudLLM does, and nowhere else."""

    serial_only = False

    def complete(self, *a, **k):
        metering.record(500, 50)
        return "משפט מתוקן בעברית בלבד"


def test_the_bleed_fixer_bills_the_request_it_belongs_to(monkeypatch):
    """The real path. Two bleeding sentences means two provider calls on two worker threads; before
    run_in_context both vanished from the tally while still appearing on the bill."""
    monkeypatch.setattr(api, "_rewrite_bleeding_sentence",
                        lambda sentence, llm: llm.complete())

    text = "הרמב\"ם writes כך. ותוספות disagree על כך."
    with metering.meter() as tally:
        api._fix_bleeding_sentences(text, True, _CountingLLM())

    assert tally["calls"] >= 1, "the bleed fixer's provider calls are unmetered again"
    assert tally["prompt_tokens"] == 500 * tally["calls"]


def test_many_overlapping_workers_all_count(monkeypatch):
    """The first version of run_in_context captured a contextvars.Context and called ctx.run() in
    every worker. A Context is not re-entrant, so the moment two workers overlapped it raised
    "cannot enter context: already entered" — precisely when a pool is worth having. Eight workers
    hammering one tally is the shape that caught it."""
    import threading

    barrier = threading.Barrier(8)

    def one(_):
        barrier.wait(timeout=5)      # force genuine overlap, not lucky serialisation
        metering.record(10, 1)

    with metering.meter() as tally:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(metering.run_in_context(one), range(8)))

    assert tally == {"prompt_tokens": 80, "completion_tokens": 8, "calls": 8}


def test_wrapping_outside_a_metered_block_is_a_no_op():
    """The CLI and the tests run unmetered. Wrapping must not invent a tally for them."""
    fn = metering.run_in_context(lambda: metering.record(999, 99))
    fn()                                     # must not raise
    assert metering.current() is None
