# -*- coding: utf-8 -*-
"""build_lesson.py — end-to-end lesson/teshuva assembler (NO LLM API).

Ties the two retrieval layers of Chavruta.AI into one step:
  1. WHICH TEMPLATE?  — route the topic to its best-fit template (chavruta_templates).
  2. WHICH SOURCES?   — pull relevant sources for the topic (chavruta, hybrid bge-m3).
  3. ASSEMBLE         — write a "work packet" to sample_lessons/<slug>/: the chosen template's
                        file(s) ready to fill + a sources sheet + a build note.

The packet is then filled by the teaching model (Claude) from the retrieved sources — NO external
LLM API is called here or after. Output goes under sample_lessons/ (gitignored, local only).

    docker compose up -d qdrant
    .venv/Scripts/python.exe scripts/build_lesson.py --query "מצות סוכה וטעמה" \
        --query "ישב בסוכה שבעת ימים למען ידעו דורותיכם" --k 6
    .venv/Scripts/python.exe scripts/build_lesson.py --mode shut \
        --query "האם מותר לסחוט לימון לתה בשבת" --k 6
"""

from __future__ import annotations

import torch  # noqa: F401 — MUST be first (native DLL load order; see verify_retrieval.py)
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
QDRANT_URL = os.environ["CHAVRUTA_QDRANT_URL"]
COLLECTION_TPL = os.environ.get("CHAVRUTA_TEMPLATES_COLLECTION", "chavruta_templates")
COLLECTION_SRC = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")


def _slugify(text: str) -> str:
    s = re.sub(r'["\'\\/:*?<>|]+', "", text).strip()
    s = re.sub(r"\s+", "-", s)
    return s[:48] or "lesson"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", required=True,
                    help="repeatable; the FIRST query also routes the template")
    ap.add_argument("--mode", choices=["lesson", "shut", "all"], default="lesson")
    ap.add_argument("--k", type=int, default=6, help="sources per query")
    ap.add_argument("--out", default=None, help="output dir (default sample_lessons/<slug>)")
    args = ap.parse_args()

    from chavruta.embedding.bge_m3 import BgeM3Embedding
    emb = BgeM3Embedding(use_sparse=True)  # dense for template routing, dense+sparse for sources
    emb.embed_query("warmup")

    from qdrant_client import QdrantClient, models
    from chavruta.store.qdrant_store import QdrantStore
    from chavruta.store.base import HybridQuery
    client = QdrantClient(url=QDRANT_URL, timeout=120)
    store = QdrantStore(mode="server", url=QDRANT_URL)

    # ---- 1) WHICH TEMPLATE? (route on the primary query) ----
    primary = args.query[0]
    et = emb.embed_query(primary)
    tfilter = None
    if args.mode != "all":
        tfilter = models.Filter(must=[
            models.FieldCondition(key="mode", match=models.MatchValue(value=args.mode))])
    tres = client.query_points(collection_name=COLLECTION_TPL, query=et.dense, limit=1,
                               query_filter=tfilter, with_payload=True)
    if not tres.points:
        print(f"no template found for mode={args.mode}")
        sys.exit(1)
    tpl = tres.points[0].payload or {}
    tpl_dir = REPO / tpl["dir"]
    print(f"► template: {tpl['id']} [{tpl.get('mode','lesson')}] ({tpl.get('genre','')})  "
          f"score={tres.points[0].score:.4f}")

    # ---- 2) WHICH SOURCES? (hybrid, dedup by ref across queries) ----
    by_ref = {}
    for q in args.query:
        e = emb.embed_query(q)
        for h in store.search(COLLECTION_SRC, HybridQuery(dense=e.dense, sparse=e.sparse), top_k=args.k):
            p = h.payload or {}
            ref = p.get("ref", "?")
            if ref not in by_ref or h.score > by_ref[ref][0]:
                by_ref[ref] = (h.score, p)
    sources = sorted(by_ref.values(), key=lambda x: -x[0])
    print(f"► sources: {len(sources)} unique (from {len(args.query)} queries)")

    # ---- 3) ASSEMBLE the work packet ----
    out = Path(args.out) if args.out else (REPO / "sample_lessons" / _slugify(primary))
    out.mkdir(parents=True, exist_ok=True)

    # copy the template file(s) → working files named by role (source_sheet/lesson_flow/full_lesson/answer)
    roles = []
    for role, fname in (tpl.get("files") or {}).items():
        src = tpl_dir / fname
        dst = out / f"{role}.md"
        if src.exists():
            shutil.copyfile(src, dst)
            roles.append(f"{role}.md")

    # sources sheet
    src_lines = [f"# מקורות שנשלפו — {primary}", "",
                 f"*תבנית: `{tpl['id']}` · מצב: {tpl.get('mode','lesson')} · {len(sources)} מקורות*", ""]
    for i, (score, p) in enumerate(sources, 1):
        who = f" [{p['commentator_id']}]" if p.get("commentator_id") not in (None, "None") else ""
        txt = (p.get("text_he") or p.get("text") or "").strip()
        src_lines += [f"## [{i}] {p.get('ref','?')}{who}  ({p.get('work_id','')})  score={score:.3f}",
                      f"🔗 {p.get('deep_link','')}", "", txt, ""]
    (out / "_sources.md").write_text("\n".join(src_lines), encoding="utf-8")

    # build note (instructions to the model)
    note = [
        f"# חבילת בנייה — {primary}", "",
        f"- **תבנית שנבחרה:** `{tpl['id']}`  ({tpl.get('genre','')})",
        f"- **מצב:** {tpl.get('mode','lesson')}",
        f"- **מבנה:** {tpl.get('structure','')}",
        f"- **שאילתות:** {' | '.join(args.query)}",
        f"- **מקורות:** {len(sources)} (ב-`_sources.md`)",
        f"- **קבצים למילוי:** {', '.join(roles)}", "",
        "## הוראות למודל (Claude)",
        "מלא את קבצי התבנית שהועתקו לכאן מתוך `_sources.md` בלבד. **אין להשתמש ב-API חיצוני** —",
        "המודל הוא הכותב. כל ציטוט חייב ref + deep_link אמיתיים מ-`_sources.md`. אם המקורות אינם",
        "מספיקים לשער מסוים — אמור זאת במפורש, אל תמציא. שמור על סדר השערים של התבנית.",
    ]
    (out / "_build.md").write_text("\n".join(note), encoding="utf-8")

    print(f"► packet: {out.relative_to(REPO)}")
    print(f"   files to fill: {', '.join(roles)}")
    print(f"   + _sources.md ({len(sources)} sources) + _build.md")
    print("\n✅ ready — the model now fills the template file(s) from _sources.md (no API).")


if __name__ == "__main__":
    main()
