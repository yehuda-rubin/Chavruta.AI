"""Hebrew reference detection (Phase 1, spec 002-query-understanding).

`router.detect_refs` only recognised English book names, so a Hebrew question
("בראשית א:א", "בבא מציעא ב׳ ע״א") never produced `named_refs` — and without an
anchor the retriever could not pull the verse + its commentaries. This module adds
Hebrew Tanakh + Talmud reference parsing, normalised to the corpus ref scheme
("Genesis.1.1", "Bava_Metzia.2a"). Pure, offline, deterministic (Principle II).
"""

from __future__ import annotations

import re

# ── Tanakh book names: Hebrew → corpus (English) id ─────────────────────────────
# Numbered books list their part-suffix form first so the longest match wins.
HE_BOOKS: dict[str, str] = {
    "בראשית": "Genesis", "שמות": "Exodus", "ויקרא": "Leviticus",
    "במדבר": "Numbers", "דברים": "Deuteronomy", "יהושע": "Joshua",
    "שופטים": "Judges",
    "שמואל א": "I Samuel", "שמואל ב": "II Samuel",
    "מלכים א": "I Kings", "מלכים ב": "II Kings",
    "ישעיהו": "Isaiah", "ישעיה": "Isaiah",
    "ירמיהו": "Jeremiah", "ירמיה": "Jeremiah",
    "יחזקאל": "Ezekiel", "הושע": "Hosea", "יואל": "Joel", "עמוס": "Amos",
    "עובדיה": "Obadiah", "יונה": "Jonah", "מיכה": "Micah", "נחום": "Nahum",
    "חבקוק": "Habakkuk", "צפניה": "Zephaniah", "חגי": "Haggai",
    "זכריה": "Zechariah", "מלאכי": "Malachi",
    "תהילים": "Psalms", "תהלים": "Psalms", "משלי": "Proverbs", "איוב": "Job",
    "שיר השירים": "Song of Songs", "רות": "Ruth", "איכה": "Lamentations",
    "קהלת": "Ecclesiastes", "אסתר": "Esther", "דניאל": "Daniel",
    "עזרא": "Ezra", "נחמיה": "Nehemiah",
    "דברי הימים א": "I Chronicles", "דברי הימים ב": "II Chronicles",
}

# ── Bavli tractate names: Hebrew → corpus (English) id ───────────────────────────
# Values use the corpus' textual ref format — SPACES, not underscores
# (the store holds e.g. "Bava Metzia.2a", so "Bava_Metzia" would never match).
HE_TRACTATES: dict[str, str] = {
    "ברכות": "Berakhot", "שבת": "Shabbat", "עירובין": "Eruvin", "פסחים": "Pesachim",
    "שקלים": "Shekalim", "יומא": "Yoma", "סוכה": "Sukkah", "ביצה": "Beitzah",
    "ראש השנה": "Rosh Hashanah", "תענית": "Taanit", "מגילה": "Megillah",
    "מועד קטן": "Moed Katan", "חגיגה": "Chagigah", "יבמות": "Yevamot",
    "כתובות": "Ketubot", "נדרים": "Nedarim", "נזיר": "Nazir", "סוטה": "Sotah",
    "גיטין": "Gittin", "קידושין": "Kiddushin",
    "בבא קמא": "Bava Kamma", "בבא מציעא": "Bava Metzia", "בבא בתרא": "Bava Batra",
    "סנהדרין": "Sanhedrin", "מכות": "Makkot", "שבועות": "Shevuot",
    "עבודה זרה": "Avodah Zarah", "הוריות": "Horayot", "זבחים": "Zevachim",
    "מנחות": "Menachot", "חולין": "Chullin", "בכורות": "Bekhorot",
    "ערכין": "Arakhin", "תמורה": "Temurah", "כריתות": "Keritot",
    "מעילה": "Meilah", "נדה": "Niddah",
}

# Hebrew letter → numeric value (gematria); includes final forms.
_GEMATRIA: dict[str, int] = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ך": 20, "ל": 30, "מ": 40, "ם": 40, "נ": 50, "ן": 50,
    "ס": 60, "ע": 70, "פ": 80, "ף": 80, "צ": 90, "ץ": 90,
    "ק": 100, "ר": 200, "ש": 300, "ת": 400,
}

# geresh ׳ / gershayim ״ and their ASCII look-alikes, stripped before gematria
_PUNCT = "׳״'\"`"
_HE_LETTERS = "".join(_GEMATRIA.keys())


def gematria(token: str) -> int | None:
    """Numeric value of a Hebrew-numeral token ('א'→1, 'ט״ו'→15, 'כא'→21).

    Returns None when the token is not a pure Hebrew-letter numeral.
    """
    core = "".join(ch for ch in token if ch not in _PUNCT)
    if not core or any(ch not in _GEMATRIA for ch in core):
        return None
    return sum(_GEMATRIA[ch] for ch in core)


_GERESH = "׳״'\"`"


