"""Landmark / indirect-reference resolution (Phase 2, spec 002-query-understanding).

Maps well-known *indirect* phrases to concrete corpus refs so questions that never
name a verse explicitly still anchor:

    "מה המחלוקת בין רש\"י לרמב\"ן בפסוק הראשון בתורה?"  →  named_refs = ["Genesis.1.1"]

Two layers: a curated absolute map (famous passages) and relative patterns
("הפסוק הראשון ב<ספר>", "הדף הראשון ב<מסכת>"). Pure, offline, data-extendable.
"""

from __future__ import annotations

import re

from chavruta.intents.hebrew_refs import HE_BOOKS, HE_TRACTATES, _book_alt

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

    for m in _FIRST_VERSE_RE.finditer(text):
        add(f"{HE_BOOKS[m.group('book')]}.1.1")

    for m in _FIRST_DAF_RE.finditer(text):
        add(f"{HE_TRACTATES[m.group('tractate')]}.2a")

    return refs
