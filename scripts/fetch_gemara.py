# -*- coding: utf-8 -*-
"""
fetch_gemara.py — מוריד ש"ס בבלי (37 מסכתות) + מפרשים מ-Sefaria.
──────────────────────────────────────────────────────────────────────
צ'אנק = חלוקת ספריא הטבעית (לא אמוד):
  • גמרא-בסיס:     כל פסקה (segment) בנפרד  → text[amud][segment]
  • רש"י / תוספות: כל דיבור בנפרד           → text[amud][dibur]
  • מאירי / רשב"א / ריטב"א / …: כל קטע       → text[amud][segment]

פורמט פלט זהה ל-mishnah_chunks.json / all_chunks_full.json.
קישור עמוק: https://www.sefaria.org/{tractate}.{daf}{amud}.{seg}

הרצה:
    python scripts/fetch_gemara.py
    python scripts/fetch_gemara.py --tractates Berakhot Shabbat
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}
OUT = Path("data/processed/gemara_chunks.json")

# ── 37 מסכתות בבלי ──────────────────────────────────────────────────────────

SEDARIM_BAVLI: dict[str, list[str]] = {
    "Zeraim":   ["Berakhot"],
    "Moed":     ["Shabbat", "Eruvin", "Pesachim", "Yoma", "Sukkah",
                  "Beitzah", "Rosh Hashanah", "Taanit", "Megillah",
                  "Moed Katan", "Chagigah"],
    "Nashim":   ["Yevamot", "Ketubot", "Nedarim", "Nazir", "Sotah",
                  "Gittin", "Kiddushin"],
    "Nezikin":  ["Bava Kamma", "Bava Metzia", "Bava Batra", "Sanhedrin",
                  "Makkot", "Shevuot", "Avodah Zarah", "Horayot"],
    "Kodashim": ["Zevachim", "Menachot", "Chullin", "Bekhorot", "Arakhin",
                  "Temurah", "Keritot", "Meilah", "Tamid"],
    "Taharot":  ["Niddah"],
}
ALL_TRACTATES = [t for tracts in SEDARIM_BAVLI.values() for t in tracts]

# מפרשים — נסה כל אחד; 404 = לא קיים על מסכת זו (תקין)
GEMARA_COMMENTATORS = [
    "Rashi",
    "Tosafot",
    "Meiri",
    "Rashba",
    "Ritva",
    "Chidushei Halachot",   # מהרש"א חלק הלכות
    "Maharshal",
    "Ben Yehoyada",
]

_session = requests.Session()
_session.headers.update(HEADERS)

# ── Sefaria API ──────────────────────────────────────────────────────────────


def fetch_work(ref: str, retries: int = 3):
    """GET /api/v3/texts/<ref> → (he_nested, en_nested) or None."""
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
    """מיישר כל רמות קינון למחרוזת אחת."""
    if isinstance(x, list):
        return " ".join(_seg(i) for i in x if i).strip()
    return (x or "").strip() if isinstance(x, str) else ""


def _amud_label(amud_idx: int) -> tuple[int, str]:
    """אינדקס אמוד (0-based) → (דף, 'a'/'b').  0→2a, 1→2b, 2→3a, …"""
    return (amud_idx // 2) + 2, ("a" if amud_idx % 2 == 0 else "b")


def _get_amud_en(en_text, amud_idx: int):
    """בטוח מול None ו-out-of-range."""
    if not en_text or amud_idx >= len(en_text):
        return None
    return en_text[amud_idx]


# ── chunk builder ────────────────────────────────────────────────────────────


def _make_chunk(
    tractate: str,
    seder: str,
    daf: int,
    amud: str,
    seg_idx: int,           # 1-based
    ctype: str,
    commentator: str,
    he_t: str,
    en_t: str,
) -> dict | None:
    if not (he_t or en_t):
        return None
    amud_num = 1 if amud == "a" else 2
    label = commentator if commentator else tractate
    # verse_id תואם לכתובת ספריא: Berakhot.2a.3
    verse_id = f"{tractate}.{daf}{amud}.{seg_idx}"
    doc = f"[{label}] {tractate} {daf}{amud}:{seg_idx}\n{he_t}\n{en_t}".strip()
    cmt_slug = commentator.replace(" ", "") if commentator else ""
    cid = f"{verse_id}_{cmt_slug or 'gemara'}"
    return {
        "id": cid,
        "document": doc,
        "metadata": {
            "verse_id": verse_id,
            "book": tractate,
            "chapter": daf,
            "verse": amud_num * 1000 + seg_idx,   # ייחודי בתוך מסכת
            "daf": daf,
            "amud": amud,
            "segment": seg_idx,
            "chunk_type": ctype,
            "commentator": commentator,
            "seder": seder,
            "tractate": tractate,
            "work": "talmud_bavli",
            "text_he": he_t,
            "text_en": en_t,
        },
    }


# ── iterate helpers ──────────────────────────────────────────────────────────


def iter_gemara_chunks(he_text, en_text, tractate: str, seder: str) -> list[dict]:
    """גמרא-בסיס: text[amud][segment] → פסקה אחת = צ'אנק אחד."""
    out = []
    for ai, amud_segs in enumerate(he_text or []):
        if not amud_segs or not isinstance(amud_segs, list):
            continue
        daf, amud = _amud_label(ai)
        en_amud = _get_amud_en(en_text, ai) or []
        for si, seg in enumerate(amud_segs):
            he_t = _seg(seg)
            en_t = _seg(en_amud[si]) if si < len(en_amud) else ""
            c = _make_chunk(tractate, seder, daf, amud, si + 1,
                            "gemara", "", he_t, en_t)
            if c:
                out.append(c)
    return out