def _num(token: str) -> int | None:
    """Parse a chapter/verse token → int, or None if it isn't a plausible numeral.

    Accepts: digits; a single Hebrew letter; or a multi-letter Hebrew numeral that
    carries a geresh/gershayim. Bare multi-letter Hebrew words (e.g. "ברא") are
    rejected so prose after a book name isn't misread as a chapter number.
    """
    raw = token.strip()
    core = "".join(ch for ch in raw if ch not in _PUNCT)
    if core.isdigit():
        return int(core)
    if not core or any(ch not in _GEMATRIA for ch in core):
        return None
    if len(core) == 1:
        return gematria(core)
    if any(g in raw for g in _GERESH):   # multi-letter numerals must be marked
        return gematria(core)
    return None


# A number token: digits, OR a *marked* Hebrew numeral (letters + a geresh/gershayim,
# e.g. "ב׳"=2, "י״ט"=19, "קי״ט"=119), OR a single Hebrew letter — but only at a word
# boundary (negative lookahead), so a word-initial letter like the "ע" in "על" or the
# book-name "שמות" is never misread as a chapter/verse number.
_MARK = re.escape(_PUNCT)
_NUM = (
    rf"(?:\d+|(?:[{_HE_LETTERS}]{{0,3}}[{_MARK}][{_HE_LETTERS}]?|[{_HE_LETTERS}])"
    rf"(?![{_HE_LETTERS}]))"
)

# Separators between book / chapter / verse: ":", ".", ",", whitespace, or the words פרק/פסוק.
_SEP = r"(?:\s*[:.,]\s*|\s+(?:פרק|פסוק)\s+|\s+)"

_AMUD = r"(?:ע[\"'״׳ ]?א|ע[\"'״׳ ]?ב|עמוד\s*[אב]|[.:])"   # amud aleph(a)/bet(b) marker
# Daf number: digits OR a Hebrew numeral. Unmarked multi-letter numerals (e.g. "נט"=59)
# ARE accepted here because the REQUIRED amud marker disambiguates "this is a daf number".
_DAF = rf"(?:\d+|[{_HE_LETTERS}]{{1,4}})"


def _daf_value(token: str) -> int | None:
    core = "".join(ch for ch in token if ch not in _PUNCT)
    if core.isdigit():
        return int(core)
    if core and all(ch in _GEMATRIA for ch in core):
        return sum(_GEMATRIA[ch] for ch in core)
    return None


def _book_alt(names) -> str:
    # Longest names first so "שמואל א" beats "שמואל", "בבא מציעא" beats nothing partial.
    ordered = sorted(names, key=len, reverse=True)
    return "|".join(re.escape(n) for n in ordered)


_TANAKH_RE = re.compile(
    rf"(?P<book>{_book_alt(HE_BOOKS)})"
    rf"(?:{_SEP}(?P<ch>{_NUM}))?"
    rf"(?:{_SEP}(?P<vs>{_NUM}))?"
)

# The amud marker is REQUIRED (so an unmarked daf number is unambiguous and prose like
# "ברכות טובות" never matches).
_TALMUD_RE = re.compile(
    rf"(?P<tractate>{_book_alt(HE_TRACTATES)})\s+(?:דף\s+)?"
    rf"(?P<daf>{_DAF})[{_MARK}]*\s*(?P<amud>{_AMUD})"
)


def detect_tanakh_refs(text: str) -> list[str]:
    """Hebrew Tanakh refs → 'Book.ch' or 'Book.ch.verse'.

    Requires a valid chapter number — a bare book mention in prose ("בראשית ברא…")
    does not anchor, avoiding false positives.
    """
    refs: list[str] = []
    for m in _TANAKH_RE.finditer(text):
        if not m.group("ch"):
            continue
        ch = _num(m.group("ch"))
        if ch is None:
            continue
        parts = [HE_BOOKS[m.group("book")], str(ch)]
        vs = _num(m.group("vs")) if m.group("vs") else None
        if vs is not None:
            parts.append(str(vs))
        ref = ".".join(parts)
        if ref not in refs:
            refs.append(ref)
    return refs


def detect_talmud_refs(text: str) -> list[str]:
    """Hebrew Talmud refs → 'Tractate.<daf><a|b>' (amud aleph default).

    Requires a valid daf number so a tractate named in prose does not anchor.
    """
    refs: list[str] = []
    for m in _TALMUD_RE.finditer(text):
        daf = _daf_value(m.group("daf"))
        if daf is None:
            continue
        amud_tok = m.group("amud")
        amud = "b" if ("ב" in amud_tok or ":" in amud_tok) else "a"
        ref = f"{HE_TRACTATES[m.group('tractate')]}.{daf}{amud}"
        if ref not in refs:
            refs.append(ref)
    return refs


def detect_hebrew_refs(text: str) -> list[str]:
    """All Hebrew references (Tanakh first, then Talmud), de-duplicated."""
    refs = detect_tanakh_refs(text)
    for r in detect_talmud_refs(text):
        if r not in refs:
            refs.append(r)
    return refs
