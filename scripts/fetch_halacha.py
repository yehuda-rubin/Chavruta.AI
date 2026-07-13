# -*- coding: utf-8 -*-
"""
fetch_halacha.py — מוריד את כל ספריית ההלכה (Halakhah) מ-Sefaria, בחלקים.
──────────────────────────────────────────────────────────────────────────────
מייבא את קטגוריית "Halakhah" המלאה (רמב"ם · טור · שו"ע + נושאי כלים · ספרי מצוות ·
ראשונים · אחרונים · מודרני · כל הסופר-פרשנויות) — אותו פורמט צ'אנקים כמו
mishnah/gemara/shut:

    {"id", "document", "metadata": {verse_id, book, chapter, verse, chunk_type,
        commentator, work, period, author_he, section, category_path,
        text_he, text_en}}

הקטגוריה ענקית (~2,169 חיבורים), אז מורידים **חלק בכל הרצה** עד שנגמור:

    python scripts/fetch_halacha.py --plan          # הצג כמה חיבורים וכמה חלקים
    python scripts/fetch_halacha.py --next 50       # ייבא 50 החיבורים הבאים → part NN
    python scripts/fetch_halacha.py --next 50       # שוב — 50 הבאים → part NN+1
    ...                                             # חזור עד "✅ ALL WORKS DONE"
    python scripts/fetch_halacha.py --reset         # התחל מאפס

כל חלק נשמר ל-data/processed/halacha/halacha_partNN.jsonl (+ .json) — קובץ עצמאי
שאפשר להעלות ל-HF ולהריץ עליו את מחברת הקאגל או את Nebius Job (ingest_job.py).
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}
OUTDIR = Path("data/processed/halacha")
CKPT = OUTDIR / "_checkpoint.jsonl"     # שורה לכל חיבור שהושלם (כולל מספר ה-part)

# תת-קטגוריה ב-Sefaria → תקופה (תואם source_kinds / hit_kind). התקופה מתעדכנת
# ככל שיורדים בעץ — התת-קטגוריה הקרובה ביותר קובעת (Commentary תחת רמב"ם → acharonim).
PERIOD = {
    "Mishneh Torah": "rishonim",
    "Tur": "rishonim",
    "Shulchan Arukh": "acharonim",
    "Shulchan Arukh HaRav": "acharonim",
    "Sifrei Mitzvot": "rishonim",
    "Rishonim": "rishonim",
    "Acharonim": "acharonim",
    "Modern": "modern",
    "Commentary": "acharonim",
}

_session = requests.Session()
_session.headers.update(HEADERS)


# ── Sefaria API (זהה ל-fetch_shut.py) ────────────────────────────────────────


def _get_json(path: str, params: dict | None = None, retries: int = 3):
    url = f"{BASE}/api/{path}"
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=90)
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * (attempt + 1))
            continue
        return None
    return None


def fetch_text(ref: str):
    data = _get_json(f"v3/texts/{urllib.parse.quote(ref)}",
                     params={"version": ["hebrew", "english"], "return_format": "text_only"})
    if not data:
        return None
    he = en = None
    for v in data.get("versions", []):
        fam = (v.get("languageFamilyName") or v.get("language") or "").lower()
        if fam.startswith("he") and he is None:
            he = v.get("text")
        elif fam.startswith("en") and en is None:
            en = v.get("text")
    return he, en


# ── catalog: every Halakhah work + period + category path ────────────────────


def load_works() -> list[dict]:
    """Walk the live Halakhah TOC → ordered [{title, he_title, period, category_path}]."""
    toc = _get_json("index/")
    hal = next(c for c in toc if c.get("category") == "Halakhah")
    works: list[dict] = []

    def walk(node: dict, period: str, path: list[str]) -> None:
        cat = node.get("category", "")
        period = PERIOD.get(cat, period)
        path = path + [cat] if cat else path
        for ch in node.get("contents", []):
            if "contents" in ch:
                walk(ch, period, path)
            elif ch.get("title"):
                works.append({
                    "title": ch["title"],
                    "he_title": ch.get("heTitle", ""),
                    "period": period,
                    "category_path": " / ".join(path),
                })

    walk(hal, "acharonim", [])
    return works


# ── schema → leaf ref-bases (זהה ל-fetch_shut.py) ────────────────────────────


def _node_titles(node: dict) -> tuple[str, str]:
    en = he = ""
    for t in node.get("titles", []):
        if t.get("primary"):
            if t.get("lang") == "en":
                en = t.get("text", "")
            elif t.get("lang") == "he":
                he = t.get("text", "")
    return en or node.get("key", ""), he


def leaf_ref_bases(title: str, he_title: str) -> list[tuple[str, str, str]]:
    """Every leaf node's (en_ref_base, he_ref_base, section_en) — simple + complex."""
    idx = _get_json(f"v2/raw/index/{urllib.parse.quote(title)}")
    schema = (idx or {}).get("schema", {})
    out: list[tuple[str, str, str]] = []

    def walk(node: dict, en_ref: str, he_ref: str, section_en: str) -> None:
        if "nodes" in node:
            for ch in node["nodes"]:
                en_t, he_t = _node_titles(ch)
                if ch.get("default") or not en_t:
                    walk(ch, en_ref, he_ref, section_en)
                else:
                    walk(ch, f"{en_ref}, {en_t}",
                         f"{he_ref}, {he_t}" if he_t else he_ref,
                         en_t if not section_en else f"{section_en} / {en_t}")
        else:
            out.append((en_ref, he_ref, section_en))

    if "nodes" in schema:
        walk(schema, title, he_title, "")
    else:
        out.append((title, he_title, ""))
    return out


