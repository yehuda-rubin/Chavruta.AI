# -*- coding: utf-8 -*-
"""
fetch_shut.py — מוריד את כל ספריית השו"ת (Responsa) מ-Sefaria.
──────────────────────────────────────────────────────────────────────
מייבא את קטגוריית "Responsa" המלאה (גאונים · ראשונים · אחרונים · מודרני),
בדיוק באותו פורמט צ'אנקים כמו mishnah_chunks.json / gemara_chunks.json:

    {"id", "document", "metadata": {verse_id, book, chapter, verse,
        chunk_type, commentator, work, period, author_he, section,
        text_he, text_en}}

צ'אנק = יחידת ספריא הטבעית (segment/paragraph) — אותו עיקרון כמו הגמרא.
  • chunk_type = "responsa"   ·  work = "responsa"
  • period     = geonim / rishonim / acharonim / modern  (לפי תת-הקטגוריה ב-Sefaria)

תומך בשני סוגי מבנה ב-Sefaria:
  • simple  — שו"ת עם סימנים ישירות   (נטען בשליפה אחת של כל החיבור)
  • complex — שו"ת המחולק לחלקים/או"ח-יו"ד-וכו' (נשלף לכל leaf-node לפי ה-schema)

קישור עמוק: https://www.sefaria.org/{verse_id}  (verse_id בפורמט URL של ספריא)

הרצה:
    python scripts/fetch_shut.py                       # הכל (102 חיבורים)
    python scripts/fetch_shut.py --works "Chakham Tzvi" "Noda BiYehudah I"
    python scripts/fetch_shut.py --reset               # מחק checkpoint והתחל מחדש
    python scripts/fetch_shut.py --limit 3             # 3 חיבורים ראשונים (בדיקה)
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}
OUT = Path("data/processed/shut_chunks.json")
JSONL = Path("data/processed/shut_chunks.jsonl")          # ← הקובץ שהמחברת מושכת
CKPT = Path("data/processed/shut_checkpoint.jsonl")        # שורה לכל חיבור שהושלם

# תת-קטגוריה ב-Sefaria → תקופה (תואם source_kinds בתבניות השו"ת)
PERIOD = {
    "Geonim": "geonim",
    "Rishonim": "rishonim",
    "Acharonim": "acharonim",
    "Modern": "modern",
}

_session = requests.Session()
_session.headers.update(HEADERS)


# ── Sefaria API ──────────────────────────────────────────────────────────────


def _get_json(path: str, params: dict | None = None, retries: int = 3):
    """GET /api/<path> → json | None (404) — עם backoff על שגיאות זמניות."""
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
    """GET /api/v3/texts/<ref> → (he_nested, en_nested) | None."""
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


# ── catalog: list every Responsa work + its period + Hebrew title ────────────


def load_works(filter_titles: list[str] | None = None) -> list[dict]:
    """Walk the live Responsa table-of-contents → [{title, he_title, period}]."""
    toc = _get_json("index/")
    resp = next(c for c in toc if c.get("category") == "Responsa")
    works: list[dict] = []

    def walk(node: dict, period: str) -> None:
        # subcategory may refine the period (Geonim/Rishonim/Acharonim/Modern)
        period = PERIOD.get(node.get("category", ""), period)
        for ch in node.get("contents", []):
            if "contents" in ch:
                walk(ch, period)
            elif ch.get("title"):
                works.append({
                    "title": ch["title"],
                    "he_title": ch.get("heTitle", ""),
                    "period": period,
                })

    walk(resp, "acharonim")  # works sitting directly under Responsa default to acharonim
    if filter_titles:
        want = set(filter_titles)
        works = [w for w in works if w["title"] in want]
    return works


# ── schema → leaf ref-bases (handles simple + complex works) ─────────────────


def _node_titles(node: dict) -> tuple[str, str]:
    """Primary (en, he) titles of a schema node."""
    en = he = ""
    for t in node.get("titles", []):
        if t.get("primary"):
            if t.get("lang") == "en":
                en = t.get("text", "")
            elif t.get("lang") == "he":
                he = t.get("text", "")
    return en or node.get("key", ""), he


def leaf_ref_bases(title: str, he_title: str) -> list[tuple[str, str, str]]:
    """Every leaf node's (en_ref_base, he_ref_base, section_en).

    simple work  → one base == the title.
    complex work → walk schema.nodes; a non-default named node appends ", <title>"
    to the ref (e.g. "Noda BiYehudah I, Orach Chaim") — the exact ref Sefaria expects.
    """
    idx = _get_json(f"v2/raw/index/{urllib.parse.quote(title)}")
    schema = (idx or {}).get("schema", {})

    out: list[tuple[str, str, str]] = []

    def walk(node: dict, en_ref: str, he_ref: str, section_en: str) -> None:
        if "nodes" in node:  # internal schema node — descend
            for ch in node["nodes"]:
                en_t, he_t = _node_titles(ch)
                if ch.get("default") or not en_t:
                    walk(ch, en_ref, he_ref, section_en)
                else:
                    walk(ch, f"{en_ref}, {en_t}",
                         f"{he_ref}, {he_t}" if he_t else he_ref,
                         en_t if not section_en else f"{section_en} / {en_t}")
        else:  # leaf JaggedArrayNode — a fetchable text
            out.append((en_ref, he_ref, section_en))

    if "nodes" in schema:
        walk(schema, title, he_title, "")
    else:
        out.append((title, he_title, ""))   # plain simple work
    return out


# ── chunk builder ────────────────────────────────────────────────────────────


def _seg(x) -> str:
    """מיישר כל רמות קינון למחרוזת אחת."""
    if isinstance(x, list):
        return " ".join(_seg(i) for i in x if i).strip()
    return (x or "").strip() if isinstance(x, str) else ""


def _walk_leaves(he, en, path: list[int]):
    """Recurse he/en in lock-step → yield (path, he_leaf, en_leaf) at each segment."""
    if isinstance(he, list):
        for i, sub in enumerate(he):
            en_sub = en[i] if isinstance(en, list) and i < len(en) else None
            yield from _walk_leaves(sub, en_sub, path + [i + 1])
    else:
        yield path, (he or "") if isinstance(he, str) else "", \
            (en if isinstance(en, str) else "")


def build_chunks(work: dict, en_ref: str, he_ref: str, section_en: str,
                 he_nested, en_nested) -> list[dict]:
    """One Sefaria segment → one chunk, format-identical to mishnah/gemara."""
    book = work["title"]
    he_book = work["he_title"] or book
    out: list[dict] = []
    for path, he_t, en_t in _walk_leaves(he_nested, en_nested, []):
        he_t, en_t = _seg(he_t), _seg(en_t)
        if not (he_t or en_t):
            continue
        path_str = ".".join(str(p) for p in path) or "1"
        ref_label = f"{en_ref} {':'.join(str(p) for p in path)}".strip()
        verse_id = f"{en_ref}.{path_str}".replace(" ", "_")   # Sefaria URL form
        doc = f"[{he_book}] {ref_label}\n{he_t}\n{en_t}".strip()
        out.append({
            "id": f"{verse_id}_responsa",
            "document": doc,
            "metadata": {
                "verse_id": verse_id,
                "book": book,
                "chapter": path[0] if path else 1,
                "verse": path[-1] if path else 1,
                "chunk_type": "responsa",
                "commentator": "",
                "work": "responsa",
                "period": work["period"],
                "author_he": he_book,
                "section": section_en,
                "text_he": he_t,
                "text_en": en_t,
            },
        })
    return out


# ── checkpoint / resume (same pattern as fetch_gemara.py) ────────────────────


def _load_ckpt() -> tuple[set[str], dict[str, int]]:
    done: set[str] = set()
    stats = {"responsa": 0, "fetched": 0, "missing": 0}
    if not CKPT.exists():
        return done, stats
    for line in CKPT.open(encoding="utf-8"):
        rec = json.loads(line)
        done.add(rec["title"])
        for k in stats:
            stats[k] += rec.get(k, 0)
    print(f"[resume] {len(done)} חיבורים כבר בוצעו")
    return done, stats


def _save_ckpt(title: str, chunks: list[dict], wstats: dict[str, int]) -> None:
    with JSONL.open("a", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with CKPT.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"title": title, **wstats}, ensure_ascii=False) + "\n")


def _assemble(total_works: int, stats: dict[str, int]) -> None:
    """JSONL → קובץ JSON סופי (כתיבה זורמת, לא טוען הכל לזיכרון)."""
    if not JSONL.exists():
        return
    total = sum(1 for _ in JSONL.open(encoding="utf-8"))
    print(f"[assemble] כותב {total:,} צ'אנקים ל-{OUT} …")
    header = json.dumps({"metadata": {
        "total_chunks": total,
        "works": total_works,
        "by_type": {"responsa": stats.get("responsa", 0)},
        "works_fetched": stats["fetched"],
        "works_missing": stats["missing"],
    }}, ensure_ascii=False)
    with OUT.open("w", encoding="utf-8") as fout:
        fout.write(header[:-1] + ', "chunks": [\n')
        with JSONL.open(encoding="utf-8") as fin:
            for j, line in enumerate(fin):
                fout.write(line.rstrip("\n"))
                fout.write(",\n" if j + 1 < total else "\n")
        fout.write("]}\n")
    print(f"💾 {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")


# ── main ─────────────────────────────────────────────────────────────────────


def build() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--works", nargs="*", default=None, help="חיבורים ספציפיים (כותרת אנגלית)")
    ap.add_argument("--limit", type=int, default=None, help="הגבל למספר חיבורים ראשונים")
    ap.add_argument("--reset", action="store_true", help="מחק checkpoint והתחל מחדש")
    ap.add_argument("--no-assemble", action="store_true", help="אל תרכיב את ה-JSON הסופי")
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        CKPT.unlink(missing_ok=True)
        JSONL.unlink(missing_ok=True)
        print("[reset] checkpoint נמחק")

    works = load_works(args.works)
    if args.limit:
        works = works[:args.limit]
    print(f"📚 {len(works)} חיבורי שו\"ת לייבוא")

    done, stats = _load_ckpt()
    remaining = [w for w in works if w["title"] not in done]
    total = len(works)

    for i, work in enumerate(remaining, len(done) + 1):
        title = work["title"]
        print(f"[{i}/{total}] 📖 {title}  ({work['period']})")
        bases = leaf_ref_bases(title, work["he_title"])
        time.sleep(0.2)

        w_chunks: list[dict] = []
        w_stats = {"responsa": 0, "fetched": 0, "missing": 0}
        for en_ref, he_ref, section_en in bases:
            res = fetch_text(en_ref)
            if not res or not res[0]:
                w_stats["missing"] += 1
                time.sleep(0.2)
                continue
            w_stats["fetched"] += 1
            he_nested, en_nested = res
            new = build_chunks(work, en_ref, he_ref, section_en, he_nested, en_nested)
            w_chunks.extend(new)
            w_stats["responsa"] += len(new)
            tag = f" [{section_en}]" if section_en else ""
            print(f"    ✓ {en_ref}{tag}: {len(new)} segments")
            time.sleep(0.4)

        _save_ckpt(title, w_chunks, w_stats)
        for k in stats:
            stats[k] += w_stats.get(k, 0)
        print(f"    → סה\"כ צ'אנקים: {stats['responsa']:,}")

    if not args.no_assemble:
        _assemble(total, stats)
    print(f"\n✅ DONE — {stats['responsa']:,} responsa segments | "
          f"fetched: {stats['fetched']} nodes, missing: {stats['missing']}")
    print(f"📄 JSONL (לקאגל): {JSONL}")


if __name__ == "__main__":
    build()
