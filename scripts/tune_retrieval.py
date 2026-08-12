"""Choose the retriever's constants by measurement instead of judgement. Retrieval only — no LLM.

THE PROBLEM THIS SOLVES
-----------------------
Every constant in hybrid.py (the tractate boost, the foundational-works boost, how many candidates
each floor pulls, how many slots base texts are guaranteed) was picked by judgement. With 26
hand-written eval questions there was no way to check any of them: three consecutive retrieval
changes each measured 52%, which at that sample size cannot be distinguished from noise. This runs
the retriever over thousands of harvested ground-truth pairs and picks the values that actually
score best.

THE VETO — THE PART THAT MATTERS MOST
-------------------------------------
The harvested pairs are rabbinic Hebrew (see harvest_pairs.py). Real users write modern colloquial
Hebrew, and that gap IS the measured failure. So maximising the harvested score is not the goal and
can actively harm the product: a retriever tuned to love source-language phrasing gets worse at the
phrasing people actually use.

Therefore the human-written sets (eval/torah_questions_v1.jsonl, eval/regressions_v1.jsonl,
eval/user_questions_v1.jsonl) are NOT averaged in. They are a veto: a candidate value must improve
the harvested score AND not lose ground on the human sets, or it is rejected. The harvested set is
big enough to see a signal; the human set is the one that decides what "better" means.

METHOD
------
Coordinate descent, not a full grid. Each retrieval call against the 2.4M on-disk collection costs
seconds, so a full grid over five knobs is days while coordinate descent is one night: tune one knob
at a time, keep the winner, move on. It can settle in a local optimum — accepted deliberately, since
the alternative on this budget is not a global search but no search at all.

RUNTIME is dominated by Qdrant, not by us: budget roughly (sample x seconds-per-query) per candidate
value. Start with --sample 150 to get a result overnight, then re-run the winners at a larger sample
to confirm they were not noise. Nothing here writes to the codebase: it prints the winning values
for a human to apply.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import torch  # noqa: F401,E402 — must precede qdrant_client on Windows (pyarrow DLL order)

from chavruta.corpus.refs import with_ref_variants  # noqa: E402
from chavruta.corpus.schema import Intent, Query  # noqa: E402
from chavruta.retrieval import hybrid  # noqa: E402

# The knobs, and the values worth trying for each. Ordered so the ones with the most reason to
# matter come first — coordinate descent keeps earlier winners, so ordering is not cosmetic.
KNOBS: dict[str, list] = {
    "_TRACTATE_BOOST": [0.0, 0.02, 0.05, 0.10, 0.20],
    "_TRACTATE_TOP_K": [3, 6, 10, 16],
    "_FOUNDATIONAL_BOOST": [0.0, 0.02, 0.05, 0.10, 0.20],
    "_FOUNDATIONAL_TOP_K": [3, 6, 10, 16],
    "_BASE_SLOTS": [0, 1, 2, 3, 4],
}

HUMAN_SETS = ("eval/torah_questions_v1.jsonl", "eval/regressions_v1.jsonl",
              "eval/user_questions_v1.jsonl")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        # An unlabelled question (harvest_user_questions leaves expected_refs empty until a human
        # fills it in) cannot score anything — including it would count as a guaranteed miss and
        # quietly drag every candidate down by the same amount.
        if item.get("expected_refs"):
            out.append(item)
    return out


def _matches(got: str, expected: str) -> bool:
    """Whether a retrieved ref satisfies an expected one.

    Prefix-based, and deliberately so: the corpus stores at finer granularity than an eval label
    names ('Sukkah.81' is answered by 'Sukkah.81' and a commentary label by its exact ref), and both
    ref spellings are accepted because the router emits dotted refs while parts of the corpus use
    the underscore form (see corpus/refs.with_ref_variants — this was a real recall bug).
    """
    for variant in with_ref_variants([expected]):
        if got == variant or got.startswith(variant + ".") or variant.startswith(got + "."):
            return True
    return False


def score(retriever, items: list[dict], *, top_k: int) -> dict:
    """recall@k and MRR over an eval set. Both are reported because they answer different questions:
    recall asks whether the source was there at all, MRR whether it was near the top where a bounded
    prompt will actually include it.

    A harvested query is the verbatim text of a chunk that lives in the collection, so it retrieves
    ITSELF — measured at 25/25 on the first live sample. That hit is worthless as evidence (it says
    only that identical text embeds identically) and it consumes a top-k slot the real answer needed,
    so it is dropped. `source_ref` is present only on harvested items; human-written questions have
    no such chunk and are unaffected.
    """
    hits_at_k, rr = 0, []
    for item in items:
        q = Query(text=item["question"], lang="he", intent=Intent.QA)
        try:
            result = retriever.retrieve(q, top_k=top_k)
        except Exception:
            rr.append(0.0)
            continue
        source = item.get("source_ref")
        refs = [h.ref for h in result.hits if h.ref != source]
        rank = next((i + 1 for i, got in enumerate(refs)
                     if any(_matches(got, exp) for exp in item["expected_refs"])), None)
        hits_at_k += 1 if rank else 0
        rr.append(1.0 / rank if rank else 0.0)
    n = max(1, len(items))
    return {"n": len(items), "recall": hits_at_k / n, "mrr": statistics.fmean(rr) if rr else 0.0}


def _apply(values: dict) -> None:
    for name, value in values.items():
        setattr(hybrid, name, value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", default="eval/harvested_pairs_v1.jsonl")
    ap.add_argument("--sample", type=int, default=150, help="harvested pairs per candidate value")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--holdout", type=float, default=0.5,
                    help="fraction of the harvested pairs kept back to confirm the winner")
    args = ap.parse_args()

    pairs = _load(ROOT / args.pairs)
    if not pairs:
        print(f"no harvested pairs at {args.pairs} — run scripts/harvest_pairs.py first")
        return 1
    cut = int(len(pairs) * (1 - args.holdout))
    tune_set, holdout = pairs[:cut][:args.sample], pairs[cut:][:args.sample]

    human: list[dict] = []
    for name in HUMAN_SETS:
        human.extend(_load(ROOT / name))
    if not human:
        print("REFUSING to tune: no labelled human questions found, so the veto cannot run.\n"
              "Tuning on harvested pairs alone optimises for rabbinic-Hebrew phrasing, which is the\n"
              "opposite of the measured failure. See this script's docstring.")
        return 1

    from chavruta.pipeline.pipeline import ChavrutaPipeline
    retriever = ChavrutaPipeline().retriever

    baseline = {k: getattr(hybrid, k) for k in KNOBS}
    print(f"tuning on {len(tune_set)} harvested pairs | veto set: {len(human)} human questions")
    print(f"baseline: {baseline}\n")

    base_tuned = score(retriever, tune_set, top_k=args.top_k)
    base_human = score(retriever, human, top_k=args.top_k)
    print(f"baseline  harvested recall={base_tuned['recall']:.3f} mrr={base_tuned['mrr']:.3f}"
          f" | human recall={base_human['recall']:.3f} mrr={base_human['mrr']:.3f}\n")

    best = dict(baseline)
    best_score, best_human = base_tuned["mrr"], base_human["mrr"]

    for knob, candidates in KNOBS.items():
        print(f"── {knob} (currently {best[knob]})")
        for value in candidates:
            if value == best[knob]:
                continue
            trial = dict(best, **{knob: value})
            _apply(trial)
            t0 = time.monotonic()
            s = score(retriever, tune_set, top_k=args.top_k)
            h = score(retriever, human, top_k=args.top_k)
            elapsed = time.monotonic() - t0
            # THE VETO: a gain on harvested pairs that costs anything on real questions is refused.
            vetoed = h["mrr"] < best_human - 1e-9
            verdict = "VETOED (hurts real questions)" if vetoed else \
                      ("accepted" if s["mrr"] > best_score else "no gain")
            print(f"   {value!r:>6}  harvested mrr={s['mrr']:.3f}  human mrr={h['mrr']:.3f}"
                  f"  [{elapsed:.0f}s] {verdict}")
            if not vetoed and s["mrr"] > best_score:
                best, best_score, best_human = trial, s["mrr"], h["mrr"]
        _apply(best)
        print(f"   → keeping {knob} = {best[knob]}\n")

    print("confirming the winner on the held-out half (a gain that does not survive this was noise)")
    _apply(baseline)
    hold_before = score(retriever, holdout, top_k=args.top_k)
    _apply(best)
    hold_after = score(retriever, holdout, top_k=args.top_k)

    print(f"\nheld-out  before mrr={hold_before['mrr']:.3f} recall={hold_before['recall']:.3f}")
    print(f"held-out  after  mrr={hold_after['mrr']:.3f} recall={hold_after['recall']:.3f}")
    print(f"\nbaseline : {baseline}")
    print(f"winner   : {best}")
    if hold_after["mrr"] <= hold_before["mrr"]:
        print("\nThe gain did NOT survive the held-out half. Do not apply these values — this is "
              "what overfitting to a tuning split looks like, and it is the expected outcome when "
              "the constants were already near a local optimum.")
    else:
        print("\nApply by editing the constants in src/chavruta/retrieval/hybrid.py. Nothing is "
              "written automatically: these are load-bearing product values and deserve a human "
              "reading the numbers first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
