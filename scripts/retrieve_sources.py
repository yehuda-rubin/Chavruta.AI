# -*- coding: utf-8 -*-
"""retrieve_sources.py — pull real sources from the local RAG for lesson building (NO LLM API).

Given one or more queries (and optional work_id filter), runs bge-m3 hybrid search against the
local Qdrant and prints the top hits with FULL Hebrew text + reference + deep link. This is the
retrieval feed that Claude (acting as the teaching model) turns into a source sheet / lesson —
generation is done by Claude from these outputs, never by an external LLM.

    .venv/Scripts/python.exe scripts/retrieve_sources.py --k 6 \
        --query "מאימתי קורין את שמע בערבית" \
        --query "זמן קריאת שמע של ערבית רבן גמליאל"
    # optional: --work halacha   (restrict to one work_id)   --json  (machine-readable)
"""

from __future__ import annotations

import torch  # noqa: F401 — MUST be first (fixes native DLL load order; see verify_retrieval.py)
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", required=True, help="repeatable")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--work", default=None, help="restrict to a work_id (e.g. halacha, tanakh)")
    ap.add_argument("--full", action="store_true", help="print full text (not truncated)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # embedder first (FlagEmbedding) — then qdrant_client
    from chavruta.embedding.bge_m3 import BgeM3Embedding
    emb = BgeM3Embedding(use_sparse=True)
    emb.embed_query("warmup")

    from chavruta.store.qdrant_store import QdrantStore
    from chavruta.store.base import HybridQuery
    store = QdrantStore(mode="server", url=os.environ["CHAVRUTA_QDRANT_URL"])

    out = []
    for q in args.query:
        e = emb.embed_query(q)
        hq = HybridQuery(dense=e.dense, sparse=e.sparse)
        filt = {"work_id": args.work} if args.work else None
        hits = store.search(COLLECTION, hq, top_k=args.k, filters=filt)
        block = {"query": q, "hits": []}
        for h in hits:
            p = h.payload or {}
            txt = (p.get("text_he") or p.get("text") or "").strip()
            block["hits"].append({
                "score": round(h.score, 4),
                "ref": p.get("ref", "?"),
                "commentator": None if p.get("commentator_id") in (None, "None") else p.get("commentator_id"),
                "work_id": p.get("work_id"),
                "deep_link": p.get("deep_link", ""),
                "text_he": txt if args.full else txt[:280],
            })
        out.append(block)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    for block in out:
        print(f"\n{'='*70}\nQUERY: {block['query']}\n{'='*70}")
        for i, h in enumerate(block["hits"], 1):
            who = f"  [{h['commentator']}]" if h["commentator"] else ""
            print(f"\n[{i}] {h['score']}  {h['ref']}{who}  ({h['work_id']})")
            print(f"    {h['deep_link']}")
            print(f"    {h['text_he']}")


if __name__ == "__main__":
    main()
