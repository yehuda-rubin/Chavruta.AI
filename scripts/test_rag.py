# -*- coding: utf-8 -*-
"""test_rag.py — end-to-end smoke test for the LOCAL RAG (retrieval local, LLM on Nebius).

Runs REAL queries against the live local Qdrant and prints REAL results — it never asserts
success without observing it. Three stages (all on by default):

  1. store      — collection health + total point count + per-work coverage counts.
  2. retrieval  — embed a set of HE/EN questions with bge-m3, hybrid-search, print top hits.
  3. ask        — full pipeline (retrieval + Nebius generation) for one question. Needs a
                  NEBIUS_API_KEY; skipped with a note if absent.

Run (after the load finishes, with Qdrant up):
    python scripts/test_rag.py                 # all stages
    python scripts/test_rag.py --no-ask        # skip the LLM call (retrieval only, no key needed)
    python scripts/test_rag.py --stage store   # just the coverage counts
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Force the local retrieval profile regardless of shell state; LLM stays Nebius.
os.environ.setdefault("CHAVRUTA_PROFILE", "local")
os.environ.setdefault("CHAVRUTA_QDRANT_MODE", "server")
os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("CHAVRUTA_HYBRID", "true")

QUERIES = [
    ("he", "מה אומר רש\"י על בריאת האור בבראשית?"),
    ("he", "מאימתי קורין את שמע בערבית?"),
    ("he", "דיני מוקצה בשבת"),
    ("he", "מחלוקת בית שמאי ובית הלל בברכות"),
    ("en", "What does Ramban say about the beginning of creation?"),
]
WORK_TAGS = ["tanakh", "mishnah", "talmud_bavli"]   # known metadata 'work' values to spot-check


def stage_store(profile):
    from qdrant_client import QdrantClient

    print("\n=== STAGE 1: store health & coverage ===")
    c = QdrantClient(url=profile.qdrant_url, timeout=120)
    info = c.get_collection(profile.collection)
    total = c.count(profile.collection, exact=True).count
    print(f"  status={info.status}  points={total:,}")
    ok = total > 2_000_000
    print(f"  [{'PASS' if ok else 'WARN'}] total points {'>' if ok else '<='} 2,000,000")
    from qdrant_client import models
    for w in WORK_TAGS:
        n = c.count(profile.collection, exact=True,
                    count_filter=models.Filter(must=[
                        models.FieldCondition(key="work", match=models.MatchValue(value=w))])).count
        print(f"    work={w:14s} {n:>10,} points  [{'PASS' if n > 0 else 'MISSING'}]")
    return ok


def stage_retrieval(pipeline):
    print("\n=== STAGE 2: retrieval (bge-m3 hybrid, local) ===")
    from chavruta.corpus.schema import Intent, Query

    all_ok = True
    for lang, q in QUERIES:
        query = Query(text=q, lang=lang, intent=Intent.QA)
        query = pipeline._resolve_query(query)
        result = pipeline.retriever.retrieve(query, top_k=5)
        hits = list(result.hits)
        ok = len(hits) > 0
        all_ok = all_ok and ok
        print(f"\n  [{'PASS' if ok else 'FAIL'}] {q}")
        for h in hits[:5]:
            who = f" ({h.commentator_id})" if getattr(h, "commentator_id", None) else ""
            snippet = (getattr(h, "text_he", "") or getattr(h, "text", "") or "")[:60]
            print(f"      {h.score:.3f}  {h.ref}{who}  {snippet}")
    return all_ok


def stage_ask(pipeline):
    print("\n=== STAGE 3: full ask (retrieval + Nebius LLM) ===")
    if not pipeline.profile.llm_api_key:
        print("  [SKIP] no NEBIUS_API_KEY set — retrieval verified above; generation not tested.")
        return None
    from chavruta.corpus.schema import Intent, Query

    q = "מה אומר רש\"י על בריאת האור?"
    ans = pipeline.ask(Query(text=q, lang="he", intent=Intent.QA))
    print(f"  Q: {q}")
    print("  A:", (ans.text or "")[:400])
    print(f"  grounded={ans.grounded}  citations={len(ans.citations)}")
    ok = bool(ans.text) and (ans.grounded or ans.no_source is False)
    print(f"  [{'PASS' if ok else 'FAIL'}] got a grounded answer")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["store", "retrieval", "ask", "all"], default="all")
    ap.add_argument("--no-ask", action="store_true", help="skip the Nebius LLM stage")
    args = ap.parse_args()

    from chavruta.config.profile import Profile

    profile = Profile.from_env()
    print(f"profile={profile.name} qdrant={profile.qdrant_url} hybrid={profile.hybrid} "
          f"llm={profile.llm_backend}:{profile.llm_model}")

    results = {}
    if args.stage in ("store", "all"):
        results["store"] = stage_store(profile)

    if args.stage in ("retrieval", "ask", "all"):
        from chavruta.pipeline.pipeline import ChavrutaPipeline
        print("\n(loading bge-m3 — first run downloads ~2.3GB)…")
        pipeline = ChavrutaPipeline(profile)
        if args.stage in ("retrieval", "all"):
            results["retrieval"] = stage_retrieval(pipeline)
        if args.stage in ("ask", "all") and not args.no_ask:
            results["ask"] = stage_ask(pipeline)

    print("\n" + "=" * 50)
    for k, v in results.items():
        tag = "SKIP" if v is None else ("PASS" if v else "FAIL")
        print(f"  {k:10s} {tag}")
    hard_fail = any(v is False for v in results.values())
    print("=" * 50)
    print("❌ some checks failed" if hard_fail else "✅ all run checks passed")
    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()
