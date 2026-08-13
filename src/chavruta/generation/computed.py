"""Check the claims in an answer that have a COMPUTABLE right answer — the class grounding can't see.

`generation/grounded.py` asks one question: is every quoted span really in a retrieved source? That
holds the line at 0% ungrounded answers, but it is blind to a whole family of errors, because a
wrong number can be perfectly grounded. An answer may cite Chullin 104 correctly, quote it exactly,
and still open with "today we're learning Chullin 104" on a day the Daf Yomi is 105. Nothing in the
citation path contradicts that: the source is real, the quote is real, only the DATE-dependent claim
about it is false. Seen in production 2026-08-12 ("היום לומדים חולין קד").

We already know the answer to those questions — `calendar/sefaria_calendar.py` resolves today's daf
and this week's parsha — but that knowledge is used only as an ORACLE on the way in (app/api.py's
parsha / daf-yomi modes preload sources from it) and never as a CHECKER on the way out. This module
is the checker. It reads the generated text, pulls out the claims that are calendar-determinate,
and compares them with what the calendar actually says.

WHAT IT DELIBERATELY WILL NOT DO
--------------------------------
A false positive here is far worse than a miss: flagging a correct answer teaches everyone
downstream to ignore the signal. An answer is fully entitled to name a daf that is not today's —
quoting a sugya, comparing a parallel, giving an example — and that must never be touched. So a
mention becomes a CLAIM only when the text itself frames it as "now": היום / הדף היומי for a daf,
השבוע / פרשת השבוע for a parsha, in the same clause. Anything else is left alone, and a clause that
names two dapim is dropped as ambiguous rather than guessed at. The cost is misses; that is the
intended trade.

Two claim types are covered — the daf ("היום לומדים חולין קד") and the parsha ("פרשת השבוע היא
שופטים") — and only in HEBREW, since that is what the app answers in and what the miss was in.
Hebrew dates, zmanim, omer count and holiday claims are computable too but are not touched here:
each needs its own source of truth, and none of them is in `sefaria_calendar`'s two lookups.

Likewise, "I could not establish this" is reported as UNKNOWN, never as a mismatch: if the calendar
is unreachable, or the calendar's own parsha name is one this module can't map, the claim comes back
unverified. A contradiction is only ever reported when both sides are actually known.

NO NETWORK IN THE ANSWER PATH BY DEFAULT
----------------------------------------
`sefaria_calendar._fetch_calendar_items` is written for a deliberate "what is today's daf" job: five
attempts, a 10s timeout each, 1.5s between them — up to ~56 seconds. That is correct there and fatal
here, since this runs AFTER generation, on a request a user is waiting on. `resolve_facts` therefore
reads the SQLite calendar_cache the daf-yomi/parsha modes already populate (app/db.py's
calendar_cache, keyed exactly as app/api.py::_calendar_cache_key keys it) and touches the network
only if a caller explicitly passes a deadline — and even then the call is abandoned at that deadline
and reported as unknown. The cache reader is injected rather than imported: nothing under
src/chavruta imports the app layer, and this module is not the place to start.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from chavruta.calendar.sefaria_calendar import DafYomiInfo, ParshaInfo
from chavruta.corpus.normalize import normalize_he
from chavruta.intents.hebrew_refs import HE_TRACTATES, gematria

# ── what the calendar says ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalendarFacts:
    """The source of truth for one moment. A None field means "we do not know" — never "no daf"."""
    daf: DafYomiInfo | None = None
    parsha: ParshaInfo | None = None


@dataclass(frozen=True)
class CalendarClaim:
    kind: str      # "daf_yomi" | "parsha"
    stated: str    # canonicalised: "Chullin 104" for a daf, the Hebrew parsha name for a parsha
    span: str      # the clause it was read from, so a caller can show the user what was flagged


@dataclass(frozen=True)
class CalendarMismatch:
    kind: str
    stated: str
    expected: str
    span: str


@dataclass(frozen=True)
class CalendarCheck:
    """Deliberately three lists, not a boolean: "wrong", "right" and "couldn't tell" are three
    different things and only the caller knows what each is worth."""
    mismatches: list[CalendarMismatch] = field(default_factory=list)
    confirmed: list[CalendarClaim] = field(default_factory=list)
    unknown: list[CalendarClaim] = field(default_factory=list)


# ── Hebrew surface forms ────────────────────────────────────────────────────────

_HEL = "א-ת"
_MARKS = "׳״'\"`"

# A daf claim is read only inside a clause that frames it as today's. "היום" is a prefix of
# "היומי", so "הדף היומי" is caught by the same test.
_TODAY_MARKERS = ("היום", "היומי")

# ...and, on its own, "היום" is not enough to call a bare "<tractate> <number>" a daf: "היום שבת כ'
# באב" is a date, not Shabbat 20. A bare form is accepted only alongside one of these, which is what
# actually distinguishes learning from dating. An explicit "דף" or an ע"א/ע"ב marker in the match
# itself passes without needing one.
_STUDY_CUES = ("לומד", "למדנ", "נלמד", "מסיימ", "סיימנ", "מתחילי", "שיעור", "דף", "היומי")

_WEEK_MARKERS = ("השבוע", "שבוע זה", "השבת הקרובה", "שבת הקרובה", "השבת הזאת", "השבת הזו")

# Clause boundaries. A claim's framing and its value must sit in the SAME clause; splitting here is
# what stops "today we learn Chullin 104. Compare Berakhot 5b" from reading as one statement.
_CLAUSE_SPLIT = re.compile(r"[.!?\n;•]+")

_TRACTATE_ALT = "|".join(re.escape(n) for n in sorted(HE_TRACTATES, key=len, reverse=True))

# A daf number: digits, or a Hebrew numeral with or without gershayim (קד / ק״ד / כ / ל״ה).
_DAF_NUM = rf"(?:\d{{1,3}}|[{_HEL}]{{1,3}}[{_MARKS}]?[{_HEL}]{{0,2}})"
_DAF_RE = re.compile(
    rf"(?P<tractate>{_TRACTATE_ALT})\s+(?P<dafword>דף\s+)?(?P<num>{_DAF_NUM})(?![{_HEL}])"
    rf"\s*(?P<amud>ע[{_MARKS}]?\s?[אב](?![{_HEL}])|עמוד\s+[אב](?![{_HEL}]))?"
)

# Every parsha, with the spellings that actually occur: Sefaria's calendar answers in ktiv haser for
# a good number of them ("שפטים", "בהעלתך", "נצבים") while users write male ("שופטים"). normalize_he
# folds nikud and final letters but NOT a missing vav, so both spellings are listed and mapped to one
# canonical name. Sefaria's own name is looked up in this same table — if it is not here, the claim
# comes back unknown rather than mismatched.
_PARSHA_VARIANTS: tuple[tuple[str, ...], ...] = (
    ("בראשית",), ("נח",), ("לך לך", "לך-לך"), ("וירא",), ("חיי שרה",), ("תולדות", "תלדות"),
    ("ויצא",), ("וישלח",), ("וישב",), ("מקץ",), ("ויגש",), ("ויחי",),
    ("שמות",), ("וארא",), ("בא",), ("בשלח",), ("יתרו",), ("משפטים",), ("תרומה",),
    ("תצוה", "תצווה"), ("כי תשא",), ("ויקהל",), ("פקודי",),
    ("ויקרא",), ("צו",), ("שמיני",), ("תזריע",), ("מצורע", "מצרע"), ("אחרי מות", "אחרי"),
    ("קדושים", "קדשים"), ("אמור", "אמר"), ("בהר",), ("בחוקותי", "בחקתי", "בחוקתי"),
    ("במדבר",), ("נשא",), ("בהעלותך", "בהעלתך"), ("שלח לך", "שלח-לך", "שלח"), ("קרח",),
    ("חוקת", "חקת"), ("בלק",), ("פינחס", "פנחס"), ("מטות",), ("מסעי",),
    ("דברים",), ("ואתחנן",), ("עקב",), ("ראה",), ("שופטים", "שפטים"), ("כי תצא",),
    ("כי תבוא", "כי תבא"), ("ניצבים", "נצבים"), ("וילך",), ("האזינו",),
    ("וזאת הברכה", "זאת הברכה"),
)
_PARSHA_BY_NORM: dict[str, str] = {
    normalize_he(v): forms[0] for forms in _PARSHA_VARIANTS for v in forms
}
_PARSHA_ALT = "|".join(
    re.escape(v) for v in sorted(
        (v for forms in _PARSHA_VARIANTS for v in forms), key=len, reverse=True)
)

# The name must hang directly off the word פרשה/פרשת. Half the parsha names are ordinary Hebrew
# words — ראה, בא, נשא, עקב, שופטים (also the BOOK of Judges) — so a loose scan of a clause about
# this week would flag prose constantly.
_PARSHA_RE = re.compile(
    rf"פרש[הת]\s*(?:ה?שבוע|הקרובה|הבאה)?\s*(?:היא|הוא|הינה)?\s*[:,\-–—(\"'״]?\s*"
    rf"(?P<name>{_PARSHA_ALT})(?![{_HEL}])"
)

# Berakhot opens at 2 and Bava Batra, the longest tractate, ends at 176 — a value outside this is
# not a daf, which is what keeps "שבת קודש" (gematria 410) from parsing as Shabbat 410.
_MIN_DAF, _MAX_DAF = 2, 180


def _daf_value(token: str) -> int | None:
    core = "".join(ch for ch in token if ch not in _MARKS).strip()
    if core.isdigit():
        return int(core)
    return gematria(core)


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT.split(text or "") if c.strip()]


# ── extraction ──────────────────────────────────────────────────────────────────


def _daf_claim(clause: str) -> CalendarClaim | None:
    if not any(m in clause for m in _TODAY_MARKERS):
        return None
    found = []
    for m in _DAF_RE.finditer(clause):
        value = _daf_value(m.group("num"))
        if value is None or not _MIN_DAF <= value <= _MAX_DAF:
            continue
        explicit = bool(m.group("dafword") or m.group("amud"))
        if not explicit and not any(c in clause for c in _STUDY_CUES):
            continue
        found.append((HE_TRACTATES[m.group("tractate")], value))
    # Two dapim in one breath ("today is Chullin 104, unlike Berakhot 5b") — which one is the
    # today-claim is genuinely ambiguous, so make no claim at all rather than pick.
    if len(found) != 1:
        return None
    tractate, value = found[0]
    return CalendarClaim(kind="daf_yomi", stated=f"{tractate} {value}", span=clause)


def _parsha_claim(clause: str) -> CalendarClaim | None:
    if not any(m in clause for m in _WEEK_MARKERS):
        return None
    names = {_PARSHA_BY_NORM[normalize_he(m.group("name"))] for m in _PARSHA_RE.finditer(clause)}
    if len(names) != 1:
        return None
    return CalendarClaim(kind="parsha", stated=names.pop(), span=clause)


def extract_calendar_claims(text: str) -> list[CalendarClaim]:
    """Claims the text frames as being about NOW. At most one of each kind per clause; a clause
    that only mentions a daf/parsha without framing it as today's yields nothing."""
    claims: list[CalendarClaim] = []
    for clause in _clauses(text):
        for claim in (_daf_claim(clause), _parsha_claim(clause)):
            if claim is not None:
                claims.append(claim)
    return claims


