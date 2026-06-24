# -*- coding: utf-8 -*-
"""
fetch_category.py — מוריד **כל קטגוריה עליונה** של ספריא לאותו פורמט צ'אנקים.
──────────────────────────────────────────────────────────────────────────────
הכללה של fetch_halacha.py: במקום לקודד "Halakhah", מקבל --category כלשהו ומייצר
בדיוק אותו פורמט (zהה ל-mishnah/gemara/shut/halacha):

    {"id", "document", "metadata": {verse_id, book, chapter, verse, chunk_type,
        commentator, work, period, author_he, section, category_path,
        text_he, text_en}}

  • chunk_type = work = <slug>   (Midrash→"midrash", "Jewish Thought"→"jewish_thought")
  • period     = תת-הקטגוריה אם היא Geonim/Rishonim/Acharonim/Modern, אחרת = <slug>

הקטגוריות שכבר ייבאנו (לא להריץ עליהן): Tanakh · Mishnah · Talmud · Halakhah · Responsa.
הנותרות:  Midrash · Kabbalah · Liturgy · Jewish Thought · Tosefta · Chasidut ·
          Musar · Second Temple · Reference.

הרצה:
    python scripts/fetch_category.py --category Musar --plan        # סטטוס בלבד
    python scripts/fetch_category.py --category Musar --all         # כל הקטגוריה (resumable)
    python scripts/fetch_category.py --category Midrash --next 50   # 50 חיבורים → part אחד
    python scripts/fetch_category.py --category Midrash --reset      # התחל מאפס

כל חלק נשמר ל-data/processed/<slug>/<slug>_partNN.jsonl (+ .json) — עצמאי, מוכן
להעלאה ל-HF ולהרצת ה-Nebius embed job (CORPUS_PREFIX=<slug>_part).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.parse
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}

# קטגוריות שכבר ייבאנו בנפרד — להגנה מפני הרצה כפולה.
ALREADY_DONE = {"Tanakh", "Mishnah", "Talmud", "Halakhah", "Responsa"}

# תת-קטגוריות "תקופה" שמופיעות בכמה ענפים — דורסות את ברירת המחדל (=slug) כשנפגשות.
PERIOD_OVERRIDE = {
    "Geonim": "geonim",
    "Rishonim": "rishonim",
    "Acharonim": "acharonim",
    "Modern": "modern",
}

_session = requests.Session()
_session.headers.update(HEADERS)


def slugify(category: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")


# ── Sefaria API (זהה ל-fetch_halacha.py) ─────────────────────────────────────


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


# ── catalog: every work in <category> + period + category path ───────────────


def load_works(category: str) -> list[dict]:
    """Walk the live <category> TOC → ordered [{title, he_title, period, category_path}]."""
    toc = _get_json("index/")
    try:
        root = next(c for c in toc if c.get("category") == category)
    except StopIteration:
        avail = sorted(c.get("category", "") for c in toc if c.get("category"))
        raise SystemExit(f"❌ קטגוריה '{category}' לא נמצאה. זמינות: {', '.join(avail)}")
    default_period = slugify(category)
    works: list[dict] = []

    def walk(node: dict, period: str, path: list[str]) -> None:
        cat = node.get("category", "")
        period = PERIOD_OVERRIDE.get(cat, period)
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

    walk(root, default_period, [])
    return works


# ── schema → leaf ref-bases (זהה ל-fetch_halacha.py) ─────────────────────────


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


# ── chunk builder (זהה ל-fetch_halacha.py, chunk_type=<slug>) ────────────────


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


def build_chunks(work: dict, slug: str, en_ref: str, section_en: str,
                 he_nested, en_nested) -> list[dict]:
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
            "id": f"{verse_id}_{slug}",
            "document": doc,
            "metadata": {
                "verse_id": verse_id,
                "book": book,
                "chapter": path[0] if path else 1,
                "verse": path[-1] if path else 1,
                "chunk_type": slug,
                "commentator": "",
                "work": slug,
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


def _load_ckpt(ckpt: Path) -> tuple[set[str], int]:
    """→ (done_titles, last_part_no)."""
    done: set[str] = set()
    last_part = 0
    if not ckpt.exists():
        return done, last_part
    for line in ckpt.open(encoding="utf-8"):
        rec = json.loads(line)
        done.add(rec["title"])
        last_part = max(last_part, rec.get("part", 0))
    return done, last_part


def _write_part(outdir: Path, slug: str, part_no: int, chunks: list[dict]) -> None:
    jsonl = outdir / f"{slug}_part{part_no:02d}.jsonl"
    js = outdir / f"{slug}_part{part_no:02d}.json"
    with jsonl.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    payload = {"metadata": {"total_chunks": len(chunks), "part": part_no,
                            "by_type": {slug: len(chunks)}}, "chunks": chunks}
    js.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"💾 part {part_no:02d}: {len(chunks):,} chunks → {jsonl}  ({jsonl.stat().st_size/1e6:.1f} MB)")


# ── one batch → one part ─────────────────────────────────────────────────────


def _run_batch(works: list[dict], outdir: Path, slug: str, ckpt: Path, batch: int) -> int:
    """ייבא את ה-batch הבא לחלק חדש. → מספר החיבורים שנותרו אחריו."""
    done, last_part = _load_ckpt(ckpt)
    remaining = [w for w in works if w["title"] not in done]
    if not remaining:
        return 0

    batch_works = remaining[:batch]
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
            new = build_chunks(work, slug, en_ref, section_en, *res)
            part_chunks.extend(new)
            w_count += len(new)
            time.sleep(0.35)
        ckpt_lines.append({"title": title, "part": part_no, slug: w_count})
        print(f"      → {w_count:,} segments  (part total: {len(part_chunks):,})")

    _write_part(outdir, slug, part_no, part_chunks)
    with ckpt.open("a", encoding="utf-8") as f:
        for rec in ckpt_lines:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    left = len(remaining) - len(batch_works)
    print(f"✅ part {part_no:02d} done — {len(part_chunks):,} chunks. נותרו {left:,} חיבורים.")
    return left


# ── main ─────────────────────────────────────────────────────────────────────


def build() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", required=True, help="קטגוריה עליונה ב-Sefaria (Midrash, Kabbalah, ...)")
    ap.add_argument("--next", type=int, default=50, dest="batch", help="כמה חיבורים בכל חלק")
    ap.add_argument("--all", action="store_true", help="הרץ עד שהקטגוריה כולה נגמרת (resumable)")
    ap.add_argument("--plan", action="store_true", help="הצג סטטוס ויציאה")
    ap.add_argument("--reset", action="store_true", help="מחק הכל והתחל מאפס")
    ap.add_argument("--force", action="store_true", help="אפשר גם קטגוריה שכבר ייבאנו")
    args = ap.parse_args()

    if args.category in ALREADY_DONE and not args.force:
        raise SystemExit(f"⚠️  '{args.category}' כבר יובאה בנפרד. השתמש ב---force אם בכוונה.")

    slug = slugify(args.category)
    outdir = Path("data/processed") / slug
    ckpt = outdir / "_checkpoint.jsonl"
    outdir.mkdir(parents=True, exist_ok=True)

    if args.reset:
        for p in outdir.glob(f"{slug}_part*"):
            p.unlink()
        ckpt.unlink(missing_ok=True)
        print(f"[reset] {slug}: כל החלקים וה-checkpoint נמחקו")

    works = load_works(args.category)
    done, last_part = _load_ckpt(ckpt)
    remaining = [w for w in works if w["title"] not in done]

    if args.plan:
        from collections import Counter
        per = Counter(w["period"] for w in works)
        print(f"📚 {args.category} (slug={slug}) — סה\"כ חיבורים: {len(works):,} | תקופות: {dict(per)}")
        print(f"✅ הושלמו: {len(done):,} ב-{last_part} חלקים | ⏳ נותרו: {len(remaining):,} "
              f"(~{math.ceil(len(remaining)/max(args.batch,1))} חלקים של {args.batch})")
        return

    if not remaining:
        print(f"🎉 {args.category}: ALL WORKS DONE — אין מה לייבא")
        return

    if args.all:
        left = len(remaining)
        while left > 0:
            left = _run_batch(works, outdir, slug, ckpt, args.batch)
        print(f"\n🎉 {args.category}: ALL WORKS DONE")
    else:
        left = _run_batch(works, outdir, slug, ckpt, args.batch)
        if left:
            print(f"➡️  הרץ שוב:  python scripts/fetch_category.py --category {args.category} --next {args.batch}")
        else:
            print(f"🎉 {args.category}: ALL WORKS DONE")


if __name__ == "__main__":
    build()
