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

Usage:

    with metering.meter() as usage:
        ...                                    # any number of LLM calls, any depth
    spent = usage["prompt_tokens"], usage["completion_tokens"]
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_usage: ContextVar[dict | None] = ContextVar("chavruta_llm_usage", default=None)


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
    tally["prompt_tokens"] += max(0, int(prompt_tokens or 0))
    tally["completion_tokens"] += max(0, int(completion_tokens or 0))
    tally["calls"] += 1


def current() -> dict | None:
    """The active tally, or None outside a metered block."""
    return _usage.get()
