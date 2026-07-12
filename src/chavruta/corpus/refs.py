"""Canonical ref normalization — the single join key between the link graph and the corpus.

Our stored refs are inconsistent: base texts use dotted/underscored Sefaria refs
(``Prisha,_Yoreh_De'ah.335.19.1``), while commentary chunks prepend a Hebrew label
(``רש"י on Rashi on Chullin 11.3.1``) and keep the clean Sefaria ref in ``anchor_ref``
(``Rashi on Chullin 11.3.1``). Sefaria's Links use yet another spacing (``Radak on Isaiah.53.1``).

`canonical_ref` collapses all of these to one separator-agnostic key so that a link endpoint and
a corpus chunk that denote the SAME text produce the SAME string — regardless of whether the
original used ``_``, ``.``, ``:`` or a space, and regardless of a Hebrew label prefix. Both the
corpus indexer and the (external) link-graph builder MUST use this function.
"""

from __future__ import annotations

import re

_HEB = re.compile(r"[֐-׿]")    # any Hebrew letter → the ref carries a Hebrew label prefix
_SEP = re.compile(r"[_.,:;]+")           # Sefaria depth/segment separators, treated as equivalent
_WS = re.compile(r"\s+")


def canon_corpus_ref(ref: str | None) -> str:
    """Exact router→corpus ref form for an EXACT Qdrant `ref` lookup — distinct from `canonical_ref`
    (a loose lowercased join key). The router emits dotted refs ('Genesis.1.1'), but the corpus stores
    Tanakh/Talmud/Mishnah base texts with a space after the book name ('Genesis 1.1', 'Kiddushin 82.4',
    'Mishnah Sukkah 3.5'). Convert only the book↔chapter dot — a dot preceded by a non-digit and
    followed by a digit — to a space, preserving case and the chapter.verse dot. Already-spaced refs
    pass through unchanged. Verified against the live collection across tanakh/mishnah/talmud_bavli."""
    if not ref:
        return ""
    return re.sub(r"(?<=\D)\.(?=\d)", " ", ref, count=1)


# A Talmud daf in amud form: 'Bava Metzia 2a', 'Sanhedrin 23b'. The corpus stores Talmud base texts
# with a FLAT amud-linear number instead of the amud letter: N = 2·daf − 1 (amud a) / 2·daf (amud b)
# — verified against the live collection (2a→3, 23a→45). So an amud ref anchors on 'Tractate N.1'.
_AMUD_RE = re.compile(r"^(?P<t>.+?)[ .](?P<daf>\d+)(?P<amud>[ab])$")


def daf_amud_to_corpus_n(daf: int, amud: str) -> int:
    """The corpus's flat amud-linear daf number: N = 2·daf − 1 (amud a) / 2·daf (amud b). This IS the
    corpus's Talmud storage convention — the single source of truth (the offline perek-index builder
    imports it too, so runtime and index never drift)."""
    return 2 * int(daf) - (1 if amud == "a" else 0)


def _amud_to_corpus(ref: str) -> str | None:
    m = _AMUD_RE.match(ref or "")
    # Only a bare tractate name + daf + amud is Talmud ('Sanhedrin 23a'). A digit in the name means a
    # volume-numbered work like the Zohar ('Zohar 1.15a') that is NOT amud-linear — don't fabricate a ref.
    if not m or any(ch.isdigit() for ch in m.group("t")):
        return None
    return f"{m.group('t')} {daf_amud_to_corpus_n(int(m.group('daf')), m.group('amud'))}.1"


def with_ref_variants(refs) -> list[str]:
    """The original + corpus-canonical form of each ref (deduped, order-preserving), so an exact
    `fetch_by_refs` lookup matches whichever spelling the stored `ref`/`anchor_ref` uses:
      • dotted↔space book boundary ('Genesis.1.1' ↔ 'Genesis 1.1'),
      • chapter-level → opening verse ('Exodus.20' → 'Exodus 20.1'),
      • Talmud amud form → the corpus amud-linear opening ref ('Sanhedrin.23a' → 'Sanhedrin 45.1')."""
    out: list[str] = []

    def _add(v: str) -> None:
        if v and v not in out:
            out.append(v)

    for r in refs or []:
        _add(r)
        canon = canon_corpus_ref(r)
        _add(canon)
        amud = _amud_to_corpus(canon)              # Talmud daf → corpus amud-linear opening segment
        if amud:
            _add(amud)
        elif re.fullmatch(r".+\s\d+", canon):      # chapter-level (no verse) → opening verse
            _add(canon + ".1")
    return out


def canonical_ref(s: str | None) -> str:
    """Loose, separator-agnostic join key for a Sefaria-style ref (empty string for falsy input)."""
    if not s:
        return ""
    s = s.strip()
    # Commentary chunks store 'רש"י on Rashi on Chullin 11.3.1' — drop the Hebrew label up to the
    # first ' on ' so only the clean English Sefaria ref remains. A purely-Hebrew ref with no ' on '
    # is KEPT (normalized) — stripping all its Hebrew would collapse distinct refs to the same empty
    # skeleton (a silent over-merge / empty join key).
    if _HEB.search(s):
        i = s.find(" on ")
        if i != -1:
            s = s[i + 4:]
    s = _SEP.sub(" ", s)                  # _ . , : ; → space
    s = _WS.sub(" ", s).strip().lower()
    return s
