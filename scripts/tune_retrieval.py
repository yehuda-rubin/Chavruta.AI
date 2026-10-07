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

RESUMING ACROSS NIGHTS (--state)
--------------------------------
A full descent does not fit in one 5-hour window once the pool is big enough to mean anything, and
for a week it did not fit and nobody noticed: each night restarted from the constants in hybrid.py,
got partway through the sweep, was killed at 05:00, and threw the evening away. The log said
"will resume next run", which was simply not true — there was nothing to resume from. Two nights ran
to `rc=124` having accepted a value that was never confirmed and never written down.

With `--state PATH` this tunes ONE knob per run and persists what it learned, so a sweep spans as
many nights as it needs. Each run ends with the held-out check on everything accepted so far, which
means every night produces an answer that is either applicable or explicitly rejected — rather than
nothing at all until a sweep that never finishes finishes.

The state is abandoned and started over when the ground moves under it: if the constants in
hybrid.py no longer match the baseline the sweep began from (someone applied a value by hand), or if
the pairs pool changed. Coordinate descent keeps earlier winners, so every later decision was made
in the context of the earlier ones; carrying those forward onto a different baseline or different
data would be quietly comparing things that were never comparable.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

try:
    import torch  # noqa: F401,E402 — must precede qdrant_client on Windows (pyarrow DLL order)
except Exception:  # noqa: BLE001
    pass

from chavruta.corpus.refs import with_ref_variants  # noqa: E402
from chavruta.corpus.schema import Intent, Query  # noqa: E402
from chavruta.retrieval import hybrid  # noqa: E402

# The knobs, and the values worth trying for each. Ordered so the ones with the most reason to
# matter come first — coordinate descent keeps earlier winners, so ordering is not cosmetic.
KNOBS: dict[str, list] = {
    # First, because it is the newest and the least evidenced: added 2026-08-14 when the base-text
    # floor turned out to append candidates and boost nothing, so its "reserved" slots lost the score
    # sort every time. 0.0 is in the list on purpose — it reproduces the old behaviour, so the sweep
    # can say the lift does not help rather than being unable to express that.
    "_BASE_BOOST": [0.0, 0.02, 0.05, 0.10, 0.20],
    "_QUOTE_BOOST": [0.0, 0.02, 0.05, 0.10, 0.20],
    "_QUOTE_WINDOWS": [0, 2, 4, 6],
    "_TRACTATE_BOOST": [0.0, 0.02, 0.05, 0.10, 0.20],
    "_TRACTATE_TOP_K": [3, 6, 10, 16],
    "_FOUNDATIONAL_BOOST": [0.0, 0.02, 0.05, 0.10, 0.20],
    "_FOUNDATIONAL_TOP_K": [3, 6, 10, 16],
    "_BASE_SLOTS": [0, 1, 2, 3, 4],
}

HUMAN_SETS = ("eval/torah_questions_v1.jsonl", "eval/regressions_v1.jsonl",
              "eval/user_questions_v1.jsonl")

# How much evidence a run needs before its answer means anything.
#
# MIN_HITS is the number of harvested pairs that must actually be ANSWERED — not the number of pairs
# in the file. Coordinate descent over five answered questions finds whichever candidate got lucky,
# which is exactly what the first week produced: identical inputs, three runs, three different
# winners. Thirty is the point where one item flipping (~0.033 of mrr) stops dwarfing the effects
# being measured; it is a floor, not a target.
MIN_HITS = 30
# And a candidate has to beat the incumbent by more than one question's worth of luck. mrr averages
# over the whole set, so a single item going from missed to first place moves it by 1/len(tune_set) —
# any "gain" smaller than that is one item, not an effect. That floor scales itself with the sample
# instead of being a constant I would have to remember to retune; the relative term only takes over
# once mrr is large enough for 2% of it to exceed a single item.
MIN_GAIN_REL = 0.02


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


# ── Cross-night state ─────────────────────────────────────────────────────────
STATE_VERSION = 2


def _fingerprint(pairs_path: Path, baseline: dict) -> str:
    """What the stored progress is only valid FOR.

    Two things invalidate a half-finished descent, and both have to be caught or the resumed sweep
    silently compares values that were measured under different conditions:

      * the constants in hybrid.py changed — someone applied a winner by hand, so the incumbent the
        earlier knobs were measured against no longer exists;
      * the pairs pool changed — a re-harvest replaces the questions, and an mrr on one set of
        questions is not comparable to an mrr on another.
    """
    try:
        stat = pairs_path.stat()
        pool = f"{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        pool = "missing"
    return json.dumps({"baseline": baseline, "pool": pool}, sort_keys=True)


