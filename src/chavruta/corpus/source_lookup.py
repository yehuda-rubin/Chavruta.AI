"""Turn a short typed citation into a reader reference: "בראשית א א", "בראשית פרק א פסוק ג",
"ברכות ב ע״ב", "תהילים קיט", "משנה ברכות ב ג".

This is the library's *source* search — distinct from content search (full text). It differs from
intents/hebrew_refs.py, which finds citations inside free prose and is therefore strict (a bare
"ברכות ב" must not match inside a sentence). Here the whole query is the citation, so after a
recognised book name everything left is read as numbers, bare Hebrew letters included ("קיט" = 119).

Pure functions over the catalogue — no database. The caller verifies that a candidate exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from chavruta.intents.hebrew_refs import HE_BOOKS, HE_TRACTATES, gematria

_NIQQUD = re.compile(r"[֑-ׇ]")
_QUOTES = re.compile(r"[׳״\"'`’‘“”]")
_SEPS = re.compile(r"[\s,;:.\-_/()]+")
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")

# Words that only label a number ("פרק א", "דף ב", "סימן רסג"): dropped, never read as a name.
_MAX_NUMERAL_LETTERS = 4
_AMUD = {"עא": "a", "עב": "b"}


def fold(s: str) -> str:
    """Compare-key for Hebrew/English text: no niqqud, quotes or punctuation; final letters unified."""
    s = _NIQQUD.sub("", s)
    s = _QUOTES.sub("", s)
    s = _SEPS.sub(" ", s).strip().lower()
    return s.translate(_FINALS)


# Compared after fold(), so final letters are unified ("דף" → "דפ").
_LABELS = {fold(w) for w in ("פרק", "פסוק", "פס", "דף", "עמוד", "סימן", "סעיף", "הלכה", "משנה", "פרשה", "מסכת", "ספר")}


@dataclass(frozen=True)
class Source:
    """A parsed citation. `ref` opens the unit in the reader, `target` (optional) is the exact segment
    to scroll to inside it; both are in the forms /reader/unit already accepts."""
    book_en: str
    book_he: str
    ref: str                 # unit: 'Genesis.1', 'Berakhot.2a', 'Mishnah_Berakhot.2'
    target: str              # segment: 'Genesis 1:3' ('' when the citation names the whole unit)
    nums: tuple[int, ...]


class SourceIndex:
    """Hebrew names → English titles, built once from the library catalogue plus the alias tables."""

    def __init__(self, books: list[dict]):
        self.names: dict[str, tuple[str, str]] = {}           # folded Hebrew name → (title_en, title_he)
        by_en = {b["title_en"]: b["title_he"] for b in books}
        for b in books:
            self.names.setdefault(fold(b["title_he"]), (b["title_en"], b["title_he"]))
        # Spelling variants (תהלים/תהילים, שמואל א…) and tractate names, kept only if the book exists.
        for he, en in {**HE_BOOKS, **HE_TRACTATES}.items():
            if en in by_en:
                self.names.setdefault(fold(he), (en, by_en[en]))
        self.talmud = {en for en in HE_TRACTATES.values() if en in by_en}
        self.longest = max((len(k.split()) for k in self.names), default=1)


def _numeral(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    if len(token) <= _MAX_NUMERAL_LETTERS:
        return gematria(token)
    return None


def parse(query: str, index: SourceIndex) -> list[Source]:
    """Citations the query could mean, best first; [] when it does not start with a known book name
    or names no number (a bare title is the book search's job, not this one's)."""
    tokens = fold(query).split()
    if not tokens:
        return []

    # Longest known name at the start of the query wins ("שמואל א" before "שמואל").
    found = None
    for k in range(min(index.longest, len(tokens)), 0, -1):
        hit = index.names.get(" ".join(tokens[:k]))
        if hit:
            found = (hit, tokens[k:])
            break
    if not found:
        return []
    (book_en, book_he), rest = found

    nums: list[int] = []
    amud = ""
    for tok in rest:
        if tok in _LABELS:
            continue
        if tok in _AMUD:
            amud = _AMUD[tok]
            continue
        n = _numeral(tok)
        if n is None:
            return []                   # a word after the book name: not a citation
        nums.append(n)
    if not nums:
        return []

    stem = book_en.replace(" ", "_")
    if book_en in index.talmud:
        daf = nums[0]
        side = amud or ("b" if len(nums) > 1 and nums[1] == 2 else "a")
        return [Source(book_en, book_he, f"{stem}.{daf}{side}", "", (daf,))]

    unit = f"{stem}.{nums[0]}"
    if len(nums) == 1:
        return [Source(book_en, book_he, unit, "", (nums[0],))]
    return [Source(book_en, book_he, unit, f"{book_en} " + ":".join(map(str, nums)), tuple(nums))]
