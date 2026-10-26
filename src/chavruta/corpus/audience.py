"""Who is asking, as far as retrieval and prompting are concerned (spec 009-school-minors).

A request made by a minor carries two things the deep layers need and cannot be handed one parameter at
a time: that the audience is a minor (FR-016..019: the safety block goes into EVERY system prompt), and
that some works are denied to them (R10: the union of their school's and their parents' denylists).
They are reached through the retriever, the link expander, the agentic ===NEED_SOURCES=== fetcher, the
base-source floor, the calendar modes and ten prompt builders; threading two arguments through all of
that is how a path gets missed. So they ride a ContextVar, like `llm.base._SOURCE_NOTE`.

Set with `use(scope)` around ONE synchronous unit of work (the whole of `app/api.py::_run_query`, or the
single `ask_stream` call). Never set it across a `yield`: a generator's later `next()` runs in a fresh
copy of the context, so a value set before a yield is not there after it.

The default is the adult scope: not a minor, nothing denied. Reading it costs nothing, and every consumer
treats the default as "behave exactly as before".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Denylist:
    """What a request may not retrieve. `work_ids` are corpus tier slugs (the payload `work_id`, enforced
    in Qdrant as `must_not`); `titles` are Sefaria work titles (enforced by post-filter on the hit's ref,
    because no payload field names a book — see specs/009-school-minors/research.md, R10 investigation)."""

    work_ids: frozenset[str] = frozenset()
    titles: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.work_ids or self.titles)


@dataclass(frozen=True)
class AudienceScope:
    minor: bool = False
    deny: Denylist = field(default_factory=Denylist)


ADULT = AudienceScope()
_SCOPE: ContextVar[AudienceScope] = ContextVar("chavruta_audience_scope", default=ADULT)


def current() -> AudienceScope:
    return _SCOPE.get()


def set_scope(scope: AudienceScope):
    """Returns a reset token. Prefer `use()`; this exists for the one caller that already has a
    try/finally of its own (`_run_query`)."""
    return _SCOPE.set(scope)


def reset_scope(token) -> None:
    _SCOPE.reset(token)


@contextmanager
def use(scope: AudienceScope) -> Iterator[AudienceScope]:
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)
