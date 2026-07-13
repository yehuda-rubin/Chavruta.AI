# -*- coding: utf-8 -*-
"""verify_retrieval.py — direct RAG retrieval check (NO LLM API at all).

Confirms the local Qdrant actually RETURNS relevant sources for real HE/EN questions,
using bge-m3 (dense+sparse) + hybrid RRF search — the exact retrieval path the app uses,
but WITHOUT constructing the full pipeline (which drags in sklearn+datasets and hits a
pyarrow access-violation on this box). `import torch` first fixes the native DLL load order.

    .venv/Scripts/python.exe scripts/verify_retrieval.py
"""

from __future__ import annotations

import torch  # noqa: F401 — MUST be first: fixes native DLL load order (pyarrow crash otherwise)
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")

QUERIES = [
    ("he", "מה אומר רש\"י על בריאת האור בבראשית?"),
    ("he", "מאימתי קורין את שמע בערבית?"),
    ("he", "דיני מוקצה בשבת"),
    ("he", "מחלוקת בית שמאי ובית הלל בברכות"),
    ("he", "כיצד מברכים על הדלקת נר חנוכה?"),
    ("en", "What does Ramban say about the beginning of creation?"),
]


def main() -> None:
    from chavruta.embedding.bge_m3 import BgeM3Embedding

    # Load the embedding model FIRST — i.e. import FlagEmbedding (→datasets→pyarrow) before
    # qdrant_client. Importing qdrant_client first leaves the process in a state where
    # pyarrow.dataset segfaults (access violation) on this box. Order fixes it.
    print("loading bge-m3 (dense+sparse)…", flush=True)
    emb = BgeM3Embedding(use_sparse=True)
    emb.embed_query("warmup")  # force model load once
    print("model ready.\n", flush=True)

    from chavruta.store.qdrant_store import QdrantStore
    from chavruta.store.base import HybridQuery

    url = os.environ["CHAVRUTA_QDRANT_URL"]
    print(f"collection={COLLECTION} qdrant={url}", flush=True)
    store = QdrantStore(mode="server", url=url)
    total = store.count(COLLECTION)
    print(f"points={total:,}\n", flush=True)

    all_ok = True
    for lang, q in QUERIES:
        e = emb.embed_query(q)
        hq = HybridQuery(dense=e.dense, sparse=e.sparse)
        hits = store.search(COLLECTION, hq, top_k=5)
        ok = len(hits) > 0
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] ({lang}) {q}", flush=True)
        for h in hits:
            p = h.payload or {}
            who = f" [{p['commentator_id']}]" if p.get("commentator_id") not in (None, "None") else ""
            snippet = (p.get("text_he") or p.get("text") or "").replace("\n", " ")[:70]
            print(f"    {h.score:.4f}  {p.get('ref','?')}{who}  {snippet}", flush=True)
        print(flush=True)

    print("=" * 60)
    print("✅ retrieval returns hits for all queries" if all_ok else "❌ some queries returned nothing")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
