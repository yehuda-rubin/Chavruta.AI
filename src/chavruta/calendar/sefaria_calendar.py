"""Which parsha/daf applies right now — leaning on Sefaria's own `/api/calendars`, not homemade
Hebrew-calendar math.

Getting this wrong (a holiday overriding the regular parsha, a combined-parsha week, the Daf Yomi
cycle's skip-Yom-Kippur accounting) is embarrassing on a Torah-study app and easy to get subtly
wrong by hand. Sefaria already maintains this centrally and returns both in Sefaria's own ref
vocabulary (`Genesis 1:1-6:8`, `Chullin 97`) — the exact vocabulary `chavruta.corpus.refs` is built
to consume. So there is no local parsha-name table and no Daf Yomi cycle-start-date arithmetic here;
this module is just a thin, retrying HTTP client plus the two lookups callers need.

IMPORTANT — this module is IDENTIFICATION only, never content: `/api/calendars` returns a whole
day's worth of items (Parashat Hashavua, Haftarah, 929, Daily Mishnah, Daily Rambam, Daf a Week, …),
each with its own description/aliyot/etc. `ParshaInfo`/`DafYomiInfo` below keep only a name and a
ref — enough to know WHICH parsha/daf it is. The actual verse/Gemara/Rashi/Tosafot TEXT a caller
generates from always comes from our own corpus (fetch_by_refs in app/api.py), never from this
API — we already have that text in the RAG; Sefaria's calendar just says which of it applies today.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

API = "https://www.sefaria.org/api/calendars"
_MAX_ATTEMPTS = 5
_RETRY_BACKOFF_S = 1.5   # short, fixed backoff between attempts — this is a same-request retry,
                          # not a background poll, so it should resolve in a few seconds or give up

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParshaInfo:
    name_en: str      # e.g. "Re'eh" (also the combined name on a doubled week, e.g. "Vayakhel-Pekudei")
    name_he: str
    ref_range: str    # Sefaria's own ref, e.g. "Genesis 1:1-6:8" — the FULL range, already
                       # holiday/combined-week correct; nothing here re-derives it


@dataclass(frozen=True)
class DafYomiInfo:
    tractate: str     # e.g. "Chullin"
    daf: int          # e.g. 97 — no amud: Daf Yomi covers BOTH amudim of this daf in one day


def _fetch_calendar_items() -> list[dict] | None:
    """One HTTP call, up to _MAX_ATTEMPTS tries. Returns None only if every attempt failed —
    callers show a friendly "couldn't resolve, try again shortly" message, never a raw error."""
    import requests  # lazy, matching chavruta.corpus.sources.sefaria's convention

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(API, params={"timezone": "Asia/Jerusalem"}, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("calendar_items")
            if isinstance(items, list):
                return items
            last_exc = ValueError(f"unexpected /api/calendars shape: {resp.json()!r}")
        except Exception as exc:  # noqa: BLE001 — any failure just counts as an attempt
            last_exc = exc
        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_S)
    _log.warning("Sefaria /api/calendars failed after %d attempts", _MAX_ATTEMPTS, exc_info=last_exc)
    return None


def _find(items: list[dict], title_en: str) -> dict | None:
    for item in items:
        if (item.get("title") or {}).get("en") == title_en:
            return item
    return None


def resolve_parsha() -> ParshaInfo | None:
    items = _fetch_calendar_items()
    if items is None:
        return None
    item = _find(items, "Parashat Hashavua")
    if not item or not item.get("ref"):
        return None
    display = item.get("displayValue") or {}
    return ParshaInfo(
        name_en=display.get("en", ""), name_he=display.get("he", ""), ref_range=item["ref"],
    )


def resolve_daf_yomi() -> DafYomiInfo | None:
    items = _fetch_calendar_items()
    if items is None:
        return None
    item = _find(items, "Daf Yomi")
    ref = (item or {}).get("ref", "")
    # "Chullin 97" — tractate + daf, no amud (Daf Yomi covers both sides of the daf in one day).
    parts = ref.rsplit(" ", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return DafYomiInfo(tractate=parts[0], daf=int(parts[1]))
