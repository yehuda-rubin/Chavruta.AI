"""Hebrew text normalisation for nikud/ktiv-insensitive lexical search.

The corpus stores fully-vocalised text ("שְׁנַיִם אוֹחֲזִין"), but users type plain,
plene Hebrew ("שניים אוחזין"). The two never match on the sparse/lexical channel —
the nikud breaks tokenisation and the ktiv differs (שְׁנַיִם vs שניים). This module
produces a single normalised representation applied to BOTH sides so they coincide:

    "שְׁנַיִם אוֹחֲזִין בְּטַלִּית"  ─┐
                                    ├─ normalize_he ─→  "שנים אוחזין בטלית"
    "שניים אוחזין בטלית"          ─┘

Pure, offline, deterministic (Principle II). Display still uses the vocalised text;
only the search representation is normalised.
"""

from __future__ import annotations

import re
import unicodedata

# Hebrew punctuation that should not survive into a search token (maqaf joins words;
# geresh/gershayim mark numerals/abbreviations).
_HE_PUNCT = {
    "־",  # maqaf  ־
    "׀",  # paseq  ׀
    "׃",  # sof pasuq ׃
    "׆",  # nun hafukha
    "׳",  # geresh ׳
    "״",  # gershayim ״
}
_ASCII_PUNCT = set("'\"`")

# Word-final letters → their medial form, so position never blocks a match.
_FINALS = {"ך": "כ", "ם": "מ", "ן": "נ",
           "ף": "פ", "ץ": "צ"}


def normalize_he(text: str) -> str:
    """Nikud/ktiv-insensitive search form of `text`.

    Strips nikud + cantillation (Unicode combining marks), drops Hebrew/ASCII
    punctuation, folds final letters, collapses plene doublings (יי→י, וו→ו) so
    ktiv male/haser coincide, and squeezes whitespace.
    """
    if not text:
        return ""
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch):           # nikud + te'amim
            continue
        if ch in _HE_PUNCT or ch in _ASCII_PUNCT:
            continue
        out.append(_FINALS.get(ch, ch))
    s = "".join(out)
    # Fold ktiv male/haser: doubled yod/vav → single (applied to both query & corpus).
    while "יי" in s:
        s = s.replace("יי", "י")
    while "וו" in s:
        s = s.replace("וו", "ו")
    return " ".join(s.split()).lower()


# ── The reverent spelling ─────────────────────────────────────────────────────────────────────
# Observant Hebrew writers substitute ק for ה in the divine name outside of prayer and study —
# אלוקים for אלוהים, חלק אלוק ממעל for חלק אלוה ממעל. The corpus, being the texts themselves,
# always carries the real spelling. So the single most reverent habit in the language makes a
# user's words miss the very pasuk they are quoting.
#
# Measured on the live corpus, 2026-08-14, for a real question ("מה המקור לכך שהנשמה היא חלק
# אלוק ממעל?"):
#
#     "חלק אלוק ממעל"  → Job 31:2 not in the top 10
#     "חלק אלוה ממעל"  → Job 31:2 at rank 2
#
# One letter. The pasuk was in the corpus the whole time, and the user was told there was no
# source for a phrase that is a verbatim quotation of it.
#
# Anchored to the אל- stem with a word boundary, so ordinary words are untouched: "חלק" has no
# aleph, "צדק"/"חוק"/"רק" never reach the pattern. Only the ק in a word that is already the
# divine name is moved, and only where a ה belongs.
_REVERENT_RE = re.compile(r"(?<![א-ת])([בכלמשוהד]?)(אלו?)ק(ים|י|ינו|יכם|יהם|יך)?(?![א-ת])")


def deuphemize_he(text: str) -> str:
    """Rewrite the reverent divine-name spelling to the one the sources actually use.

    For SEARCH only — never for display. What a user chose to write is theirs, and rewriting it
    back at them would be both presumptuous and, to many readers, offensive. This exists so the
    query and the corpus can meet, nothing more.
    """
    if not text or "ק" not in text:
        return text or ""
    return _REVERENT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}ה{m.group(3) or ''}", text)


# ── Quotation windows ─────────────────────────────────────────────────────────────────────────
# The words a question is BUILT from, as opposed to the words it is ABOUT. Asking "what is the
# source for X" wraps X in a frame, and the frame is what a dense embedding spends its budget on.
_FRAME_WORDS = frozenset("""
מה מהו מהי המקור מקור מקורות לכך כך על של את זה זו הוא היא הם הן אני לי יש אין אם האם
למה מדוע איפה היכן מתי איך כיצד כתוב נאמר מובא אומר אומרת מניין מנין רוצה אשמח תוכל
ה ו ב ל מ ש כ אבל גם רק כל לא כן עם בין אחרי לפני זאת אלה
""".split())


def quote_windows(text: str, *, min_words: int = 3, max_words: int = 5,
                  limit: int = 4) -> list[str]:
    """Spans of `text` that might be a quotation, densest in content words first.

    A user quoting a pasuk inside a sentence does not get the pasuk back: measured on the live
    corpus 2026-08-14, "חלק אלוה ממעל" puts Iyov 31:2 at rank 2, while the same three words inside
    "מה המקור לכך שהנשמה היא חלק אלוה ממעל?" put it nowhere in the top ten. Even adding ONE word —
    "הנשמה חלק אלוה ממעל" — loses it. The quotation is not diluted by the frame so much as drowned
    by it, and no amount of re-ranking helps because the pasuk is never a candidate.

    So the phrase is searched on its own, as a floor. Windows are ranked by how many of their words
    are not question scaffolding, which is what picks "חלק אלוה ממעל" out of that sentence: the
    frame words carry no weight, and the three that remain are all content.

    `limit` is a cost bound, not a quality choice — every window costs a search, and they are
    embedded in ONE batch (see HybridRetriever.retrieve) because embedding is what actually costs.
    """
    words = [w for w in (text or "").split() if w]
    if len(words) < min_words:
        return []
    seen: set[str] = set()
    scored: list[tuple[int, int, str]] = []
    for size in range(min_words, max_words + 1):
        for i in range(len(words) - size + 1):
            window = words[i:i + size]
            phrase = " ".join(window).strip(" ?!.,:;")
            if not phrase or phrase in seen:
                continue
            content = sum(1 for w in window if w.strip("?!.,:;־") not in _FRAME_WORDS)
            if content < min_words:            # mostly scaffolding — not a quotation
                continue
            seen.add(phrase)
            # Densest first; among equals prefer the SHORTER span, since the measurement says a
            # tight phrase reaches the source and a looser one does not.
            scored.append((-content, size, phrase))
    scored.sort()
    return [p for _, _, p in scored[:limit]]