def iter_commentary_chunks(he_text, en_text, tractate: str, seder: str,
                           commentator: str) -> list[dict]:
    """מפרש: 2 רמות (amud→segment) או 3 רמות (amud→dibur→text).
    בשני המקרים: יחידת ספריא אחת = צ'אנק אחד.
    """
    out = []
    for ai, amud_data in enumerate(he_text or []):
        if not amud_data or not isinstance(amud_data, list):
            continue
        daf, amud = _amud_label(ai)
        en_amud = _get_amud_en(en_text, ai) or []

        # זהה: 2-level (item=string/list-of-words) או 3-level (item=list-of-strings)
        # בשני המקרים ה-item הוא "יחידה אחת" בעיני ספריא
        for ui, unit in enumerate(amud_data):
            he_t = _seg(unit)
            en_t = _seg(en_amud[ui]) if ui < len(en_amud) else ""
            c = _make_chunk(tractate, seder, daf, amud, ui + 1,
                            "commentary", commentator, he_t, en_t)
            if c:
                out.append(c)
    return out


# ── main ─────────────────────────────────────────────────────────────────────


CKPT = Path("data/processed/gemara_checkpoint.jsonl")  # checkpoint — שורה לכל מסכת


def _load_checkpoint() -> tuple[set[str], dict[str, int]]:
    """טוען מסכתות שכבר נשמרו ב-checkpoint."""
    done: set[str] = set()
    stats: dict[str, int] = {"gemara": 0, "commentary": 0, "fetched": 0, "missing": 0}
    if not CKPT.exists():
        return done, stats
    with CKPT.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            done.add(rec["tractate"])
            for k in stats:
                stats[k] += rec.get(k, 0)
    print(f"[resume] {len(done)} מסכתות כבר בוצעו: {', '.join(sorted(done))}")
    return done, stats


