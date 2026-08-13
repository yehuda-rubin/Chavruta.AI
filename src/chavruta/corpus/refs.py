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


# Per-chapter verse counts for the 5 Chumash books (Masoretic — fixed forever), fetched once from
# Sefaria's /api/shape/<book> and checked in as static data — the fast path, no network, for the
# overwhelmingly common case (a parsha range). Used only by expand_range: a range spans many verses
# and fetch_by_refs has no native range support, so the range must be enumerated into individual
# verse refs before it can be looked up.
_TORAH_LENGTHS_PATH = Path(__file__).parent / "torah_chapter_lengths.json"
_TORAH_CHAPTER_LENGTHS: dict[str, list[int]] | None = None


def _torah_chapter_lengths() -> dict[str, list[int]]:
    global _TORAH_CHAPTER_LENGTHS
    if _TORAH_CHAPTER_LENGTHS is None:
        _TORAH_CHAPTER_LENGTHS = json.loads(_TORAH_LENGTHS_PATH.read_text(encoding="utf-8"))
    return _TORAH_CHAPTER_LENGTHS


# The Haftarah is a range in NEVI'IM (Isaiah, Jeremiah, Ezekiel, or one of the 12 minor prophets —
# whichever book varies by week), not one of the 5 Chumash books the static file covers. Rather than
# hand-maintaining chapter-lengths for every book that could ever be a Haftarah source, fall back to
# fetching it from the SAME Sefaria endpoint the static file was built from, once per book per
# process lifetime (in-memory only — this is small, cheap, and reused for the rest of the week).
_SHAPE_CACHE: dict[str, list[int]] = {}
_SHAPE_MAX_ATTEMPTS = 2


