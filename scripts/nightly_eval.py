"""Run the retrieval harvest + tune inside a permitted window, on a bounded slice of the machine.

SCHEDULE (Israel local time, decided here rather than in cron)
--------------------------------------------------------------
    every night   23:00-07:00   on 2 CPUs   (wraps past midnight)
    Saturday      00:00-16:00   on 6 CPUs

Widened from 00:00-05:00 on 2026-08-17: at --sample 1600 (see the --sample argument below) a
candidate measured ~87 minutes live, not the ~54 estimated, so a 5-hour window fit only 2-3 of a
knob's up to 5 candidates before rc=124 — and _save_state only writes once a whole knob is finished
(see main(), "written only once the knob is finished AND checked"), so an interrupted knob restarts
from its first candidate every single night rather than resuming mid-knob. 8 hours does not
guarantee finishing a knob either, but it roughly doubles how far one night gets.

The window is computed from Asia/Jerusalem, NOT from a fixed UTC offset, because the server runs on
UTC and Israel moves between UTC+2 and UTC+3. A cron line with a hardcoded offset would silently
slide by an hour twice a year and start work in the middle of the evening. cron therefore only wakes
this script up often; THIS decides whether the moment is inside a window and for how long.

WHY A CPU BUDGET AT ALL
-----------------------
The API serves users from the same 8-core box, and bge-m3 embedding is the CPU-bound part of every
single request. An unbounded batch job here does not "use spare capacity" — it competes with live
questions and makes them slow, at night, silently. Two limits are applied together because either
alone is insufficient: `taskset` decides WHICH cores the process may touch, while the BLAS/OMP
thread caps stop torch from spawning eight worker threads inside those cores and thrashing.

STOPPING, AND WHY IT USED TO THROW THE NIGHT AWAY
-------------------------------------------------
The run is bounded by the window, not by the work. That was always the design, and until 2026-08-14
the second half of it did not exist: the log said an abandoned step would be "picked up the next
night", and nothing carried anything over. Every night restarted from the constants in hybrid.py,
swept partway, and was killed at 05:00. Two consecutive nights ended `rc=124` having accepted a
value that was never confirmed and never recorded anywhere.

It could not have finished, either. Once the pool grew to a size worth measuring on, a candidate
went from ~130s to ~1310s, so a full five-knob descent needs 7-9 hours and the weeknight window was
5 (now 8 — see SCHEDULE above). No number of nights adds up when each one starts over.

So the tuner now keeps state (`tune_retrieval.py --state`) and does ONE knob per night, ending each
run with the held-out confirmation. A sweep takes about five nights instead of one, and every night
produces a result that is either applicable or explicitly rejected — instead of nothing, five nights
running.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ISRAEL = ZoneInfo("Asia/Jerusalem")

# (last hour exclusive, cpu budget). Saturday is checked first so it wins where the two overlap.
SATURDAY_WINDOW = (0, 16, 6)     # 00:00-16:00 on six cores
NIGHTLY_WINDOW = (23, 7, 2)      # 23:00-07:00 on two cores — WRAPS past midnight; see window_for

# Where GENERATED artefacts go — harvested pairs and each night's log. Deliberately separable from
# eval/, which holds the hand-written question sets: in the container those are mounted READ-ONLY
# (curated input, version-controlled) while this points at a writable volume. Sharing one directory
# would mean either making the curated sets writable by the job or having no output at all — the
# first run failed with exactly that permission error, which is the right thing to have hit.
OUT_ROOT = Path(os.environ.get("CHAVRUTA_EVAL_OUT") or (ROOT / "eval"))
LOG_DIR = OUT_ROOT / "nightly"
PAIRS = str(OUT_ROOT / "harvested_pairs_v1.jsonl")
# Where the descent's progress lives between nights. Beside the logs and on the same writable volume,
# because it is generated output — and losing it costs only a repeated sweep, never correctness: the
# tuner re-derives everything from the constants and the pool, and discards the file outright if
# either has moved.
STATE = str(LOG_DIR / "tuning_state.json")
# Re-harvesting every night would burn the window re-deriving pairs that have not changed — the
# corpus is static between loads. Refresh only when the file is missing or older than this.
PAIRS_MAX_AGE_DAYS = 14
# ...but AGE was the only test, and that was the whole reason the first week produced nothing. A run
# with an early `--target 150` left 105 pairs behind; the file was then "current" for a fortnight, so
# every night re-tuned on a set far too small to separate anything, and returned a different answer
# each time. Size is the condition that actually matters: below this the tuner refuses to run at all
# (tune_retrieval.MIN_HITS), so a small pool means the window is burnt for nothing.
PAIRS_MIN = 2000


def window_for(now: datetime) -> tuple[datetime, int] | None:
    """(when this window ends, how many CPUs) — or None if `now` is outside every window.

    NIGHTLY_WINDOW crosses midnight (23:00-07:00), which a plain `start <= hour < end` cannot
    express — that comparison is false for every hour when start > end. Two cases instead: `now` at
    23:30 is inside a window that started TODAY and ends TOMORROW; `now` at 03:00 is inside a window
    that started YESTERDAY and ends TODAY. Saturday never wraps (0 < 16), so it falls through to the
    plain range check unchanged.
    """
    start_h, end_h, cpus = SATURDAY_WINDOW if now.weekday() == 5 else NIGHTLY_WINDOW
    if start_h > end_h:
        if now.hour >= start_h:
            ends_at = (now + timedelta(days=1)).replace(hour=end_h, minute=0, second=0, microsecond=0)
        elif now.hour < end_h:
            ends_at = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
        else:
            return None
        return ends_at, cpus
    if not (start_h <= now.hour < end_h):
        return None
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=end_h), cpus


def _run(cmd: list[str], *, cpus: int, deadline_s: int, log) -> int:
    """Run one step pinned to `cpus` cores, killed at the deadline. Never raises."""
    env = dict(os.environ)
    # Cap the numeric libraries too. taskset alone would let torch start 8 threads on 2 cores, which
    # is slower than 2 threads AND still starves the API through cache and memory-bandwidth pressure.
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS", "TOKENIZERS_PARALLELISM"):
        env[var] = "false" if var == "TOKENIZERS_PARALLELISM" else str(cpus)

    # Cores 0..cpus-1, and nice so the kernel prefers a real user request over this every time.
    wrapped = ["nice", "-n", "19", "taskset", "-c", f"0-{max(0, cpus - 1)}", *cmd]
    log.write(f"$ {' '.join(wrapped)}\n")
    log.flush()
    try:
        proc = subprocess.run(wrapped, env=env, timeout=deadline_s, stdout=log, stderr=log)
        return proc.returncode
    except subprocess.TimeoutExpired:
        log.write("\n[window closed — step abandoned, will resume next run]\n")
        return 124
    except FileNotFoundError:
        # taskset/nice missing (a slim image): fall back to the thread caps alone rather than not
        # running at all — a degraded budget still beats an unbounded one.
        log.write("[taskset/nice unavailable — falling back to thread caps only]\n")
        try:
            return subprocess.run(cmd, env=env, timeout=deadline_s, stdout=log, stderr=log).returncode
        except subprocess.TimeoutExpired:
            return 124


def _pairs_count(path: Path) -> int:
    """Data lines in the pairs file — the leading `#` header is not evidence."""
    try:
        with path.open(encoding="utf-8") as fh:
            return sum(1 for ln in fh if ln.strip() and not ln.startswith("#"))
    except OSError:
        return 0


def _too_thin_reason(pairs_path: Path) -> str:
    """Whether the tuner already measured THIS pool and found too few of it actually answered to
    tune on — see tune_retrieval.py::_mark_thin. Count and age are necessary but not sufficient: a
    pool can be large and fresh and still be ~99% unanswered (measured live 2026-08-14 through
    2026-08-16, size 3325/age <14d passing every tick of a 16-hour Saturday window and a full
    nightly window — recall=0.026, ~21 pairs actually answered — while every single tick re-derived
    and re-discarded the same verdict instead of re-harvesting). The marker is tagged with the pool's
    own size:mtime, so a harvest that already happened (which changes both) silently invalidates a
    stale mark — no separate cleanup needed.
    """
    marker = pairs_path.with_suffix(pairs_path.suffix + ".thin.json")
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
        stat = pairs_path.stat()
        pool = f"{stat.st_size}:{int(stat.st_mtime)}"
    except (OSError, ValueError):
        return ""
    if info.get("pool") != pool:
        return ""    # the pool moved since the tuner measured it — the mark no longer applies
    return (f"the tuner already found only {info.get('hits', '?')} of "
            f"{info.get('sample', '?')} pairs answered (needs {info.get('min_hits', '?')})")


def _harvest_reason() -> str:
    """Why this run should re-harvest, or "" to skip. Size first: a pool too small to measure with
    is a worse reason to skip than a pool that is merely old."""
    path = Path(PAIRS)
    if not path.exists():
        return "no pairs file yet"
    have = _pairs_count(path)
    if have < PAIRS_MIN:
        return f"only {have} pairs, need at least {PAIRS_MIN} for the tuner to have any power"
    if reason := _too_thin_reason(path):
        return reason
    age = datetime.now().timestamp() - path.stat().st_mtime
    if age > PAIRS_MAX_AGE_DAYS * 86400:
        return f"pairs older than {PAIRS_MAX_AGE_DAYS}d"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="run regardless of the window (for testing)")
    ap.add_argument("--cpus", type=int, default=0, help="override the window's CPU budget")
    # Sized from what ONE knob-night actually costs, measured on the live box at 1.9s a query:
    #
    #   scoring the incumbent          1
    #   scoring the carried-forward best  1   (only when earlier nights accepted something)
    #   candidate values               4   (the widest knob has five, minus the current one)
    #   held-out, before and after     2
    #                                 ──
    #                                  8 scoring passes
    #
    # 800 was sized for a hit rate around 5%. Measured 2026-08-14 through 2026-08-16 on the actual
    # pool it runs against: 2.6%-3.5%, not 5% — 800 pairs answers only ~21-28 of them, under
    # tune_retrieval.MIN_HITS (30), so EVERY run of that entire window bailed out at "TOO THIN"
    # before testing a single candidate. All of a 16-hour Saturday (32/32 ticks) and a full nightly
    # window (8/8 ticks) did this — see docs/OPEN-ITEMS-PLAN.md and [[hhh-rollout-verification]]'s
    # sibling finding for the numbers. Re-harvesting does not fix this on its own: harvest_pairs.py
    # hits its own --target long before --scan-limit binds, from the same deterministic slice of the
    # corpus, so the pool — and its hit rate — comes back identical. What actually clears the floor
    # is more of the EXISTING pool per candidate: at a 50% holdout, 3325 pairs leave ~1662 available
    # before this cuts to --sample, and 800 was leaving over half of that on the table. 1600 was
    # measured live (same pool, same code) at recall=0.035 → ~56 answered, comfortably above 30.
    #
    # This roughly doubles the per-candidate cost the math above is built on — a full 8-pass
    # evaluation of one knob may now outrun a single 298-minute weeknight window and carry into the
    # next. That is not a new failure mode: it is exactly what the resumable state
    # (tune_retrieval.py --state) exists for, and it is a real night of partial progress instead of a
    # guaranteed zero. Saturday's 16-hour/6-core window absorbs the extra cost with room to spare.
    #
    # What this does NOT fix: noise falls with the square root, and the gains being chased are the
    # same size as the noise either way. The thing that makes a result trustworthy is the held-out
    # confirmation at the end of every run, not the sample size.
    ap.add_argument("--sample", type=int, default=1600)
    ap.add_argument("--target", type=int, default=5000, help="pairs to harvest when refreshing")
    args = ap.parse_args()

    now = datetime.now(ISRAEL)
    slot = window_for(now)
    if slot is None and not args.force:
        return 0                                    # outside the window: say nothing, do nothing
    ends_at, cpus = slot if slot else (now + timedelta(hours=1), 2)
    cpus = args.cpus or cpus
    budget_s = max(60, int((ends_at - now).total_seconds()))

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{now:%Y-%m-%d_%H%M}.log"
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"nightly eval — {now:%Y-%m-%d %H:%M %Z} | cpus={cpus} "
                  f"| window ends {ends_at:%H:%M} ({budget_s // 60} min)\n\n")

        py = sys.executable
        if reason := _harvest_reason():
            log.write(f"== harvest ({reason})\n")
            # Half the window at most: a harvest that eats the whole night leaves nothing measured.
            # It writes only on success, so a harvest killed here leaves the previous pool intact
            # and the next night simply tries again with the same budget.
            _run([py, str(ROOT / "scripts" / "harvest_pairs.py"),
                  "--target", str(args.target), "--out", PAIRS],
                 cpus=cpus, deadline_s=budget_s // 2, log=log)
            log.write(f"   pool is now {_pairs_count(Path(PAIRS))} pairs\n")
        else:
            log.write(f"== harvest skipped ({_pairs_count(Path(PAIRS))} pairs, "
                      f"under {PAIRS_MAX_AGE_DAYS}d old)\n")

        remaining = max(60, int((ends_at - datetime.now(ISRAEL)).total_seconds()))
        log.write(f"\n== tune ({remaining // 60} min left in the window)\n")
        rc = _run([py, str(ROOT / "scripts" / "tune_retrieval.py"),
                   "--pairs", PAIRS, "--sample", str(args.sample), "--state", STATE],
                  cpus=cpus, deadline_s=remaining, log=log)
        log.write(f"\nfinished rc={rc} at {datetime.now(ISRAEL):%H:%M}\n")

    # The sweep's position, echoed here so "where is this up to" is one small file rather than
    # reading a night's log to find out. rc=124 means the window closed mid-knob: the state was not
    # written, and tonight is simply repeated tomorrow.
    summary: dict = {"ran_at": now.isoformat(), "cpus": cpus, "log": log_path.name,
                     "window_ends": ends_at.isoformat(), "rc": rc,
                     "timed_out": rc == 124, "pairs": _pairs_count(Path(PAIRS))}
    try:
        st = json.loads(Path(STATE).read_text(encoding="utf-8"))
        summary["knobs_done"] = st.get("done", [])
        summary["best"] = st.get("best")
        summary["last"] = (st.get("history") or [None])[-1]
    except (OSError, ValueError):
        summary["knobs_done"] = []
    (LOG_DIR / "latest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"nightly eval done → {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
