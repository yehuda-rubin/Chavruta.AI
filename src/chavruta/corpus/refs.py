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

import json
import re
from pathlib import Path

from chavruta.intents.hebrew_refs import HE_BOOKS, HE_TRACTATES

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
    metadata derived at READ time — there is no backfill script, and deliberately so: writing it
    to 2.4M on-disk points measured at ~5 points/sec. See docs/CORPUS.md §7.2b.
    """
    if not ref:
        return None
    if _ON not in ref:
        # A handful of works are filed as a plain prefix rather than a commentary ('Onkelos_Exodus.
        # 20.2'). Only the explicitly known ones are recognised — guessing from the first underscore
        # would rename base texts like 'Netinah_LaGer,_Genesis.1.1.2' after their own title.
        for cid in _TARGUM_PREFIXED:
            if ref.startswith(commentator_title(cid) + "_"):
                return cid
        return None
    return _slug(ref.split(_ON, 1)[0]) or None


def is_commentary_ref(ref: str | None) -> bool:
    """Whether a ref carries the '<Title>_on_<Base>' commentary form.

    Narrower than `commentator_from_ref`, which also names the prefix-filed targumim — those are
    stored as their own running text and the corpus files them as `unit_type: source`.
    """
    return bool(ref) and _ON in ref


# The Sefaria title behind a commentator id. Title-casing the slug is right for almost all of them
# ('metzudat_david' → 'Metzudat_David'); these are the ones whose capitalisation it gets wrong.
# Verified against the live collection 2026-07-27.
_TITLE_SPECIAL = {"or_hachaim": "Or_HaChaim", "ibn_ezra": "Ibn_Ezra"}

# Onkelos is not filed as a commentary at all: the corpus stores 'Onkelos_Genesis.1.1' — no '_on_'
# join and no trailing comment index, one segment per verse.
_TARGUM_PREFIXED = {"onkelos"}


def commentator_title(cid: str) -> str:
    """'or_hachaim' -> 'Or_HaChaim', 'metzudat_david' -> 'Metzudat_David'."""
    return _TITLE_SPECIAL.get(cid, "_".join(w.capitalize() for w in (cid or "").split("_")))


def commentary_refs(base_refs, commentator_ids, *, max_comments: int = 8) -> list[str]:
    """Exact refs for the named commentators ON the given base refs.

    The inverse of `commentator_from_ref`, and the reason it can be: Sefaria names a commentary
    '<Title>_on_<Base>.<k>', where k enumerates the comments on that one segment. Deriving the refs
    lets a "what does Rashi say here" question anchor by EXACT lookup — which the `ref` keyword index
    answers in milliseconds — rather than depending on the named commentator happening to surface in
    a semantic search. It is what makes named-commentator retrieval work at all on a corpus whose
    `commentator_id` and `anchor_ref` payload fields were never populated.

    Refs that do not exist simply return nothing from the store, so over-generating k is cheap and a
    commentator with no comment here stays honestly absent (Principle I).
    """
    out: list[str] = []
    seen = set()
    for base in base_refs or []:
        if " " in base:          # commercial underscore-dot form only; the space form has no commentaries
            continue
        for cid in commentator_ids or []:
            title = commentator_title(str(cid).lower())
            if str(cid).lower() in _TARGUM_PREFIXED:
                cands = [f"{title}_{base}"]
            else:
                cands = [f"{title}{_ON}{base}.{k}" for k in range(1, max_comments + 1)]
            for c in cands:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
    return out


# ── Licence attribution: which WORK a stored ref belongs to ───────────────────────────────────────
# Built once by scripts/build_license_table.py from the per-tier licenses.json the corpus build
# produced — the record of which edition was actually ingested, which is not the same question as
# which editions exist on Sefaria today.
_LICENSES_PATH = Path(__file__).with_name("data") / "licenses.json"
_licenses: dict[str, dict] | None = None
_titles_by_len: list[str] = []


def _load_licenses() -> dict[str, dict]:
    """Load once. A missing or unreadable table degrades to empty — never breaks a query."""
    global _licenses, _titles_by_len
    if _licenses is None:
        try:
            _licenses = json.loads(_LICENSES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _licenses = {}
        # Longest first, so 'Genesis Rabbah' is tested before 'Genesis'.
        _titles_by_len = sorted(_licenses, key=len, reverse=True)
    return _licenses


def work_title_for_ref(ref: str | None) -> str | None:
    """The Sefaria work title a stored ref belongs to, or None if the work is not in the table.

    Matched against the KNOWN TITLES rather than parsed out of the ref, because no rule over the
    string can do it. These two have the same shape and opposite answers:

        Guide_for_the_Perplexed,_Part_1.1.1             -> 'Guide for the Perplexed'
        Chafetz_Chaim_on_Sifra,_Behar,_Section_2.2.8    -> 'Chafetz Chaim on Sifra'

    'Part 1' and 'Section 2' are indistinguishable as text; only the title set knows where each name
    ends. It also handles names that end in a numeral ('Shoel uMeshiv Mahadura I') and names carrying
    commas or apostrophes, all of which defeat a "strip the trailing numbers" rule.

    The match must land on a segment boundary, or 'Genesis' would swallow 'Genesis Rabbah'.
    """
    if not ref:
        return None
    _load_licenses()
    flat = ref.replace("_", " ")
    for title in _titles_by_len:
        if flat == title or flat.startswith(title + ".") or flat.startswith(title + ",") \
                or flat.startswith(title + " "):
            return title
    return None


def license_for_ref(ref: str | None, lang: str = "he") -> tuple[str, str]:
    """(license, version_title) for a ref, per LANGUAGE — ('', '') when unknown.

    Rights are per edition, and a work can be Public Domain in Hebrew while its English translation
    is CC-BY, so the chunk's own language decides which side is read.
    """
    title = work_title_for_ref(ref)
    if not title:
        return "", ""
    entry = _load_licenses().get(title) or {}
    side = "en" if (lang or "he").lower().startswith("en") else "he"
    return entry.get(f"{side}_license", "") or "", entry.get(f"{side}_version", "") or ""


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


# ── Hebrew display names for citations ──────────────────────────────────────────────────────────
# The corpus stores every ref in Sefaria's English/transliterated spelling ('Genesis.1.1',
# 'Rashi_on_Genesis.1.1.1') — correct as a machine key, but a Hebrew-reading user sees a citation
# titled in English on every single source card. `hebrew_display_ref` gives a best-effort Hebrew
# rendering for the common cases (Tanakh, Mishnah, Talmud Bavli, and a curated set of classic
# commentators) and returns None for anything else, so the caller falls back to the original ref
# rather than a half-translated guess — an honest gap reads better than confidently wrong Hebrew
# (Principle I). Reuses the Hebrew↔English book/tractate tables already built for parsing Hebrew
# input refs (intents/hebrew_refs.py) instead of hand-duplicating them.
_BOOK_HE = {en: he for he, en in HE_BOOKS.items()}            # 'Genesis' -> 'בראשית'
_TRACTATE_HE = {en: he for he, en in HE_TRACTATES.items()}    # 'Sukkah' -> 'סוכה'

# Curated on purpose: only classic Rishonim/Acharonim whose Sefaria "<Title>_on_<base>" ref is known
# to point straight at a bare Tanakh/Talmud-Bavli ref or a 'Mishnah_<Tractate>' ref — both handled
# unambiguously below. Commentators on the Tosefta, Yerushalmi, Mishneh Torah, Tur/Shulchan Aruch,
# Midrash, or responsa are deliberately left out: their Sefaria base ref can look identical to a bare
# tractate name (e.g. a Tosefta commentary's base strips to 'Bava_Metzia.1.1', not 'Tosefta_Bava_
# Metzia...') which would make the daf/amud math below confidently wrong rather than absent — and
# wrong is worse than untranslated.
COMMENTATOR_HE: dict[str, str] = {
    # Tanakh
    "rashi": "רש\"י", "rashbam": "רשב\"ם", "ibn_ezra": "אבן עזרא", "ramban": "רמב\"ן",
    "sforno": "ספורנו", "or_hachaim": "אור החיים", "kli_yakar": "כלי יקר", "malbim": "מלבי\"ם",
    "metzudat_david": "מצודת דוד", "metzudat_zion": "מצודת ציון", "chizkuni": "חזקוני",
    "radak": "רד\"ק", "baal_haturim": "בעל הטורים", "abarbanel": "אברבנאל",
    "haamek_davar": "העמק דבר", "gur_aryeh": "גור אריה", "siftei_chachamim": "שפתי חכמים",
    "targum_onkelos": "אונקלוס", "onkelos": "אונקלוס", "targum_yonatan": "תרגום יונתן",
    # Talmud Bavli
    "tosafot": "תוספות", "ritva": "ריטב\"א", "rashba": "רשב\"א", "ran": "ר\"ן", "meiri": "מאירי",
    "rif": "רי\"ף", "rosh": "רא\"ש", "maharsha": "מהרש\"א", "maharshal": "מהרש\"ל",
    "chananel": "רבינו חננאל", "yad_ramah": "יד רמ\"ה", "shittah_mekubetzet": "שיטה מקובצת",
    "pnei_yehoshua": "פני יהושע", "rashbatz": "רשב\"ץ",
    # Mishnah (Sefaria keeps the 'Mishnah_' prefix on the base for these, so no ambiguity)
    "bartenura": "ברטנורא", "tiferet_yisrael": "תפארת ישראל", "yachin": "יכין", "boaz": "בועז",
    "rambam": "רמב\"ם", "maggid_mishneh": "מגיד משנה", "kessef_mishneh": "כסף משנה",
    "lechem_mishneh": "לחם משנה",
}

_HEAD_RE = re.compile(r"^(.+?)[ .](\d[\d. ]*)$")


def _split_book(flat: str) -> tuple[str | None, str]:
    """('Genesis 1.1' -> ('בראשית', '1:1')), ('Bava Metzia 3.1' -> ('בבא מציעא', '2.')) — the
    corpus's amud-linear N converted back to daf+amud (see daf_amud_to_corpus_n), ('Mishnah Bava
    Metzia 1.1' -> ('משנה בבא מציעא', '1:1')). (None, '') if the book/tractate isn't one of these
    three known tables."""
    m = _HEAD_RE.match(flat)
    if not m:
        return None, ""
    book, tail = m.group(1).strip(), m.group(2).strip()
    nums = re.split(r"[ .]+", tail)

    if book.startswith("Mishnah "):
        he_t = _TRACTATE_HE.get(book[len("Mishnah "):])
        if not he_t or len(nums) < 2:
            return None, ""
        return f"משנה {he_t}", f"{nums[0]}:{nums[1]}"

    if book in _TRACTATE_HE:
        if not nums or not nums[0].isdigit():
            return None, ""
        n = int(nums[0])
        daf, amud_mark = (n + 1) // 2, ("." if n % 2 else ":")
        return _TRACTATE_HE[book], f"{daf}{amud_mark}"

    if book in _BOOK_HE:
        if len(nums) < 2:
            return None, ""
        return _BOOK_HE[book], f"{nums[0]}:{nums[1]}"

    return None, ""


def hebrew_display_ref(ref: str | None) -> str | None:
    """Best-effort Hebrew rendering of a corpus ref for a Hebrew-reading user, or None if no Hebrew
    name is known for some part of it — the caller then keeps showing the original ref, which reads
    as more honest than a half-translated string.

        'Genesis.1.1'                 -> 'בראשית 1:1'
        'Bava_Metzia.3.1'             -> 'בבא מציעא 2.'      (daf 2a — see daf_amud_to_corpus_n)
        'Rashi_on_Genesis.1.1.1'      -> 'רש"י על בראשית 1:1'
        'Bartenura_on_Mishnah_Bava_Metzia.1.1.1' -> 'ברטנורא על משנה בבא מציעא 1:1'
    """
    if not ref:
        return None
    tail, prefix = ref, ""
    cid = commentator_from_ref(ref)
    if cid:
        he_name = COMMENTATOR_HE.get(cid)
        if not he_name:
            return None
        tail = ref.split(_ON, 1)[1]
        # Drop the trailing comment-index segment ('<base-ref>.<k>') so what's left is the base ref.
        head, _dot, last = tail.rpartition(".")
        if head and last.isdigit():
            tail = head
        prefix = f'{he_name} על '

    he_book, rest = _split_book(tail.replace("_", " "))
    if he_book is None:
        return None
    return f"{prefix}{he_book} {rest}"