# ── comparison ──────────────────────────────────────────────────────────────────


def _parsha_canon(name: str) -> str | None:
    return _PARSHA_BY_NORM.get(normalize_he(name))


def _expected_parsha_names(info: ParshaInfo) -> list[str]:
    """A doubled week reads "ויקהל-פקודי"; someone naming either half is right, not wrong."""
    parts = re.split(r"[-–—־]", info.name_he or "")
    canon = [_parsha_canon(p) for p in parts if p.strip()]
    return [c for c in canon if c]


def check_calendar_claims(text: str, facts: CalendarFacts) -> CalendarCheck:
    """Compare every today-framed claim in `text` against `facts`.

    Anything the facts can't settle lands in `unknown`, never in `mismatches`."""
    check = CalendarCheck()
    for claim in extract_calendar_claims(text):
        if claim.kind == "daf_yomi":
            if facts.daf is None:
                check.unknown.append(claim)
                continue
            expected = f"{facts.daf.tractate} {facts.daf.daf}"
            ok = claim.stated == expected
        else:
            expected_names = _expected_parsha_names(facts.parsha) if facts.parsha else []
            if not expected_names:
                # Either no parsha resolved, or the calendar named one this table doesn't hold —
                # in which case a "mismatch" would be a fact about our table, not about the answer.
                check.unknown.append(claim)
                continue
            expected = facts.parsha.name_he
            ok = claim.stated in expected_names
        if ok:
            check.confirmed.append(claim)
        else:
            check.mismatches.append(CalendarMismatch(
                kind=claim.kind, stated=claim.stated, expected=expected, span=claim.span))
    return check