def _save_checkpoint(tractate: str, tractate_chunks: list[dict],
                     tractate_stats: dict[str, int]) -> None:
    """מוסיף שורת checkpoint + כותב את הצ'אנקים של המסכת ישירות לקובץ JSONL."""
    # כתיבה זורמת — שורה אחת = צ'אנק אחד
    with open(str(OUT) + ".jsonl", "a", encoding="utf-8") as fout:
        for c in tractate_chunks:
            fout.write(json.dumps(c, ensure_ascii=False) + "\n")
    # רשומת checkpoint
    rec = {"tractate": tractate, **tractate_stats}
    with CKPT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _assemble_final(total_tractates: int, stats: dict[str, int]) -> None:
    """הופך את ה-JSONL לקובץ JSON סופי (כתיבה זורמת — לא טוען הכל לזיכרון)."""
    jsonl = Path(str(OUT) + ".jsonl")
    if not jsonl.exists():
        return
    total = sum(1 for _ in jsonl.open(encoding="utf-8"))
    print(f"[assemble] כותב {total:,} צ'אנקים ל-{OUT} …")
    with OUT.open("w", encoding="utf-8") as fout:
        # header
        header = json.dumps({
            "metadata": {
                "total_chunks": total,
                "tractates": total_tractates,
                "by_type": {
                    "gemara":     stats.get("gemara", 0),
                    "commentary": stats.get("commentary", 0),
                },
                "works_fetched": stats["fetched"],
                "works_missing": stats["missing"],
            }
        }, ensure_ascii=False)
        fout.write(header[:-1] + ', "chunks": [\n')  # פתח מערך
        with jsonl.open(encoding="utf-8") as fin:
            for j, line in enumerate(fin):
                fout.write(line.rstrip("\n"))
                fout.write(",\n" if j + 1 < total else "\n")
        fout.write("]}\n")
    mb = OUT.stat().st_size / 1e6
    print(f"💾 {OUT}  ({mb:.1f} MB)")


def build():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tractates", nargs="*", default=None)
    ap.add_argument("--reset", action="store_true", help="מחק checkpoint והתחל מחדש")
    args = ap.parse_args()

    if args.reset:
        CKPT.unlink(missing_ok=True)
        Path(str(OUT) + ".jsonl").unlink(missing_ok=True)
        print("[reset] checkpoint נמחק")

    tractates_to_fetch = args.tractates or ALL_TRACTATES
    tractate_seder = {t: s for s, ts in SEDARIM_BAVLI.items() for t in ts}

    done_tractates, stats = _load_checkpoint()
    remaining = [t for t in tractates_to_fetch if t not in done_tractates]
    total = len(tractates_to_fetch)

    OUT.parent.mkdir(parents=True, exist_ok=True)

    for i, tractate in enumerate(remaining, len(done_tractates) + 1):
        seder = tractate_seder.get(tractate, "Unknown")
        print(f"[{i}/{total}] 📖 {tractate}  (סדר {seder})")
        tractate_chunks: list[dict] = []
        t_stats: dict[str, int] = {"gemara": 0, "commentary": 0, "fetched": 0, "missing": 0}

        # ── גוף הגמרא ───────────────────────────────────────────────────────
        result = fetch_work(tractate)
        if result:
            t_stats["fetched"] += 1
            ghe, gen = result
            new = iter_gemara_chunks(ghe, gen, tractate, seder)
            tractate_chunks.extend(new)
            t_stats["gemara"] += len(new)
            print(f"    ✓ גמרא: {len(new)} פסקאות")
        else:
            print(f"  ⚠️  לא נמצא: {tractate}")
            t_stats["missing"] += 1
        time.sleep(0.5)

        # ── מפרשים ──────────────────────────────────────────────────────────
        for commentator in GEMARA_COMMENTATORS:
            c_result = fetch_work(f"{commentator} on {tractate}")
            if not c_result:
                t_stats["missing"] += 1
                time.sleep(0.2)
                continue
            t_stats["fetched"] += 1
            che, cen = c_result
            new = iter_commentary_chunks(che, cen, tractate, seder, commentator)
            tractate_chunks.extend(new)
            t_stats["commentary"] += len(new)
            print(f"    ✓ {commentator}: {len(new)} יחידות")
            time.sleep(0.3)

        # ── checkpoint ───────────────────────────────────────────────────────
        _save_checkpoint(tractate, tractate_chunks, t_stats)
        for k in stats:
            stats[k] += t_stats.get(k, 0)
        print(f"    ✓ נשמר checkpoint  ({stats.get('gemara', 0) + stats.get('commentary', 0):,} סה\"כ)")

    # ── הרכבת קובץ סופי ─────────────────────────────────────────────────────
    _assemble_final(len(tractates_to_fetch), stats)
    print(f"\n✅ DONE — "
          f"{stats.get('gemara', 0):,} גמרא + {stats.get('commentary', 0):,} מפרשים | "
          f"fetched: {stats['fetched']}, missing: {stats['missing']}")


if __name__ == "__main__":
    build()
