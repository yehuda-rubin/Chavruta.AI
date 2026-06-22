# -*- coding: utf-8 -*-
"""Diagnose the lesson opening-source retrieval (unit_type=source) for a topic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.config.profile import Profile
from chavruta.pipeline.pipeline import build_backends
from chavruta.retrieval.hybrid import _to_hit
from chavruta.store.base import HybridQuery

TOPIC = "שניים אוחזין בטלית"

p = Profile(name="local", qdrant_mode="server", qdrant_url="http://localhost:6333",
            collection="chavruta", hybrid=True, embedding_device="cpu", llm_backend="nebius")
emb, store, llm, retr = build_backends(p)
e = emb.embed_query(TOPIC)
print("sparse terms:", len(e.sparse or {}))
try:
    print("--- generic unit_type=source ---")
    raw = store.search("chavruta", HybridQuery(dense=e.dense, sparse=e.sparse),
                       top_k=4, filters={"unit_type": "source"})
    for h in raw:
        hh = _to_hit(h)
        print(f"  {hh.score:.4f} work={hh.work_id:12} ref={hh.ref}")
    print("--- WORK-SCOPED source (mishnah/talmud_bavli) — the opening fix ---")
    raw2 = store.search("chavruta", HybridQuery(dense=e.dense, sparse=e.sparse),
                        top_k=6, filters={"unit_type": "source", "work_id": ["mishnah", "talmud_bavli"]})
    for h in raw2:
        hh = _to_hit(h)
        print(f"  {hh.score:.4f} work={hh.work_id:12} ref={hh.ref}  | {hh.text[:30]}")
except Exception as ex:
    import traceback; traceback.print_exc()
    print("ERROR:", ex)