# ── facts, without a way to hang the request ────────────────────────────────────


def _today(now: datetime | None = None) -> date:
    """Israel is UTC+2/+3 and the server runs UTC, so "today" from `date.today()` is wrong for the
    two-to-three hours after midnight local — exactly when a night-seder question arrives. Same
    reasoning (and the same env override) as app/api.py and scripts/nightly_eval.py."""
    tz = ZoneInfo(os.environ.get("CHAVRUTA_TZ", "Asia/Jerusalem"))
    return (now or datetime.now(tz)).astimezone(tz).date()


def cache_key(kind: str, today: date) -> str:
    """Must stay identical to app/api.py::_calendar_cache_key — this reads the buckets that writes."""
    if kind == "daf_yomi":
        return today.isoformat()
    return (today - timedelta(days=today.isoweekday() % 7)).isoformat()


def _bounded(fn: Callable[[], object], seconds: float):
    """Run `fn` but never wait longer than `seconds`. sefaria_calendar's resolvers retry for up to
    ~56s, which is right for a job the user asked for and unacceptable for a check they didn't; a
    call still in flight at the deadline is abandoned (daemon thread) and treated as unknown."""
    box: dict[str, object] = {}

    def _run() -> None:
        try:
            box["value"] = fn()
        except Exception:  # noqa: BLE001 — an unreachable calendar is "unknown", not an error path
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(seconds)
    return box.get("value")


