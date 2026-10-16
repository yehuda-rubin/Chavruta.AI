"""Per-request switch for the improved chavruta answer path.

The improvements (stricter chavruta prompt, quote-by-reference, up to 5 agentic rounds with small
fetches) are rolled out to the operator's own account first. A ContextVar carries the decision from
the request entry point down to the code that has to behave differently (job text, agentic loop,
source fetcher) without threading a flag through every signature. It defaults to OFF, so any code
path that never sets it — and any thread that does not inherit the context — keeps the old behaviour.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar

_improved: ContextVar[bool] = ContextVar("chavruta_improved", default=False)


def improved() -> bool:
    return _improved.get()


@contextmanager
def improved_for(on: bool):
    token = _improved.set(bool(on))
    try:
        yield
    finally:
        _improved.reset(token)


def enabled_for(is_admin: bool) -> bool:
    """Who gets the improved path. CHAVRUTA_IMPROVED_SCOPE: "all" (default) | "admin" | "off".
    Setting it to "admin" and recreating the api container is the fast rollback (no image build)."""
    scope = os.environ.get("CHAVRUTA_IMPROVED_SCOPE", "all").strip().lower()
    if scope == "off":
        return False
    if scope == "admin":
        return bool(is_admin)
    return True
