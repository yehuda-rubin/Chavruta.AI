"""Show WHICH specific human eval questions flip from miss to hit between two constant sets.

usage_report.py answers "did the agentic-reruns rate go down" in aggregate, across real traffic
mixed with everything else that varies day to day. This answers a narrower, more concrete question:
for the fixed 40-ish hand-written questions in eval/*.jsonl, which ones does a proposed retrieval
change actually fix (source now in top-k) or break (source drops out)? That is retrieval-only — no
LLM call, no cost — and it is the closest thing to "did we save an agentic round" that can be
checked before spending anything on a live before/after comparison.

    docker compose exec -T api python scripts/diff_retrieval_constants.py \\
        --new _BASE_BOOST=0.2 _QUOTE_BOOST=0.0 _QUOTE_WINDOWS=0

Reports OLD constants as whatever is currently live in src/chavruta/retrieval/hybrid.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import torch  # noqa: F401,E402 — must precede qdrant_client on Windows (pyarrow DLL order)

from tune_retrieval import HUMAN_SETS, _apply, _load, _matches  # noqa: E402

from chavruta.corpus.schema import Intent, Query  # noqa: E402
from chavruta.pipeline.pipeline import ChavrutaPipeline  # noqa: E402


def _ranks(retriever, items: list[dict], top_k: int) -> dict[int, int | None]:
    out: dict[int, int | None] = {}
    for i, item in enumerate(items):
        q = Query(text=item["question"], lang="he", intent=Intent.QA)
        try:
            hits = retriever.retrieve(q, top_k=top_k).hits
        except Exception:
            out[i] = None
            continue
        rank = next((r + 1 for r, h in enumerate(hits)
                     if any(_matches(h.ref, exp) for exp in item["expected_refs"])), None)
        out[i] = rank
    return out


def _parse_kv(pairs: list[str]) -> dict:
    values: dict = {}
    for p in pairs:
        k, v = p.split("=", 1)
        try:
            values[k] = int(v) if "." not in v else float(v)
        except ValueError:
            values[k] = v
    return values


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", nargs="+", required=True, help="KNOB=value pairs to test, e.g. _BASE_BOOST=0.2")
    ap.add_argument("--top-k", type=int, default=8)
    args = ap.parse_args()

    items: list[dict] = []
    for name in HUMAN_SETS:
        items.extend(_load(ROOT / name))
    if not items:
        print("no labelled human questions found")
        return 1

    retriever = ChavrutaPipeline().retriever

    before = _ranks(retriever, items, args.top_k)
    _apply(_parse_kv(args.new))
    after = _ranks(retriever, items, args.top_k)

    fixed, broke, still_miss, still_hit = [], [], 0, 0
    for i, item in enumerate(items):
        b, a = before[i], after[i]
        if b is None and a is not None:
            fixed.append((item["question"], a))
        elif b is not None and a is None:
            broke.append((item["question"], b))
        elif b is None and a is None:
            still_miss += 1
        else:
            still_hit += 1

    print(f"{len(items)} human questions | new constants: {_parse_kv(args.new)}\n")
    print(f"FIXED (miss -> hit): {len(fixed)}")
    for q, rank in fixed:
        print(f"  + rank {rank:>2}  {q}")
    print(f"\nBROKE (hit -> miss): {len(broke)}")
    for q, rank in broke:
        print(f"  - was rank {rank:>2}  {q}")
    print(f"\nunchanged: {still_hit} still hit, {still_miss} still miss")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
