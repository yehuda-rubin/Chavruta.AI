"""One channel for every watching guard's findings.

The three post-generation checks — misattribution (`grounded.misattributed_quotes`), deontic
self-contradiction (`deontic.deontic_conflicts`) and calendar-determinate claims
(`computed.check_calendar_claims`) — are INTERNAL ONLY by decision on 2026-08-13. They add nothing a
user sees, because none of them has met real traffic yet and a caveat on a correct answer costs more
than a missed finding on a wrong one. They watch; we read what they caught; only what earns it goes
in front of anybody.

"Read what they caught" was `docker compose logs | grep`, which is not a thing an operator does
weekly. So a finding goes two places at once: the log, and — if a sink has been registered — durable
storage the admin panel can query.

WHY A SINK RATHER THAN AN IMPORT
--------------------------------
Nothing under `src/chavruta` imports `app.*`, anywhere in this repo. The engine has to keep running
in the CLI and in tests with no database at all, and reaching into the web layer for a diagnostic
would end that. So the web layer registers a writer at startup (`app/api.py`), and everything here
stays a no-op until it does. A missing sink is the normal state, not a failure.

WHAT A FINDING MAY CONTAIN — read before adding a field
-------------------------------------------------------
Only the MODEL'S OWN OUTPUT and corpus text: the sentence it wrote, the name it credited, the ref the
text actually came from. **Never the user's question**, and no owner or session id. This is a record
of how well the system writes, not of who asked what — which is also why `guard_findings` needs no
handling in `db.purge_owner`: there is nothing in it belonging to a person.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("chavruta.guards")

# (kind, intent, detail) -> None. Registered by the web layer; None means log-only.
_sink: Callable[[str, str, dict[str, Any]], None] | None = None

# What a caller may report. A typo in a kind would produce a category the panel silently never shows,
# so it is checked rather than trusted.
KINDS = ("misattribution", "deontic", "calendar")


def set_sink(fn: Callable[[str, str, dict[str, Any]], None] | None) -> None:
    """Install (or clear, with None) the durable writer. Idempotent; last call wins."""
    global _sink
    _sink = fn


def report(kind: str, intent: str, detail: dict[str, Any], *, summary: str = "") -> None:
    """Record one finding. Never raises — a guard that only watches must not be able to break the
    answer it is watching, and that includes failing while writing down what it saw."""
    if kind not in KINDS:
        _log.error("guard reported unknown kind %r — dropped", kind)
        return
    try:
        _log.warning("%s [%s] %s", kind, intent or "?", summary or detail)
    except Exception:                       # noqa: BLE001
        pass
    if _sink is None:
        return
    try:
        _sink(kind, intent or "", detail)
    except Exception:                       # noqa: BLE001 — storage is the optional half
        _log.exception("guard sink failed for %s", kind)
