# -*- coding: utf-8 -*-
"""run_eval.py — the trust gate (task T029, Principle V).

Runs the evaluation harness over a versioned dataset and prints a reproducible report.
Changes that touch retrieval/prompting/corpus must be checked against this before they
are considered done (SC-008). Run under either profile for parity checks (SC-006).

    python scripts/run_eval.py --profile local --dataset eval/tanakh_v1.jsonl
    python scripts/run_eval.py --retrieval-only          # fast, LLM-free gate
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Chavruta evaluation harness")
    ap.add_argument("--dataset", default="eval/tanakh_v1.jsonl")
    ap.add_argument("--profile", default=None, help="local | cloud (overrides CHAVRUTA_PROFILE)")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="skip generation — fast retrieval/honesty gate without an LLM")
    ap.add_argument("--out", default=None, help="also write the JSON report to this path")
    ap.add_argument("--show-failures", type=int, default=10)
    args = ap.parse_args()

    if args.profile:
        os.environ["CHAVRUTA_PROFILE"] = args.profile

    from chavruta.config.profile import Profile
    from chavruta.eval.harness import evaluate, load_dataset
    from chavruta.pipeline.pipeline import ChavrutaPipeline

    items = load_dataset(args.dataset)
    print(f"📋 dataset: {args.dataset}  ({len(items)} items)")

    pipeline = ChavrutaPipeline(Profile.from_env())
    report = evaluate(pipeline, items, dataset_name=args.dataset,
                      retrieval_only=args.retrieval_only)

    d = report.to_dict()
    print("─" * 60)
    print(f"profile:        {d['profile']}   (top_k={d['top_k']})")
    print(f"retrieval@K:    {d['retrieval_at_k']:.1%}   ({report.retrieval_hits}/{report.n_answerable})")
    print(f"grounding:      {d['grounding_rate']:.1%}" + ("   [retrieval-only proxy]" if args.retrieval_only else ""))
    print(f"honesty (SC-002): {d['honesty_rate']:.1%}   ({report.no_source_honest}/{report.n_unanswerable})")
    print(f"time:           {d['seconds']}s")
    if report.failures:
        print(f"\n⚠️  failures ({len(report.failures)} total, showing {args.show_failures}):")
        for f in report.failures[: args.show_failures]:
            print("  ", json.dumps(f, ensure_ascii=False)[:200])

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 report → {args.out}")


if __name__ == "__main__":
    main()
