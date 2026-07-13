# -*- coding: utf-8 -*-
"""Diagnostic: what does the retriever actually return for the routed query (server mode)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.config.profile import Profile
from chavruta.corpus.schema import Query
from chavruta.intents.router import Router
from chavruta.pipeline.pipeline import build_backends

Q = "מה המחלוקת בין רשי לרמבן בפסוק הראשון בתורה?"

p = Profile(name="local", qdrant_mode="server", qdrant_url="http://localhost:6333",
            collection="chavruta", hybrid=True, rerank=False,
            relevance_threshold=0.0, top_k=16, embedding_device="cpu", llm_backend="nebius")
emb, store, llm, retriever = build_backends(p)

q = Router().route(Query(text=Q))
print("named_refs:", q.named_refs, "| commentators:", q.commentator_ids, "| intent:", q.intent.value)
res = retriever.retrieve(q, top_k=16)
print(f"is_empty={res.is_empty} hits={len(res.hits)}")
for h in res.hits:
    print(f"  {h.score:.4f}  {h.commentator_id or '-':14}  {h.ref}")
