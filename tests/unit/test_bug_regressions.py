"""Regression gate for the Tier 0–2 audit fixes (2026-07).

Every test here pins a specific bug that was fixed, so a future refactor can't silently
re-introduce it. All are deterministic — pure heuristics + registry, no Qdrant and no LLM.
Grouped by the layer they exercise: intent router, corpus registry, and the api lesson
helpers (audience / clarify-answer detection).
"""

from __future__ import annotations

import pytest

from chavruta.corpus.registry import default_registry
from chavruta.corpus.schema import Intent, Query
from chavruta.intents.router import (
    Router,
    detect_commentators,
    detect_intent,
    detect_requested_works,
)


# ── Tier 0-C: whole-word alias matching (COMMENTATOR / WORK) ──────────────────────
# Bug: a bare substring test fired 'רשי' inside 'מפרשים' / 'שרשי', and 'משנה' inside
# 'משנה תורה' / 'משנה ברורה'. Fixed with word-boundary matching + a one-hop prefix class
# that deliberately EXCLUDES ש (so 'שרשי' can't reach 'רשי').

@pytest.mark.parametrize("text", [
    "מה שרשי המילה הזאת",        # שרשי (roots) must NOT match rashi
    "לפי כל המפרשים על הפסוק",   # מפרשים (commentators) contains 'רשי' — must NOT match
    "פרשת השבוע",                # פרש… — must NOT match
])
def test_rashi_not_falsely_detected(text):
    assert "rashi" not in detect_commentators(text)


@pytest.mark.parametrize("text", [
    'מה אומר רש"י כאן',           # bare
    "מה אומר רשי כאן",           # no gershayim
    'ולרש"י יש פירוש אחר',        # two stacked one-letter prefixes ו+ל
    'לפי הרש"י',                  # ה prefix
])
def test_rashi_detected_with_prefixes(text):
    assert "rashi" in detect_commentators(text)


def test_mishneh_torah_not_tagged_as_mishnah():
    """'משנה תורה' is the Rambam's code, not the Mishnah — the bare 'משנה' work must drop."""
    works = detect_requested_works("מה פוסק הרמב\"ם במשנה תורה")
    assert "mishneh_torah" in works
    assert "mishnah" not in works


def test_mishnah_berurah_not_tagged_as_mishnah():
    works = detect_requested_works("מה כותב המשנה ברורה על הלכות שבת")
    assert "mishnah_berurah" in works
    assert "mishnah" not in works


def test_plain_mishnah_still_detected():
    assert "mishnah" in detect_requested_works("מה אומרת המשנה על זמן קריאת שמע")


def test_masechet_does_not_force_mishnah_work():
    """'מסכת' was removed from the Mishnah aliases — a Talmud tractate is not the Mishnah."""
    assert "mishnah" not in detect_requested_works("מה הדין במסכת בבא מציעא")


# ── Tier 0-C2: registry knows the loaded categories + their aliases ───────────────
# Bug: the registry only knew 'tanakh', so has('talmud') was False and honest-refusal logic
# for genuinely-unloaded works couldn't tell a loaded corpus from a missing one.

@pytest.mark.parametrize("cat", [
    "tanakh", "mishnah", "talmud_bavli", "halacha", "responsa", "midrash", "kabbalah",
])
def test_registry_has_loaded_categories(cat):
    assert default_registry().has(cat)


@pytest.mark.parametrize("alias,canonical", [
    ("talmud", "talmud_bavli"),
    ("shulchan_aruch", "halacha"),
    ("mishneh_torah", "halacha"),
    ("zohar", "kabbalah"),
])
def test_registry_resolves_aliases(alias, canonical):
    r = default_registry()
    assert r.has(alias) and r.has(canonical)


def test_registry_rejects_unloaded_work():
    """A genuinely out-of-corpus modern work must stay unknown → honest-refusal path fires."""
    assert not default_registry().has("modern_torah")


# ── Tier 0: halacha intent tightened ─────────────────────────────────────────────
# Bug: bare 'מותר'/'אסור'/'הלכה' over-triggered the heavy responsa machine on ordinary
# narrative questions. Now requires an interrogative / pesak framing.

@pytest.mark.parametrize("text", [
    "מה אסור לפרעה לעשות במצרים",     # narrative 'אסור', not a halachic query
    "מדוע מותר לעם ישראל לצאת",        # narrative 'מותר'
    "מה ההלכות שלמד משה בסיני",        # mentions הלכות, not a ruling question
])
def test_narrative_not_routed_to_halacha(text):
    assert detect_intent(text, 0) is not Intent.HALACHA


@pytest.mark.parametrize("text", [
    "האם מותר לאכול בשר עוף בחלב",
    "האם אסור לטלטל מוקצה בשבת",
    "מה הדין בהלכות מוקצה",
    "מהי ההלכה למעשה בברכת שהחיינו",
])
def test_genuine_ruling_routed_to_halacha(text):
    assert detect_intent(text, 0) is Intent.HALACHA


# ── Router-level: 'shut'/responsa question still surfaces the responsa work ───────

def test_router_responsa_work_detected():
    q = Router().route(Query(text='מה כתוב בשו"ת על השאלה הזאת'))
    assert q.requested_works and "responsa" in q.requested_works


# ── api lesson helpers: audience / grade-band / clarify-answer detection ──────────
# These live in app/api.py; importing it is cheap (no eager pipeline/embedder build).
# Bug set: (a) the plural 'כיתות ד–ו' clarify-answer was read as a fresh topic because the
# grade range was consumed before the range-strip; (b) English grade/school phrasing wasn't
# detected; (c) a real topic must NOT be mistaken for a clarify-answer.

api = pytest.importorskip("app.api")


@pytest.mark.parametrize("text", [
    "לכיתות ד–ו",          # plural + range — the exact case that regressed
    "כיתה ה",
    "ד",                    # a lone grade letter
    "grades 4-6",
    "high school",
])
def test_clarify_answer_recognised(text):
    assert api._is_clarify_answer(text) is True


@pytest.mark.parametrize("text", [
    "הלכות שבת",            # a real topic, not a clarify-answer
    "שניים אוחזין בטלית",
    "the laws of Shabbat",
    "the dispute between Rashi and Ramban",
])
def test_real_topic_not_a_clarify_answer(text):
    assert api._is_clarify_answer(text) is False


@pytest.mark.parametrize("text,band", [
    ("שיעור לכיתה ב", "a-c"),
    ("שיעור לכיתה ה", "d-f"),
    ("שיעור לכיתה ח", "g-i"),
    ("שיעור לכיתה יא", "j-l"),
])
def test_grade_band_detection(text, band):
    assert api._detect_band(text) == band


@pytest.mark.parametrize("text", [
    "prepare a lesson for 5th grade",
    "a shiur for high school students",
    "בית ספר יסודי",
])
def test_school_audience_detected(text):
    assert api._detect_school(text)
