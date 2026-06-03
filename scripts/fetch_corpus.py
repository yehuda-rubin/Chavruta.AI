# -*- coding: utf-8 -*-
"""
fetch_corpus.py — מוריד את כל התנ"ך + המפרשים מ-Sefaria ובונה all_chunks_full.json.
─────────────────────────────────────────────────────────────────────────────
יעיל: קריאה אחת לכל (יצירה × ספר) דרך v3 texts API — ~300 קריאות סה"כ, לא פסוק-פסוק.
פלט בפורמט שתואם ל-embed_corpus_gpu.py + load_to_qdrant.py.

  • טקסט בסיס:  chunk_type="pasuk",  commentator=""
  • מפרש:       chunk_type="commentary", commentator=<שם>

הרצה:
    python scripts/fetch_corpus.py                 # הכל
    python scripts/fetch_corpus.py --books Genesis # ספר אחד (בדיקה)
"""

import argparse
import json
import time
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}
OUT = Path("data/processed/all_chunks_full.json")

# ── 39 יחידות-ספר של Sefaria (תנ"ך מלא) ──────────────────────────────
TORAH = ["Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy"]
NEVIIM = ["Joshua", "Judges", "I Samuel", "II Samuel", "I Kings", "II Kings",
          "Isaiah", "Jeremiah", "Ezekiel", "Hosea", "Joel", "Amos", "Obadiah",
          "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai",
          "Zechariah", "Malachi"]
KETUVIM = ["Psalms", "Proverbs", "Job", "Song of Songs", "Ruth", "Lamentations",
           "Ecclesiastes", "Esther", "Daniel", "Ezra", "Nehemiah",
           "I Chronicles", "II Chronicles"]
ALL_BOOKS = TORAH + NEVIIM + KETUVIM

COMMENTATORS = ["Rashi", "Ramban", "Ibn Ezra", "Radak", "Sforno", "Rashbam",
                "Or HaChaim", "Baal HaTurim", "Malbim", "Metzudat David", "Metzudat Zion"]
TARGUMIM = ["Onkelos", "Targum Jonathan"]

_session = requests.Session()
_session.headers.update(HEADERS)


def _candidate_titles(name: str, book: str) -> list[str]:
    if name in TARGUMIM:
        return [f"{name} on {book}", f"{name} {book}", f"Targum {name} on {book}"]
    return [f"{name} on {book}"]


def fetch_work(ref: str, retries: int = 3):
    """מחזיר (he, en) כל אחד = nested list, או None אם 404."""
    for attempt in range(retries):
        try:
            r = _session.get(f"{BASE}/api/v3/texts/{ref}",
                             params={"version": ["hebrew", "english"],
                                     "return_format": "text_only"}, timeout=90)
        except requests.RequestException:
            time.sleep(2 * (attempt + 1)); continue
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
            time.sleep(2 * (attempt + 1)); continue
        return None
    return None


def _seg(x) -> str:
    """משטח מחרוזת או רשימת-קטעים לטקסט אחד."""
    if isinstance(x, list):
        return " ".join(_seg(i) for i in x if i).strip()
    return (x or "").strip() if isinstance(x, str) else ""


def _get(nested, ch, vs):
    try:
        return nested[ch][vs]
    except (IndexError, TypeError):
        return ""


def build():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", nargs="*", default=None, help="ספרים מסוימים (ברירת מחדל: הכל)")
    args = ap.parse_args()
    books = args.books or ALL_BOOKS

    chunks = []
    stats = {"pasuk": 0, "commentary": 0, "works_fetched": 0, "works_404": 0}

    def add(book, ch, vs, ctype, cmt, he_t, en_t):
        if not (he_t or en_t):
            return
        label = cmt if cmt else book
        doc = f"[{label}] {book} {ch}:{vs}\n{he_t}\n{en_t}".strip()
        cid = f"{book}.{ch}.{vs}_{(cmt or 'pasuk').replace(' ', '')}"
        chunks.append({
            "id": cid,
            "document": doc,
            "metadata": {
                "verse_id": f"{book}.{ch}.{vs}", "book": book,
                "chapter": ch, "verse": vs,
                "chunk_type": ctype, "commentator": cmt,
                "text_he": he_t, "text_en": en_t,
            },
        })
        stats[ctype] += 1

    for bi, book in enumerate(books, 1):
        print(f"[{bi}/{len(books)}] 📖 {book}")
        base = fetch_work(book)
        if base:
            stats["works_fetched"] += 1
            bhe, ben = base
            for ci, verses in enumerate(bhe or []):
                if not isinstance(verses, list):
                    continue
                for vi, vtext in enumerate(verses):
                    add(book, ci + 1, vi + 1, "pasuk", "",
                        _seg(vtext), _seg(_get(ben, ci, vi)))
        time.sleep(0.3)

        for name in COMMENTATORS + TARGUMIM:
            res = None
            for title in _candidate_titles(name, book):
                res = fetch_work(title)
                if res:
                    break
            if not res:
                stats["works_404"] += 1
                continue
            stats["works_fetched"] += 1
            che, cen = res
            for ci, verses in enumerate(che or []):
                if not isinstance(verses, list):
                    continue
                for vi, segs in enumerate(verses):
                    add(book, ci + 1, vi + 1, "commentary", name,
                        _seg(segs), _seg(_get(cen, ci, vi)))
            time.sleep(0.3)
        print(f"    → chunks so far: {len(chunks):,}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {"total_chunks": len(chunks), "books": len(books),
                     "by_type": {"pasuk": stats["pasuk"], "commentary": stats["commentary"]},
                     "works_fetched": stats["works_fetched"], "works_404": stats["works_404"]},
        "chunks": chunks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    mb = OUT.stat().st_size / 1e6
    print(f"\n✅ DONE — {len(chunks):,} chunks ({stats['pasuk']:,} pasuk + "
          f"{stats['commentary']:,} commentary) | works: {stats['works_fetched']} ok, "
          f"{stats['works_404']} missing")
    print(f"💾 {OUT}  ({mb:.1f} MB)")


if __name__ == "__main__":
    build()
