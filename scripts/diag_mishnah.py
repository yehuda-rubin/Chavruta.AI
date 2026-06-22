# -*- coding: utf-8 -*-
"""Is Mishnah Bava Metzia.1.1 even retrievable for its own opening words?"""
import sys, unicodedata
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.config.profile import Profile
from chavruta.pipeline.pipeline import build_backends
from chavruta.retrieval.hybrid import _to_hit
from chavruta.store.base import HybridQuery

p = Profile(name="local", qdrant_mode="server", qdrant_url="http://localhost:6333",
            collection="chavruta", hybrid=True, embedding_device="cpu", llm_backend="nebius")
emb, store, llm, retr = build_backends(p)

# 1) Fetch the mishnah directly by ref — does it exist, and what's its text?
hits = store.fetch_by_refs("chavruta", ["Mishnah Bava Metzia.1.1"])
print("fetch_by_refs(Mishnah Bava Metzia.1.1):", len(hits), "hit(s)")
mtext = None
for h in hits:
    hh = _to_hit(h)
    mtext = hh.text
    has_nikud = any(unicodedata.category(c) == "Mn" for c in hh.text)
    print(f"  ref={hh.ref} unit={getattr(hh,'unit_type',None)} work={hh.work_id} nikud={has_nikud}")
    print("  text:", hh.text[:90])

def strip_nikud(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

# 2) Rank of the mishnah when we search by its OWN text (nikud-stripped) — work-scoped to mishnah
for label, q in [("topic", "שניים אוחזין בטלית"),
                 ("mishnah-own-text", strip_nikud(mtext) if mtext else "שניים אוחזין בטלית")]:
    e = emb.embed_query(q)
    raw = store.search("chavruta", HybridQuery(dense=e.dense, sparse=e.sparse),
                       top_k=8, filters={"unit_type": "source", "work_id": ["mishnah"]})
    print(f"\n[{label}] mishnah-only top-8 (sparse terms={len(e.sparse or {})}):")
    for h in raw:
        hh = _to_hit(h)
        mark = "  <== TARGET" if hh.ref == "Mishnah Bava Metzia.1.1" else ""
        print(f"   {hh.score:.4f} {hh.ref}{mark}")
