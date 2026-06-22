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
