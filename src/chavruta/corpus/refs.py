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


def _to_sefaria_ref(ref: str) -> str:
    """The Sefaria API spelling the COMMERCIAL corpus stores: spaces inside the book name become
    underscores and every depth separator becomes a dot — 'Bava Metzia 3.1' → 'Bava_Metzia.3.1',
    'Exodus 20' → 'Exodus.20', 'Mishnah Sukkah 3.5' → 'Mishnah_Sukkah.3.5'. (The older space-form
    corpus stores 'Bava Metzia 3.1'; emitting BOTH lets one ref resolve against either.)"""
    ref = (ref or "").strip()
    m = re.match(r"^(.*?)[ ._](\d.*)$", ref)       # book (up to the first digit-led segment), tail
    if not m:
        return ref.replace(" ", "_")
    book = m.group(1).replace(" ", "_")
    tail = re.sub(r"[ :._]+", ".", m.group(2))
    return f"{book}.{tail}"


def with_ref_variants(refs) -> list[str]:
    """Every stored spelling of each ref (deduped, order-preserving), so an EXACT `fetch_by_refs`
    lookup resolves regardless of which corpus format holds it — Qdrant matches the `ref` string
    literally, so the caller must supply the stored form. Covers BOTH corpora:
      • old space-form ('Genesis 1.1', 'Bava Metzia 3.1', 'Mishnah Sukkah 3.5'), and
      • commercial Sefaria underscore-dot form ('Genesis.1.1', 'Bava_Metzia.3.1', 'Mishnah_Sukkah.3.5');
    with the transforms:
      • dotted↔space book boundary ('Genesis.1.1' ↔ 'Genesis 1.1'),
      • chapter-level → opening verse ('Exodus.20' → 'Exodus 20.1' AND 'Exodus.20.1'),
      • Talmud amud → the amud-linear opening ref ('Sanhedrin.23a' → 'Sanhedrin 45.1' / 'Sanhedrin.45.1')."""
    out: list[str] = []

    def _add(v: str) -> None:
        if v and v not in out:
            out.append(v)

    for r in refs or []:
        _add(r)
        canon = canon_corpus_ref(r)
        _add(canon)
        amud = _amud_to_corpus(canon)              # Talmud daf → amud-linear opening segment
        if amud:
            _add(amud)                             # 'Bava Metzia 3.1'  (old space-form)
            _add(_to_sefaria_ref(amud))            # 'Bava_Metzia.3.1'  (commercial)
            continue
        sef = _to_sefaria_ref(canon)
        _add(sef)                                  # 'Exodus.20' / 'Mishnah_Sukkah.3.5'
        if re.fullmatch(r".+\s\d+", canon):        # chapter-level (no verse) → opening verse
            _add(canon + ".1")                     # 'Exodus 20.1'   (old space-form)
        if sef.count(".") == 1:                    # Book.Chapter (book carries no dots) → opening verse
            _add(sef + ".1")                       # 'Exodus.20.1'   (commercial)  ← the base-verse fix
    return out


# Sefaria names a commentary "<Commentator>_on_<Base>" — 'Rashi_on_Genesis.1.1.1',
# 'Kessef_Mishneh_on_Mishneh_Torah,_Prayer.12.17.4'. Match is CASE-SENSITIVE on purpose: title words
# are capitalised, so a lowercase '_on_' is the join and never a fragment of a name. Without that,
# 'Targum_Onkelos_on_Genesis' would split at 'Onkelos' and yield the commentator 'targum'.
_ON = "_on_"


def _slug(name: str) -> str:
    """The commentator-id form used everywhere else (corpus/sources/sefaria.py, router aliases)."""
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def commentator_from_ref(ref: str | None) -> str | None:
    """The commentator id a ref belongs to, or None for a base text.

        'Rashi_on_Genesis.1.1.1'                  -> 'rashi'
        'Or_HaChaim_on_Genesis.1.25.1'            -> 'or_hachaim'
        'Mizrachi_on_Rashi_on_Genesis.1.1.1'      -> 'mizrachi'   (supercommentary: FIRST author wins)
        'Genesis.1.1'                             -> None

    This exists because the commercial corpus was built without a `commentator_id` payload field,
    which the explain/compare intents filter on — so every "what does Rashi say here" question came
    back empty while Rashi sat in the index. The name is recoverable from the ref itself, so this is
    metadata that can be backfilled without re-embedding anything (see scripts/backfill_structure.py).
    """
    if not ref or _ON not in ref:
        return None
    return _slug(ref.split(_ON, 1)[0]) or None


def is_commentary_ref(ref: str | None) -> bool:
    """Whether a ref names a commentary rather than a base text."""
    return bool(ref) and _ON in ref


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