def resolve_facts(
    *,
    load_cached: Callable[[str, str], str | None] | None = None,
    now: datetime | None = None,
    network_deadline_s: float = 0.0,
) -> CalendarFacts:
    """Today's daf and this week's parsha, from the cache the daf-yomi/parsha modes already fill.

    `load_cached` takes app/db.py's `get_calendar_cache(kind, date_key)` signature and is injected so
    this module stays inside src/chavruta (nothing there imports the app layer). With no reader and
    no deadline this returns empty facts — i.e. every claim comes back unknown, which is the safe
    default for a checker: it can only ever go quiet, never accuse.
    """
    today = _today(now)
    resolved: dict[str, object] = {}
    for kind, cls in (("daf_yomi", DafYomiInfo), ("parsha", ParshaInfo)):
        if load_cached is not None:
            try:
                raw = load_cached(kind, cache_key(kind, today))
            except Exception:  # noqa: BLE001 — a cache miss and a broken cache are the same to us
                raw = None
            if raw:
                try:
                    resolved[kind] = cls(**json.loads(raw))
                    continue
                except Exception:  # noqa: BLE001 — a malformed row must not fail the answer
                    pass
        if network_deadline_s > 0:
            from chavruta.calendar import sefaria_calendar
            fetch = (sefaria_calendar.resolve_daf_yomi if kind == "daf_yomi"
                     else sefaria_calendar.resolve_parsha)
            value = _bounded(fetch, network_deadline_s)
            if value is not None:
                resolved[kind] = value
    return CalendarFacts(daf=resolved.get("daf_yomi"), parsha=resolved.get("parsha"))
