"""Landmark / indirect-reference resolution (Phase 2, spec 002-query-understanding).

Maps well-known *indirect* phrases to concrete corpus refs so questions that never
name a verse explicitly still anchor:

    "מה המחלוקת בין רש\"י לרמב\"ן בפסוק הראשון בתורה?"  →  named_refs = ["Genesis.1.1"]

Two layers: a curated absolute map (famous passages) and relative patterns
("הפסוק הראשון ב<ספר>", "הדף הראשון ב<מסכת>"). Pure, offline, data-extendable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from chavruta.intents.hebrew_refs import HE_BOOKS, HE_TRACTATES, _book_alt, gematria

# Talmud perek → opening ref in the CORPUS format (built from Sefaria by
# scripts/build_talmud_perek_index.py). {English tractate: {"he":…, "perakim":[ref per perek]}}.
try:
    _PEREK_INDEX = json.loads(
        (Path(__file__).parent / "data" / "talmud_perek_daf.json").read_text(encoding="utf-8"))
except Exception:
    _PEREK_INDEX = {}

# Hebrew ordinal words → number (perek names). Higher perakim are addressed by gematria/digits.
_HE_ORDINALS = {
    "ראשון": 1, "שני": 2, "שלישי": 3, "רביעי": 4, "חמישי": 5, "שישי": 6, "ששי": 6,
    "שביעי": 7, "שמיני": 8, "תשיעי": 9, "עשירי": 10,
}
_ORD_ALT = "|".join(sorted(_HE_ORDINALS, key=len, reverse=True))


def _perek_num(token: str) -> int | None:
    token = token.strip()
    if token in _HE_ORDINALS:
        return _HE_ORDINALS[token]
    core = token.rstrip("'׳\"״")
    if core.isdigit():
        return int(core)
    # A Hebrew numeral counts only if it's a SINGLE letter ('ג') or carries a geresh/gershayim
    # ('ג׳', 'י״א'); a bare multi-letter token is rejected — otherwise demonstratives like 'זה'/'הוא'
    # ('פרק זה' = "this chapter") gematria-sum to a bogus perek number and anchor the wrong daf.
    marked = any(c in token for c in "'׳\"״")
    if core and all("א" <= c <= "ת" for c in core) and (len(core) == 1 or marked):
        return gematria(core) or None
    return None

# ── Absolute landmarks: famous passages with a fixed ref ─────────────────────────
ABSOLUTE_LANDMARKS: dict[str, str] = {
    "הפסוק הראשון בתורה": "Genesis.1.1",
    "הפסוק הראשון של התורה": "Genesis.1.1",
    "פסוק ראשון בתורה": "Genesis.1.1",
    "תחילת התורה": "Genesis.1.1",
    "ריש התורה": "Genesis.1.1",
    "בראשית ברא": "Genesis.1.1",
    "בריאת העולם": "Genesis.1.1",
    "מעשה בראשית": "Genesis.1",
    "עשרת הדיברות": "Exodus.20",
    "עשרת הדברות": "Exodus.20",
    "קריאת שמע": "Deuteronomy.6.4",
    "שמע ישראל": "Deuteronomy.6.4",
    "ואהבת לרעך כמוך": "Leviticus.19.18",
    "פרשת העקדה": "Genesis.22",
    "עקדת יצחק": "Genesis.22",
    "שירת הים": "Exodus.15",
    "ברכת כהנים": "Numbers.6.24",
}

# English famous-passage map — English queries otherwise ride entirely on cross-lingual dense (which
# buries the terse Hebrew base verse). Matched case-insensitively as a substring. Extendable as data.
# Keys are matched at WORD BOUNDARIES (not raw substring) and are kept specific — a bare "shema"
# collides with the name "Shemaiah", "in the beginning" is a common discourse phrase, etc.
ENGLISH_LANDMARKS: dict[str, str] = {
    "shema yisrael": "Deuteronomy.6.4", "the shema": "Deuteronomy.6.4",
    "ten commandments": "Exodus.20", "decalogue": "Exodus.20",
    "binding of isaac": "Genesis.22", "akedah": "Genesis.22", "the akeda": "Genesis.22",
    "creation of the world": "Genesis.1.1", "first verse of the torah": "Genesis.1.1",
    "love your neighbor": "Leviticus.19.18", "love your fellow": "Leviticus.19.18",
    "song of the sea": "Exodus.15", "priestly blessing": "Numbers.6.24",
    "garden of eden": "Genesis.2", "tower of babel": "Genesis.11",
    "the golden calf": "Exodus.32",
}
_EN_LANDMARK_RE = {p: re.compile(rf"\b{re.escape(p)}\b") for p in ENGLISH_LANDMARKS}

# ── Relative landmarks: pattern → resolver ───────────────────────────────────────
_HE_BOOK_ALT = _book_alt(HE_BOOKS)
_HE_TRACTATE_ALT = _book_alt(HE_TRACTATES)

# "the first verse of the Torah", tolerant of ה/ב prefixes: "בפסוק הראשון בתורה",
# "הפסוק הראשון של התורה", "תחילת התורה", "ריש התורה".
_TORAH_FIRST_RE = re.compile(
    r"(?:[הב]?פסוק\s+(?:ה)?ראשון\s+(?:ב|של\s+)?(?:ה)?(?:תורה|חומש)"
    r"|(?:ב?תחילת|ריש)\s+(?:ה)?(?:תורה|חומש))"
)

# "הפסוק הראשון בבראשית" / "הפסוק הראשון בספר שמות" / "תחילת ספר ויקרא"
_FIRST_VERSE_RE = re.compile(
    rf"(?:[הב]?פסוק\s+(?:ה)?ראשון|פסוק\s+ראשון|ב?תחילת|ריש|בתחילת)\s+"
    rf"(?:ספר\s+|ב|של\s+|בספר\s+)?(?P<book>{_HE_BOOK_ALT})"
)

# "הדף הראשון בבבא מציעא" → tractate opens at daf 2a
_FIRST_DAF_RE = re.compile(
    rf"(?:הדף\s+הראשון|דף\s+ראשון|תחילת\s+מסכת)\s+"
    rf"(?:מסכת\s+|ב|של\s+)?(?P<tractate>{_HE_TRACTATE_ALT})"
)

# "פרק שלישי בסנהדרין" / "פרק ג' בבבא מציעא" / "פרק 3 בגיטין" (prefix-tolerant: "הדף הראשון בפרק…").
_PEREK_RE = re.compile(
    rf"פרק\s+(?P<ord>{_ORD_ALT}|[א-ת]{{1,3}}['׳]?|\d+)\s+"
    rf"(?:ב|של\s+|ב?מסכת\s+|ד)?(?P<tractate>{_HE_TRACTATE_ALT})"
)


def resolve_landmarks(text: str) -> list[str]:
    """All landmark refs found in the question, de-duplicated, order-preserving."""
    refs: list[str] = []

    def add(ref: str) -> None:
        if ref not in refs:
            refs.append(ref)

    # "first verse of the Torah" (prefix-tolerant) → Genesis.1.1
    if _TORAH_FIRST_RE.search(text):
        add("Genesis.1.1")

    # Absolute phrases (longest first so "הפסוק הראשון בתורה" beats "תחילת התורה" overlap)
    for phrase in sorted(ABSOLUTE_LANDMARKS, key=len, reverse=True):
        if phrase in text:
            add(ABSOLUTE_LANDMARKS[phrase])

    # English famous passages — WORD-BOUNDARY match (case-insensitive), longest first for specificity.
    low = text.lower()
    for phrase in sorted(ENGLISH_LANDMARKS, key=len, reverse=True):
        if _EN_LANDMARK_RE[phrase].search(low):
            add(ENGLISH_LANDMARKS[phrase])

    for m in _FIRST_VERSE_RE.finditer(text):
        add(f"{HE_BOOKS[m.group('book')]}.1.1")

    # First daf of a tractate → its opening daf 2a (amud form; the anchoring path converts it to the
    # corpus amud-linear ref via with_ref_variants).
    for m in _FIRST_DAF_RE.finditer(text):
        add(f"{HE_TRACTATES[m.group('tractate')]}.2a")

    # "פרק <ordinal> ב<מסכת>" → the perek's opening ref from the Sefaria-built index.
    for m in _PEREK_RE.finditer(text):
        tractate = HE_TRACTATES.get(m.group("tractate"))
        n = _perek_num(m.group("ord"))
        perak = (_PEREK_INDEX.get(tractate) or {}).get("perakim") or []
        if tractate and n and 1 <= n <= len(perak) and perak[n - 1]:
            add(perak[n - 1])

    return refs
