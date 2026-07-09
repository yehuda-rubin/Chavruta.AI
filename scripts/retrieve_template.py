# -*- coding: utf-8 -*-
"""retrieve_template.py — pick the lesson template that best fits a topic (NO LLM API).

The "which template?" retrieval layer of Chavruta.AI. Given a lesson request (a topic or short
description), embeds it with bge-m3 and searches the 'chavruta_templates' collection built by
index_templates.py, returning the best-matching template set — its id, genre, and the paths to
its 3 files (source_sheet, lesson_flow, full_lesson). The lesson generator then fills those files
using sources from retrieve_sources.py — all locally, no external LLM API.

    .venv/Scripts/python.exe scripts/retrieve_template.py --query "זמן קריאת שמע של ערבית"
    .venv/Scripts/python.exe scripts/retrieve_template.py --query "מידת הענווה" --k 3 --json
"""

from __future__ import annotations

import torch  # noqa: F401 — MUST be first (native DLL load order)
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
QDRANT_URL = os.environ["CHAVRUTA_QDRANT_URL"]
COLLECTION = os.environ.get("CHAVRUTA_TEMPLATES_COLLECTION", "chavruta_templates")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="lesson topic / short description")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from chavruta.embedding.bge_m3 import BgeM3Embedding
    emb = BgeM3Embedding(use_sparse=False)
    emb.embed_query("warmup")

    from qdrant_client import QdrantClient
    client = QdrantClient(url=QDRANT_URL, timeout=120)
    if not client.collection_exists(COLLECTION):
        print(f"template collection '{COLLECTION}' not found — run scripts/index_templates.py first")
        sys.exit(1)

    e = emb.embed_query(args.query)
    res = client.query_points(collection_name=COLLECTION, query=e.dense, limit=args.k, with_payload=True)

    matches = []
    for p in res.points:
        pl = p.payload or {}
        files = {k: f"{pl.get('dir','')}/{v}" for k, v in (pl.get("files") or {}).items()}
        matches.append({
            "score": round(p.score, 4),
            "id": pl.get("id"),
            "genre": pl.get("genre"),
            "title": pl.get("title"),
            "dir": pl.get("dir"),
            "files": files,
            "example_topics": pl.get("example_topics", []),
        })

    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return

    print(f"\nQUERY: {args.query}\n{'='*60}")
    for i, m in enumerate(matches, 1):
        star = "  ← best match" if i == 1 else ""
        print(f"\n[{i}] {m['score']}  {m['id']}  ({m['genre']}){star}")
        print(f"    {m['title']}")
        print(f"    דוגמאות: {', '.join(m['example_topics'])}")
        for role, path in m["files"].items():
            print(f"      {role:13s} {path}")


if __name__ == "__main__":
    main()
