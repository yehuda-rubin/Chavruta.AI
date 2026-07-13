# -*- coding: utf-8 -*-
"""
fetch_mishnah.py — מוריד את כל המשנה + מפרשים מ-Sefaria ובונה mishnah_chunks.json.
──────────────────────────────────────────────────────────────────────────────────
פורמט הפלט זהה לחלוטין ל-all_chunks_full.json:
  • chunk_type="mishnah"    — גוף המשנה   (book=tractate, verse=מספר המשנה)
  • chunk_type="commentary" — מפרשים

מפרשים: Bartenura, Tosefot Yom Tov, Tiferet Yisrael, Rambam (אם קיים ב-Sefaria)

הרצה:
    python scripts/fetch_mishnah.py                    # הכל
    python scripts/fetch_mishnah.py --tractates Berakhot Shabbat  # בחירה
    python scripts/fetch_mishnah.py --links            # + כתיבת mishnah_links.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}
OUT = Path("data/processed/mishnah_chunks.json")
LINKS_OUT = Path("data/processed/mishnah_links.jsonl")

# ── 63 מסכתות לפי סדר ───────────────────────────────────────────────────────

SEDER_ZERAIM = ["Berakhot", "Peah", "Demai", "Kilayim", "Sheviit", "Terumot",
                 "Maasrot", "Maaser Sheni", "Challah", "Orlah", "Bikkurim"]
SEDER_MOED = ["Shabbat", "Eruvin", "Pesachim", "Shekalim", "Yoma", "Sukkah",
               "Beitzah", "Rosh Hashanah", "Taanit", "Megillah", "Moed Katan", "Chagigah"]
SEDER_NASHIM = ["Yevamot", "Ketubot", "Nedarim", "Nazir", "Sotah", "Gittin", "Kiddushin"]
SEDER_NEZIKIN = ["Bava Kamma", "Bava Metzia", "Bava Batra", "Sanhedrin", "Makkot",
                  "Shevuot", "Eduyot", "Avodah Zarah", "Pirkei Avot", "Horayot"]
SEDER_KODASHIM = ["Zevachim", "Menachot", "Chullin", "Bekhorot", "Arakhin",
                   "Temurah", "Keritot", "Meilah", "Tamid", "Middot", "Kinnim"]
SEDER_TAHAROT = ["Kelim", "Oholot", "Negaim", "Parah", "Tahorot", "Mikvaot",
                  "Niddah", "Makhshirin", "Zavim", "Tevul Yom", "Yadayim", "Uktzin"]

SEDARIM: dict[str, list[str]] = {
    "Zeraim": SEDER_ZERAIM,
    "Moed": SEDER_MOED,
    "Nashim": SEDER_NASHIM,
    "Nezikin": SEDER_NEZIKIN,
    "Kodashim": SEDER_KODASHIM,
    "Taharot": SEDER_TAHAROT,
}
ALL_TRACTATES = [t for tracts in SEDARIM.values() for t in tracts]

# Tractates that don't use "Mishnah " prefix in Sefaria
BARE_TRACTATES = {"Pirkei Avot", "Uktzin"}

# מפרשים עיקריים על המשנה
MISHNAH_COMMENTATORS = [
    "Bartenura",
    "Tosafot Yom Tov",      # correct Sefaria title (not Tosefot)
    "Tiferet Yisrael",
    "Rambam",
]

_session = requests.Session()
_session.headers.update(HEADERS)

# ── Sefaria helpers ──────────────────────────────────────────────────────────


def _base_ref(tractate: str) -> str:
    """Sefaria title for the Mishnah base text (without commentator prefix)."""
    return tractate if tractate in BARE_TRACTATES else f"Mishnah {tractate}"


def _commentary_candidates(commentator: str, tractate: str) -> list[str]:
    """Try forms Sefaria might use for a commentator on a Mishnah tractate."""
    base = _base_ref(tractate)
    bare = tractate  # e.g. "Berakhot" without "Mishnah"
    candidates = [f"{commentator} on {base}"]
    if bare != base:
        candidates.append(f"{commentator} on {bare}")
    return candidates


def fetch_work(ref: str, retries: int = 3):
    """GET /api/v3/texts/<ref> → (he_nested, en_nested) or None on 404."""
    for attempt in range(retries):
        try:
            r = _session.get(
                f"{BASE}/api/v3/texts/{ref}",
                params={"version": ["hebrew", "english"], "return_format": "text_only"},
                timeout=90,
            )
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 200:
            he = en = None
            for v in r.json().get("versions", []):
                fam = (v.get("languageFamilyName") or v.get("language") or "").lower()
                if fam.startswith("he") and he is None:
                    he = v.get("text")
                elif fam.startswith("en") and en is None:
                    en = v.get("text")
            return he, en
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * (attempt + 1))
            continue
        return None
    return None


def _seg(x) -> str:
    """Flatten nested list-of-lists or string to a single string."""
    if isinstance(x, list):
        return " ".join(_seg(i) for i in x if i).strip()
    return (x or "").strip() if isinstance(x, str) else ""


def _get(nested, ch: int, vs: int):
    try:
        return nested[ch][vs]
    except (IndexError, TypeError):
        return ""


# ── Chunk builder ────────────────────────────────────────────────────────────


def add_chunk(
    chunks: list,
    stats: dict,
    tractate: str,
    seder: str,
    ch: int,
    m: int,
    ctype: str,
    commentator: str,
    he_t: str,
    en_t: str,
) -> None:
    if not (he_t or en_t):
        return
    book = _base_ref(tractate)
    label = commentator if commentator else book
    doc = f"[{label}] {tractate} {ch}:{m}\n{he_t}\n{en_t}".strip()
    cmt_slug = commentator.replace(" ", "") if commentator else ""
    verse_id = f"{book}.{ch}.{m}"
    cid = f"{verse_id}_{cmt_slug or 'mishnah'}"
    chunks.append({
        "id": cid,
        "document": doc,
        "metadata": {
            "verse_id": verse_id,
            "book": book,
            "chapter": ch,
            "verse": m,
            "chunk_type": ctype,
            "commentator": commentator,
            "seder": seder,
            "tractate": tractate,
            "work": "mishnah",
            "text_he": he_t,
            "text_en": en_t,
        },
    })
    key = "commentary" if commentator else "mishnah"
    stats[key] = stats.get(key, 0) + 1


# ── Main ─────────────────────────────────────────────────────────────────────


def build(tractate_filter: list[str] | None = None, write_links: bool = False):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tractates", nargs="*", default=None, help="מסכתות ספציפיות")
    ap.add_argument("--links", action="store_true", help="כתוב mishnah_links.jsonl")
    args = ap.parse_args()

    tractates_to_fetch = args.tractates or tractate_filter or ALL_TRACTATES
    emit_links = args.links or write_links

    # Build seder lookup
    tractate_seder: dict[str, str] = {}
    for seder, tracts in SEDARIM.items():
        for t in tracts:
            tractate_seder[t] = seder

    chunks: list[dict] = []
    links: list[dict] = []
    stats: dict[str, int] = {"mishnah": 0, "commentary": 0, "fetched": 0, "missing": 0}
    total = len(tractates_to_fetch)

    for i, tractate in enumerate(tractates_to_fetch, 1):
        seder = tractate_seder.get(tractate, "Unknown")
        base_ref = _base_ref(tractate)
        print(f"[{i}/{total}] 📖 {base_ref}  (סדר {seder})")

        # ── base Mishnah text ────────────────────────────────────────────────
        result = fetch_work(base_ref)
        if result:
            stats["fetched"] += 1
            mhe, men = result
            for ci, mishnahs in enumerate(mhe or []):
                if not isinstance(mishnahs, list):
                    # Some tractates have a flat list (1 chapter only)
                    mishnahs = [mishnahs]
                for mi, mtext in enumerate(mishnahs):
                    he_t = _seg(mtext)
                    en_t = _seg(_get(men, ci, mi)) if men else ""
                    add_chunk(chunks, stats, tractate, seder, ci + 1, mi + 1,
                               "mishnah", "", he_t, en_t)
        else:
            print(f"  ⚠️  לא נמצא: {base_ref}")
            stats["missing"] += 1
        time.sleep(0.4)

        # ── commentaries ─────────────────────────────────────────────────────
        for commentator in MISHNAH_COMMENTATORS:
            c_result = None
            c_ref_used = None
            for candidate in _commentary_candidates(commentator, tractate):
                c_result = fetch_work(candidate)
                if c_result:
                    c_ref_used = candidate
                    break

            if not c_result:
                stats["missing"] += 1
                time.sleep(0.2)
                continue

            stats["fetched"] += 1
            che, cen = c_result
            for ci, mishnahs in enumerate(che or []):
                if not isinstance(mishnahs, list):
                    mishnahs = [mishnahs]
                for mi, mtext in enumerate(mishnahs):
                    he_t = _seg(mtext)
                    en_t = _seg(_get(cen, ci, mi)) if cen else ""
                    add_chunk(chunks, stats, tractate, seder, ci + 1, mi + 1,
                               "commentary", commentator, he_t, en_t)

                    if emit_links and (he_t or en_t):
                        book = _base_ref(tractate)
                        links.append({
                            "from_ref": f"{c_ref_used} {ci + 1}:{mi + 1}",
                            "to_ref": f"{book}.{ci + 1}.{mi + 1}",
                            "from_work_id": commentator.lower().replace(" ", "_"),
                            "to_work_id": "mishnah",
                            "link_type": "commentary",
                        })
            time.sleep(0.3)

        print(f"    → chunks so far: {len(chunks):,}")

    # ── write output ─────────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "total_chunks": len(chunks),
            "tractates": len(tractates_to_fetch),
            "by_type": {"mishnah": stats.get("mishnah", 0), "commentary": stats.get("commentary", 0)},
            "works_fetched": stats["fetched"],
            "works_missing": stats["missing"],
        },
        "chunks": chunks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    mb = OUT.stat().st_size / 1e6
    print(f"\n✅ DONE — {len(chunks):,} chunks "
          f"({stats.get('mishnah', 0):,} mishnahs + {stats.get('commentary', 0):,} commentary) "
          f"| fetched: {stats['fetched']}, missing: {stats['missing']}")
    print(f"💾 {OUT}  ({mb:.1f} MB)")

    if emit_links and links:
        with LINKS_OUT.open("w", encoding="utf-8") as f:
            for lnk in links:
                f.write(json.dumps(lnk, ensure_ascii=False) + "\n")
        print(f"🔗 {len(links):,} links → {LINKS_OUT}")


if __name__ == "__main__":
    build()
