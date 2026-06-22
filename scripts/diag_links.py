# -*- coding: utf-8 -*-
"""Diagnose links-graph connectivity + link-expansion for the lesson sources."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.config.profile import Profile
from chavruta.corpus.schema import Intent, Query
from chavruta.pipeline.pipeline import build_backends

p = Profile(name="local", qdrant_mode="server", qdrant_url="http://localhost:6333",
            collection="chavruta", hybrid=True, embedding_device="cpu", llm_backend="nebius")
emb, store, llm, retr = build_backends(p)
le = getattr(retr, "link_expander", None)
g = getattr(le, "link_graph", None) or getattr(le, "graph", None)
print("link_expander:", type(le).__name__ if le else None, "| graph:", type(g).__name__ if g else None)

PROBE = [
    "Mishnah Bava Metzia.1.1", "Bava Metzia.2a", "Bava Metzia.2a.1",
    "Bava Metzia.60b.11", "Bava Metzia.60b",
]
if g is not None:
    for ref in PROBE:
        nb = list(g.neighbours(ref)) if hasattr(g, "neighbours") else []
        d1 = list(g.expand([ref], depth=1))
        d2 = list(g.expand([ref], depth=2))
        print(f"\n{ref!r}: neighbours={len(nb)} depth1={len(d1)} depth2={len(d2)}")
        for n in d1[:6]:
            print("   d1:", n)

# What does the LinkExpander actually return for the opening source we picked?
if le is not None:
    q = Query(text="שניים אוחזין בטלית", intent=Intent.LESSON, expand_links=True, expand_depth=2)
    for src in ["Bava Metzia.60b.11", "Bava Metzia.2a", "Mishnah Bava Metzia.1.1"]:
        try:
            hits = le.expand([src], q)
            print(f"\nexpand([{src!r}]) -> {len(hits)} hits")
            for h in hits[:5]:
                print(f"   {h.score:.3f} {h.ref}")
        except Exception as ex:
            import traceback; traceback.print_exc()