# ── chunk builder (זהה ל-fetch_shut.py, chunk_type=halacha) ──────────────────


def _seg(x) -> str:
    if isinstance(x, list):
        return " ".join(_seg(i) for i in x if i).strip()
    return (x or "").strip() if isinstance(x, str) else ""


def _walk_leaves(he, en, path: list[int]):
    if isinstance(he, list):
        for i, sub in enumerate(he):
            en_sub = en[i] if isinstance(en, list) and i < len(en) else None
            yield from _walk_leaves(sub, en_sub, path + [i + 1])
    else:
        yield path, (he or "") if isinstance(he, str) else "", \
            (en if isinstance(en, str) else "")


def build_chunks(work: dict, en_ref: str, section_en: str, he_nested, en_nested) -> list[dict]:
    book = work["title"]
    he_book = work["he_title"] or book
    out: list[dict] = []
    for path, he_t, en_t in _walk_leaves(he_nested, en_nested, []):
        he_t, en_t = _seg(he_t), _seg(en_t)
        if not (he_t or en_t):
            continue
        path_str = ".".join(str(p) for p in path) or "1"
        ref_label = f"{en_ref} {':'.join(str(p) for p in path)}".strip()
        verse_id = f"{en_ref}.{path_str}".replace(" ", "_")
        doc = f"[{he_book}] {ref_label}\n{he_t}\n{en_t}".strip()
        out.append({
            "id": f"{verse_id}_halacha",
            "document": doc,
            "metadata": {
                "verse_id": verse_id,
                "book": book,
                "chapter": path[0] if path else 1,
                "verse": path[-1] if path else 1,
                "chunk_type": "halacha",
                "commentator": "",
                "work": "halacha",
                "period": work["period"],
                "author_he": he_book,
                "section": section_en,
                "category_path": work["category_path"],
                "text_he": he_t,
                "text_en": en_t,
            },
        })
    return out


# ── checkpoint ────────────────────────────────────────────────────────────────