def _load_state(path: Path, fingerprint: str) -> dict:
    """Stored progress, or a fresh sweep if there is none or it no longer applies."""
    fresh = {"version": STATE_VERSION, "fingerprint": fingerprint, "best": None, "done": [],
             "history": [], "in_progress": None}
    if not path.exists():
        return fresh
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fresh
    if state.get("version") != STATE_VERSION:
        print("state file is from an older version — starting the sweep over")
        return fresh
    if state.get("fingerprint") != fingerprint:
        print("the constants or the pairs pool changed since this sweep began — starting over.\n"
              "Coordinate descent keeps earlier winners, so those decisions were made against a\n"
              "baseline that no longer exists and cannot be carried forward.")
        return fresh
    return state


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# Sits beside the pairs file, not the state file — a "too thin to tune" verdict is a property of
# the POOL, not of one knob-sweep's progress, and the nightly wrapper needs to read it without
# caring whether a --state sweep is even in progress.
_THIN_SUFFIX = ".thin.json"


def _mark_thin(pairs_path: Path, *, hits: int, sample: int) -> None:
    """Record that THIS pool, as it stood on disk just now, did not have enough answered pairs to
    tune on. `nightly_eval.py`'s harvest gate reads this so a pool that passes the count/age check
    but fails the check that actually matters (how many pairs are answered) gets re-harvested next
    time instead of sitting there being re-measured — and re-declared too thin — every single night
    until the age gate finally expires. Tagged with size:mtime so a fresh harvest (which changes
    both) invalidates the mark on its own; nothing has to remember to delete it.
    """
    marker = pairs_path.with_suffix(pairs_path.suffix + _THIN_SUFFIX)
    try:
        stat = pairs_path.stat()
        pool = f"{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        return
    try:
        marker.write_text(json.dumps(
            {"pool": pool, "hits": hits, "sample": sample, "min_hits": MIN_HITS,
             "checked_at": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", default="eval/harvested_pairs_v1.jsonl")
    # 400, not 150. Measured on the live box: a query costs about a second, so 400 harvested pairs
    # plus the human veto set is ~7 minutes per candidate and ~2.5 hours for the whole descent —
    # comfortably inside the 5-hour weeknight window. At a ~12% hit rate 400 pairs yield around 50
    # answered ones, which is enough for a difference between two settings to mean something; 150
    # would leave ~19 and most of the run would be reading noise.
    ap.add_argument("--sample", type=int, default=400, help="harvested pairs per candidate value")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--holdout", type=float, default=0.5,
                    help="fraction of the harvested pairs kept back to confirm the winner")
    ap.add_argument("--state", default="",
                    help="persist progress here and tune ONE knob per run, resuming across nights")
    ap.add_argument("--reset", action="store_true", help="discard stored progress and start over")
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

    # Resume, if asked to. `best` carries forward what earlier nights accepted; `done` is which knobs
    # no longer need looking at. Both are dropped if the fingerprint no longer matches.
    state_path = Path(args.state) if args.state else None
    state: dict = {}
    if state_path:
        fp = _fingerprint(ROOT / args.pairs, baseline)
        if args.reset and state_path.exists():
            state_path.unlink()
            print("--reset: stored progress discarded")
        state = _load_state(state_path, fp)
        state["fingerprint"] = fp

    print(f"tuning on {len(tune_set)} harvested pairs | veto set: {len(human)} human questions")
    print(f"baseline: {baseline}")
    if state:
        carried = state.get("best") or baseline
        print(f"resuming: {len(state['done'])}/{len(KNOBS)} knobs done{' — ' + ', '.join(state['done']) if state['done'] else ''}")
        if carried != baseline:
            print(f"carried  : {carried}")
    print()

    base_tuned = score(retriever, tune_set, top_k=args.top_k)
    base_human = score(retriever, human, top_k=args.top_k)
    print(f"baseline  harvested recall={base_tuned['recall']:.3f} mrr={base_tuned['mrr']:.3f}"
          f" | human recall={base_human['recall']:.3f} mrr={base_human['mrr']:.3f}\n")

    # A search needs something to search ON. Harvested hit rates run around 12%, so a small sample
    # can score a flat zero for EVERY candidate — and coordinate descent over an all-zero objective
    # is not a tuning run that found nothing, it is twenty candidates evaluated against no signal at
    # all. Caught on the first live run at --sample 6. Say so instead of printing a page of "no
    # gain" that reads like a result.
    if base_tuned["mrr"] <= 0:
        print(f"NO SIGNAL: none of the {len(tune_set)} harvested pairs is answered at all, so every\n"
              f"candidate will score 0.000 and nothing can be compared. Raise --sample (harvested\n"
              f"hit rates run near 12%, so a few hundred pairs are needed before differences show).")
        _mark_thin(ROOT / args.pairs, hits=0, sample=len(tune_set))
        return 1

    # An objective that is merely NEAR zero is barely better than one that is zero. At a ~10% hit
    # rate, 52 pairs answer about five questions, and a single one of them moving changes mrr by
    # ~0.02 — larger than any difference these knobs produce. Three runs on one night, over identical
    # inputs, then returned three different "winners": 0.2 / 0.05 / 0.05 for TRACTATE_BOOST alone.
    # That is not tuning, it is sampling noise with a 130-second stopwatch attached.
    hits = round(base_tuned["recall"] * len(tune_set))
    if hits < MIN_HITS:
        print(f"TOO THIN: only ~{hits} of {len(tune_set)} harvested pairs are answered at all "
              f"(recall={base_tuned['recall']:.3f}).\nOne of them flipping moves mrr by roughly "
              f"{1.0 / max(1, hits):.3f}, which swamps every difference these knobs make — so a "
              f"'winner'\nhere is whichever candidate got lucky. Harvest more pairs "
              f"(at least {MIN_HITS} answered; scripts/harvest_pairs.py --target 5000) and re-run.")
        _mark_thin(ROOT / args.pairs, hits=hits, sample=len(tune_set))
        return 1

    best = dict(state.get("best") or baseline)
    best_score, best_human = base_tuned["mrr"], base_human["mrr"]
    # The incumbent is what earlier nights accepted, not the code's constants — so this night's
    # candidates are compared against the same thing they will actually replace. Scoring it costs one
    # candidate's worth of window and is not optional: comparing tonight's numbers against a baseline
    # measured on a different night, with a different pool, is how a sweep accumulates drift.
    if best != baseline:
        _apply(best)
        carried_t, carried_h = score(retriever, tune_set, top_k=args.top_k), \
            score(retriever, human, top_k=args.top_k)
        print(f"carried   harvested recall={carried_t['recall']:.3f} mrr={carried_t['mrr']:.3f}"
              f" | human recall={carried_h['recall']:.3f} mrr={carried_h['mrr']:.3f}\n")
        best_score, best_human = carried_t["mrr"], carried_h["mrr"]

    # In state mode a run tunes ONE knob and stops. A full descent does not fit in a 5-hour window at
    # a pool size worth measuring on, and a run that is killed partway through has, in practice,
    # measured nothing it can keep.
    todo = [k for k in KNOBS if k not in set(state.get("done", []))]
    if state_path and not todo:
        print(f"the sweep is complete — all {len(KNOBS)} knobs tuned.\n"
              f"baseline : {baseline}\nwinner   : {best}\n"
              f"Re-run with --reset to start a fresh sweep (worth doing after a re-harvest or a "
              f"corpus reload).")
        return 0
    knobs_this_run = {todo[0]: KNOBS[todo[0]]} if state_path else KNOBS
    # One question flipping from missed to first place moves mrr by exactly this much.
    one_item = 1.0 / max(1, len(tune_set))
    min_gain = max(one_item, best_score * MIN_GAIN_REL)
    print(f"a candidate must gain more than {min_gain:.5f} mrr to be accepted "
          f"(one question of {len(tune_set)} is worth {one_item:.5f})\n")

    # Checkpointing WITHIN a knob, not just once the whole knob (candidates + held-out confirmation)
    # is done. Measured live 2026-08-17/18: the first night with the widened window scored all four
    # _BASE_BOOST candidates and printed "→ keeping _BASE_BOOST = 0.2", then the window closed one
    # step later, on the held-out confirmation — and because nothing was written until the very end,
    # the next run started that whole knob over from its first candidate, at ~87 minutes each. A
    # candidate (or a held-out half) already scored THIS sweep is reproducible — same model, same
    # corpus, same pairs, no randomness in the retrieval path — so caching its result is exactly as
    # trustworthy as the number that would come from re-running it, at zero cost instead of ~87
    # minutes.
    for knob, candidates in knobs_this_run.items():
        print(f"── {knob} (currently {best[knob]})")
        ip = state.get("in_progress") if state_path else None
        resuming = bool(ip and ip.get("knob") == knob)
        tried: dict = dict(ip["tried"]) if resuming else {}
        best_k, score_k, human_k = (dict(ip["best"]), ip["best_score"], ip["best_human"]) \
            if resuming else (dict(best), best_score, best_human)
        if resuming and tried:
            print(f"   resuming: {len(tried)} candidate(s) already scored this sweep")
        elif state_path:
            state["in_progress"] = {"knob": knob, "tried": {}, "best": dict(best_k),
                                    "best_score": score_k, "best_human": human_k}
            _save_state(state_path, state)

        for value in candidates:
            if value == best_k[knob]:
                continue
            cached = tried.get(repr(value))
            if cached is not None:
                print(f"   {value!r:>6}  harvested mrr={cached['mrr']:.5f}  human mrr={cached['human']:.5f}"
                      f"  (resumed) {'accepted' if cached['accepted'] else 'not accepted'}")
                if cached["accepted"]:
                    best_k = dict(best_k, **{knob: value})
                    score_k, human_k = cached["mrr"], cached["human"]
                continue
            trial = dict(best_k, **{knob: value})
            _apply(trial)
            t0 = time.monotonic()
            s = score(retriever, tune_set, top_k=args.top_k)
            h = score(retriever, human, top_k=args.top_k)
            elapsed = time.monotonic() - t0
            # THE VETO: a gain on harvested pairs that costs anything on real questions is refused.
            vetoed = h["mrr"] < human_k - 1e-9
            # A bare `>` on floats calls a difference in the fourth decimal a win. That is how the
            # first live run "accepted" 0.02 (mrr 0.1013) over four candidates that all scored higher
            # on the human set (0.106) — the log printed three decimals and showed them all as ties,
            # so the decision was invisible to anyone reading it. A candidate now has to clear a real
            # margin, and the print carries enough precision to check the arithmetic by eye.
            gain = s["mrr"] - score_k
            wins = gain > min_gain
            accepted = not vetoed and wins
            verdict = "VETOED (hurts real questions)" if vetoed else \
                      ("accepted" if wins else f"no gain (+{gain:.5f}, needs +{min_gain:.5f})")
            print(f"   {value!r:>6}  harvested mrr={s['mrr']:.5f}  human mrr={h['mrr']:.5f}"
                  f"  [{elapsed:.0f}s] {verdict}")
            tried[repr(value)] = {"mrr": s["mrr"], "human": h["mrr"], "accepted": accepted}
            if accepted:
                best_k, score_k, human_k = trial, s["mrr"], h["mrr"]
            if state_path:
                state["in_progress"] = {"knob": knob, "tried": tried, "best": best_k,
                                        "best_score": score_k, "best_human": human_k}
                _save_state(state_path, state)
        best, best_score, best_human = best_k, score_k, human_k
        _apply(best)
        print(f"   → keeping {knob} = {best[knob]}\n")

    print("confirming the winner on the held-out half (a gain that does not survive this was noise)")
    held = (state.get("in_progress") or {}).get("held_out") or {} if state_path else {}
    if "before" in held:
        hold_before = held["before"]
        print("   (before) already scored this sweep — resumed")
    else:
        _apply(baseline)
        hold_before = score(retriever, holdout, top_k=args.top_k)
        if state_path:
            ip = dict(state["in_progress"])
            ip["held_out"] = {"before": hold_before}
            state["in_progress"] = ip
            _save_state(state_path, state)
    if "after" in held:
        hold_after = held["after"]
        print("   (after) already scored this sweep — resumed")
    else:
        _apply(best)
        hold_after = score(retriever, holdout, top_k=args.top_k)
        if state_path:
            ip = dict(state["in_progress"])
            ip["held_out"] = dict(ip.get("held_out") or {}, after=hold_after)
            state["in_progress"] = ip
            _save_state(state_path, state)

    print(f"\nheld-out  before mrr={hold_before['mrr']:.3f} recall={hold_before['recall']:.3f}")
    print(f"held-out  after  mrr={hold_after['mrr']:.3f} recall={hold_after['recall']:.3f}")
    print(f"\nbaseline : {baseline}")
    print(f"winner   : {best}")
    survived = hold_after["mrr"] > hold_before["mrr"]
    if not survived:
        print("\nThe gain did NOT survive the held-out half. Do not apply these values — this is "
              "what overfitting to a tuning split looks like, and it is the expected outcome when "
              "the constants were already near a local optimum.")
    else:
        print("\nApply by editing the constants in src/chavruta/retrieval/hybrid.py. Nothing is "
              "written automatically: these are load-bearing product values and deserve a human "
              "reading the numbers first.")

    if state_path:
        # Moved from "done" only now that the knob is finished AND checked — a run killed mid-knob
        # (see the in_progress checkpointing above) leaves `done` untouched, so a half-swept knob
        # never reads as complete. `in_progress` itself is cleared here: the individual candidate
        # and held-out scores it held are no longer needed once this knob's verdict is recorded.
        tuned_now = list(knobs_this_run)
        state["best"] = best
        state["done"] = list(state.get("done", [])) + tuned_now
        state["in_progress"] = None
        state["history"] = list(state.get("history", []))[-40:] + [{
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "knobs": tuned_now,
            "chose": {k: best[k] for k in tuned_now},
            "held_out_before": round(hold_before["mrr"], 5),
            "held_out_after": round(hold_after["mrr"], 5),
            "survived": survived,
            "sample": len(tune_set),
        }]
        _save_state(state_path, state)
        left = [k for k in KNOBS if k not in set(state["done"])]
        print(f"\nprogress saved → {state_path}")
        print(f"{len(state['done'])}/{len(KNOBS)} knobs done"
              + (f"; next up: {left[0]}" if left else "; sweep complete"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
