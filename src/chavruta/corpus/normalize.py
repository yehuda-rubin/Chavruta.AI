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