def _fetch_shape(book: str) -> list[int] | None:
    import requests  # lazy, matching sefaria_calendar.py's convention

    url = f"https://www.sefaria.org/api/shape/{book.replace(' ', '_')}"
    for attempt in range(1, _SHAPE_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            chapters = (data[0] or {}).get("chapters") if isinstance(data, list) and data else None
            if isinstance(chapters, list) and chapters:
                return chapters
            return None   # a well-formed-but-empty response won't improve on retry
        except Exception:  # noqa: BLE001 — any failure just counts as an attempt
            if attempt == _SHAPE_MAX_ATTEMPTS:
                return None
    return None


def _chapter_lengths_for(book: str) -> list[int] | None:
    """Chapter-verse-counts for ANY Tanakh book — the static Torah table first (no network for the
    common case), then Sefaria's /api/shape on demand (cached in-memory per process) for anything
    else, e.g. a Haftarah's Nevi'im book."""
    lengths = _torah_chapter_lengths().get(book)
    if lengths:
        return lengths
    if book in _SHAPE_CACHE:
        return _SHAPE_CACHE[book]
    lengths = _fetch_shape(book)
    if lengths:
        _SHAPE_CACHE[book] = lengths
    return lengths


_RANGE_RE = re.compile(r"^(?P<book>.+?)\s+(?P<c1>\d+):(?P<v1>\d+)-(?P<c2>\d+):(?P<v2>\d+)$")


def expand_range(ref_range: str) -> list[str]:
    """A Sefaria range ref ('Genesis 1:1-6:8', as returned by the calendar API for a parsha or
    Haftarah) to the flat list of dotted verse refs it covers ('Genesis.1.1', ..., 'Genesis.6.8') —
    fetch_by_refs has no native range support, so the range must be enumerated first. Returns [] for
    a book whose chapter lengths can't be resolved (static table miss AND the Sefaria fallback
    failed) or a range this can't parse, rather than guessing wrong (Principle I: absent, not
    invented)."""
    m = _RANGE_RE.match((ref_range or "").strip())
    if not m:
        return []
    book = m.group("book")
    lengths = _chapter_lengths_for(book)
    if not lengths:
        return []
    c1, v1, c2, v2 = int(m.group("c1")), int(m.group("v1")), int(m.group("c2")), int(m.group("v2"))
    if c1 < 1 or c2 > len(lengths) or c1 > c2:
        return []
    out: list[str] = []
    for c in range(c1, c2 + 1):
        start_v = v1 if c == c1 else 1
        end_v = v2 if c == c2 else lengths[c - 1]
        out.extend(f"{book}.{c}.{v}" for v in range(start_v, end_v + 1))
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

# Full Hebrew title map from Sefaria — loaded lazily and defensively.
# Generated by scripts/build_hebrew_titles.py from the Sefaria TOC API. Shape:
#   {"<English title>": {"he": "<Hebrew title>", "cat": "<top-level Sefaria category>"}}
# Sefaria keys a commentary under its FULL title ('Turei Zahav on Shulchan Arukh, Orach Chayim'),
# which is why the lookup below matches the ref's whole title portion rather than composing
# "<commentator> על <base>" itself — Sefaria's own Hebrew for the pair is better than ours.
# Package data, NOT the repo's `data/` directory: that one is gitignored wholesale, so a table
# generated there works locally and is silently absent in the deployed image — the same trap
# licenses.json (its neighbour here) was moved out of. See .gitignore's note at the `data/` rule.
_HEBREW_TITLES_PATH = Path(__file__).parent / "data" / "hebrew_titles.json"
_hebrew_titles_map: dict[str, dict[str, str]] | None = None


def _load_hebrew_titles() -> dict[str, dict[str, str]]:
    """Load the full Hebrew titles map once, defensively — missing/unparsable file degrades to empty."""
    global _hebrew_titles_map
    if _hebrew_titles_map is None:
        try:
            raw = json.loads(_HEBREW_TITLES_PATH.read_text(encoding="utf-8"))
            # Tolerate the older flat {title: he} shape so a stale data file degrades to "no
            # category known" (and is therefore refused for Talmud below) instead of crashing.
            _hebrew_titles_map = {
                k: (v if isinstance(v, dict) else {"he": v, "cat": ""}) for k, v in raw.items()
            }
        except (OSError, ValueError, AttributeError):
            _hebrew_titles_map = {}
    return _hebrew_titles_map

# Curated on purpose: these classic Rishonim/Acharonim are prioritized because their Sefaria
# "<Title>_on_<base>" ref is known to point straight at a bare Tanakh/Talmud-Bavli ref or a
# 'Mishnah_<Tractate>' ref — both handled unambiguously below with correct daf/amud math.
# Other commentators (on Tosefta, Yerushalmi, Mishneh Torah, Tur/Shulchan Aruch, Midrash, or
# responsa) fall back to the full Hebrew titles map (loaded from data/hebrew_titles.json) which
# provides coverage for every work in Sefaria without applying daf math — the daf/amud arithmetic
# is only valid for Bavli tractates in _TRACTATE_HE.
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

_derived_commentator_he: dict[str, str] | None = None


def _is_bavli(entry: dict[str, str] | None) -> bool:
    """Whether a titles-map entry is Talmud BAVLI — the one corner stored amud-linearly here, whose
    numbers are meaningless without `_split_book`'s daf/amud conversion.

    Sefaria files the Yerushalmi under the same top-level "Talmud" category, but the corpus stores it
    as chapter.halacha like any other work, so treating the whole category as amud-linear left every
    Jerusalem Talmud source untranslated. The sub-category is what tells them apart. An entry from an
    older map without `sub` falls back to the cautious reading — refuse — rather than risk a wrong daf.
    """
    if not entry:
        return False
    if (entry.get("cat") or "").strip().lower() != "talmud":
        return False
    sub = (entry.get("sub") or "").strip().lower()
    return sub != "yerushalmi"


def _commentator_he(cid: str) -> str | None:
    """Hebrew name for a commentator: the curated table first, then one derived from Sefaria's own
    commentary titles.

    COMMENTATOR_HE is hand-checked but finite, and a commentator missing from it on a TALMUD base
    can't fall through to the generic title path — that path refuses Talmud, because only
    `_split_book` knows the amud-linear→daf conversion. The result was that e.g.
    'Rashash_on_Gittin.61.3' stayed in English forever.

    Sefaria already publishes the Hebrew for the pair ('Rashash on Gittin' → 'רש"ש על גיטין'), so the
    commentator's own Hebrew name is just the part before ' על '. Deriving it keeps the daf math in
    `_split_book` (this only supplies the NAME) and covers every commentator Sefaria knows.
    """
    if he := COMMENTATOR_HE.get(cid):
        return he
    global _derived_commentator_he
    if _derived_commentator_he is None:
        derived: dict[str, str] = {}
        for title, entry in _load_hebrew_titles().items():
            en_head, sep, _en_base = title.partition(" on ")
            he_head, he_sep, _he_base = (entry.get("he") or "").partition(" על ")
            if sep and he_sep and en_head and he_head:
                derived.setdefault(_slug(en_head), he_head.strip())
        _derived_commentator_he = derived
    return _derived_commentator_he.get(cid)


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
        'Shulchan_Arukh,_Orach_Chayim.310.1' -> 'שולחן ערוך, אורח חיים 310:1'  (via JSON map)
    """
    if not ref:
        return None

    def _curated(cid: str | None, name: str | None) -> str | None:
        """Hand-checked/derived commentator name + `_split_book`, which is the ONLY code that knows
        the corpus's amud-linear→daf conversion."""
        tail, prefix = ref, ""
        if cid and name:
            tail = ref.split(_ON, 1)[1]
            # Drop the trailing comment-index segment ('<base-ref>.<k>') → the base ref.
            head, _dot, last = tail.rpartition(".")
            if head and last.isdigit():
                tail = head
            prefix = f"{name} על "
        he_book, rest = _split_book(tail.replace("_", " "))
        return f"{prefix}{he_book} {rest}" if he_book is not None else None

    cid = commentator_from_ref(ref)

    # 1) Curated commentator (or a bare base text) → daf math is correct by construction: the
    #    curated table only holds commentators whose base is a Tanakh/Bavli/Mishnah ref.
    if out := _curated(cid, COMMENTATOR_HE.get(cid) if cid else None):
        return out

    # 2) The generic path — Sefaria's own Hebrew for the WHOLE title, including commentary titles
    #    ('Turei Zahav on Shulchan Arukh, Orach Chayim' → 'טורי זהב על שולחן ערוך אורח חיים'), which
    #    is why this matches the full title portion instead of composing "<commentator> על <base>".
    #    Numbers pass straight through as 'a:b' — never daf math.
    #
    #    This runs BEFORE the derived-name path below, and that order is load-bearing. A Tosefta
    #    commentary strips to a base that looks exactly like a Bavli tractate
    #    ('Tosefta_Kifshutah_on_Bava_Metzia.1.1.1' → 'Bava Metzia'), so letting `_split_book` see it
    #    renders chapter 1 halacha 1 as 'daf 1a'. Sefaria's category is what tells the two apart.
    entry = None
    if m := _HEAD_RE.match(ref.replace("_", " ")):
        title, nums = m.group(1).strip(), m.group(2).strip()
        entry = _load_hebrew_titles().get(title)
        if entry and entry.get("he") and not _is_bavli(entry):
            return f"{entry['he']} {':'.join(re.split(r'[ .]+', nums))}"

    # 3) A Bavli commentary whose commentator isn't in the curated table (e.g. Rashash on Gittin):
    #    the name comes from Sefaria, the daf conversion still from `_split_book`.
    if cid and entry and _is_bavli(entry):
        return _curated(cid, _commentator_he(cid))
    return None
