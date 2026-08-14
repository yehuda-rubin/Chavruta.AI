"""Per-request token accounting.

The account quota is denominated in tokens, so something has to add up what one HTTP request spent.
That is harder than it looks: a single question can become several provider calls — the agentic
===NEED_SOURCES=== loop re-sends the whole growing job up to four times — and the calls happen deep
inside the pipeline, several layers below anything that knows which user is asking.

Rather than thread a sink parameter through every layer (invasive, and easy to forget at a new call
site — which would silently under-bill), each backend records at the ONE place it actually talks to
the provider. A ContextVar carries the tally, so:

  • loops and nested helpers are counted automatically, with no plumbing;
  • concurrent requests never mix, since each gets its own context — FastAPI's threadpool copies the
    context per call, so a `def` endpoint is as safe here as an `async` one;
  • code running outside a metered block records into nothing, which is exactly what CLI and test
    use should do.

THE ONE PLACE THAT SILENTLY FAILS — read before starting a thread near an LLM call
----------------------------------------------------------------------------------
`concurrent.futures` does NOT carry the context into its workers: every pool thread starts with a
fresh, empty one, so `record()` there finds no tally and drops the call on the floor. That is the
same "records into nothing" branch the CLI relies on, which is why it never looked like a bug.

It cost real money. `app/api.py::_fix_bleeding_sentences` rewrites bleeding sentences through a
ThreadPoolExecutor, up to _MAX_BLEED_FIXES per answer, and every one of those calls reached the
provider, appeared on the bill, and was invisible both to the usage figures and to the user's quota.
Found on 2026-08-13 by reconciling our own totals against an actual Nebius invoice: 4.81M input
tokens recorded against 6.69M billed.

`run_in_context` below is the fix. Use it for ANY pool that may reach a provider.

Usage:

    with metering.meter() as usage:
        ...                                    # any number of LLM calls, any depth
    spent = usage["prompt_tokens"], usage["completion_tokens"]
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

_usage: ContextVar[dict | None] = ContextVar("chavruta_llm_usage", default=None)
_LOCK = Lock()


@contextmanager
def meter() -> Iterator[dict]:
    """Collect the token spend of everything that runs inside the block."""
    tally = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    token = _usage.set(tally)
    try:
        yield tally
    finally:
        _usage.reset(token)


def record(prompt_tokens: int, completion_tokens: int) -> None:
    """Add one provider call's usage to the active tally, if any. Never raises: metering must not be
    able to break a request that is otherwise fine."""
    tally = _usage.get()
    if tally is None:
        return
    # Locked because run_in_context lets several worker threads share one tally, and `+=` on a
    # dict entry is a read-modify-write. Contention is negligible; a lost update is money.
    with _LOCK:
        tally["prompt_tokens"] += max(0, int(prompt_tokens or 0))
        tally["completion_tokens"] += max(0, int(completion_tokens or 0))
        tally["calls"] += 1


def current() -> dict | None:
    """The active tally, or None outside a metered block."""
    return _usage.get()


def run_in_context(fn):
    """Wrap `fn` so a pool thread bills the request that started the pool.

    For any worker that may reach a provider. `concurrent.futures` gives each thread a fresh context,
    so a bare `pool.map(fn, xs)` loses the tally and the calls inside it are billed by the provider
    and counted by nobody — silently, because recording outside a metered block is a legitimate state
    (the CLI).

        with ThreadPoolExecutor() as pool:
            pool.map(metering.run_in_context(do_one), items)

    The TALLY is captured here, on the calling thread, and each worker points its own context at that
    same dict. The first version of this captured a `contextvars.Context` and called `ctx.run()` in
    every worker — which raises "cannot enter context: already entered" the moment two of them
    overlap, i.e. exactly when a pool is worth using. A Context is not re-entrant; a dict is.
    """
    tally = _usage.get()
    if tally is None:
        return fn                       # nothing to carry — outside a metered block

    def _run(*args, **kwargs):
        token = _usage.set(tally)
        try:
            return fn(*args, **kwargs)
        finally:
            _usage.reset(token)

    return _run
