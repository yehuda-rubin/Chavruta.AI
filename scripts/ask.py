# -*- coding: utf-8 -*-
"""ask.py — one-shot grounded Q&A CLI (task T027).

    python scripts/ask.py "What does Rashi say about the creation of light?"
    python scripts/ask.py "מה אומר רד\"ק על ספר יונה?" --intent qa --profile local
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.corpus.schema import Intent, Query  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Chavruta — grounded, cited answers")
    ap.add_argument("question")
    ap.add_argument("--intent", choices=[i.value for i in Intent], default=None,
                    help="qa | explain | compare | lesson (auto-detected if omitted)")
    ap.add_argument("--profile", default=None, help="local | cloud (overrides CHAVRUTA_PROFILE)")
    ap.add_argument("--works", default=None, help="comma-separated work ids to scope (e.g. tanakh)")
    ap.add_argument("--top-k", type=int, default=None)
    args = ap.parse_args()

    if args.profile:
        os.environ["CHAVRUTA_PROFILE"] = args.profile

    from chavruta.config.profile import Profile
    from chavruta.pipeline.pipeline import ChavrutaPipeline

    profile = Profile.from_env()
    if args.top_k:
        profile.top_k = args.top_k

    pipeline = ChavrutaPipeline(profile)
    query = Query(
        text=args.question,
        lang="",                       # auto-detect
        intent=Intent(args.intent) if args.intent else Intent.QA,
        work_ids=args.works.split(",") if args.works else None,
    )
    answer = pipeline.ask(query)

    print("\n" + answer.text + "\n")
    if answer.caveats:
        for c in answer.caveats:
            print(f"⚠️  {c}")
    if answer.citations:
        print("─" * 60)
        print("מקורות / Sources:")
        for c in answer.citations:
            who = f" ({c.commentator_id})" if c.commentator_id else ""
            print(f"  • {c.ref}{who}  →  {c.deep_link}")
    elif answer.no_source:
        print("(no grounded source found — nothing was invented)")


if __name__ == "__main__":
    main()