def _load_ckpt() -> tuple[set[str], int]:
    """→ (done_titles, last_part_no)."""
    done: set[str] = set()
    last_part = 0
    if not CKPT.exists():
        return done, last_part
    for line in CKPT.open(encoding="utf-8"):
        rec = json.loads(line)
        done.add(rec["title"])
        last_part = max(last_part, rec.get("part", 0))
    return done, last_part


def _write_part(part_no: int, chunks: list[dict]) -> None:
    jsonl = OUTDIR / f"halacha_part{part_no:02d}.jsonl"
    js = OUTDIR / f"halacha_part{part_no:02d}.json"
    with jsonl.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    payload = {"metadata": {"total_chunks": len(chunks), "part": part_no,
                            "by_type": {"halacha": len(chunks)}}, "chunks": chunks}
    js.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"💾 part {part_no:02d}: {len(chunks):,} chunks → {jsonl}  ({jsonl.stat().st_size/1e6:.1f} MB)")


# ── main ─────────────────────────────────────────────────────────────────────


def build() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", type=int, default=50, dest="batch",
                    help="כמה חיבורים לייבא בהרצה זו (חלק אחד)")
    ap.add_argument("--plan", action="store_true", help="הצג סטטוס ויציאה (בלי הורדה)")
    ap.add_argument("--reset", action="store_true", help="מחק הכל והתחל מאפס")
    args = ap.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)
    if args.reset:
        for p in OUTDIR.glob("halacha_part*"):
            p.unlink()
        CKPT.unlink(missing_ok=True)
        print("[reset] כל החלקים וה-checkpoint נמחקו")

    works = load_works()
    done, last_part = _load_ckpt()
    remaining = [w for w in works if w["title"] not in done]

    if args.plan or not remaining:
        from collections import Counter
        per = Counter(w["period"] for w in works)
        print(f"📚 סה\"כ חיבורי הלכה: {len(works):,}  | לפי תקופה: {dict(per)}")
        print(f"✅ הושלמו: {len(done):,} חיבורים ב-{last_part} חלקים")
        print(f"⏳ נותרו: {len(remaining):,} חיבורים  (~{math.ceil(len(remaining)/max(args.batch,1))} חלקים נוספים של {args.batch})")
        if not remaining and not args.plan:
            print("\n🎉 ALL WORKS DONE — אין מה לייבא")
        return

    batch_works = remaining[:args.batch]
    part_no = last_part + 1
    print(f"📦 part {part_no:02d}: מייבא {len(batch_works)} חיבורים "
          f"({len(done)+1}–{len(done)+len(batch_works)} מתוך {len(works)})")

    part_chunks: list[dict] = []
    ckpt_lines: list[dict] = []
    for j, work in enumerate(batch_works, 1):
        title = work["title"]
        print(f"  [{j}/{len(batch_works)}] 📖 {title}  ({work['period']})")
        bases = leaf_ref_bases(title, work["he_title"])
        time.sleep(0.2)
        w_count = 0
        for en_ref, _he_ref, section_en in bases:
            res = fetch_text(en_ref)
            if not res or not res[0]:
                time.sleep(0.2)
                continue
            new = build_chunks(work, en_ref, section_en, *res)
            part_chunks.extend(new)
            w_count += len(new)
            time.sleep(0.35)
        ckpt_lines.append({"title": title, "part": part_no, "halacha": w_count})
        print(f"      → {w_count:,} segments  (part total: {len(part_chunks):,})")

    _write_part(part_no, part_chunks)
    with CKPT.open("a", encoding="utf-8") as f:
        for rec in ckpt_lines:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    left = len(remaining) - len(batch_works)
    print(f"\n✅ part {part_no:02d} done — {len(part_chunks):,} chunks. "
          f"נותרו {left:,} חיבורים (~{math.ceil(left/max(args.batch,1))} חלקים).")
    if left:
        print(f"➡️  הרץ שוב:  python scripts/fetch_halacha.py --next {args.batch}")
    else:
        print("🎉 ALL WORKS DONE")


if __name__ == "__main__":
    build()
