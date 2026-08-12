"""Run the retrieval harvest + tune inside a permitted window, on a bounded slice of the machine.

SCHEDULE (Israel local time, decided here rather than in cron)
--------------------------------------------------------------
    every night   00:00-05:00   on 2 CPUs
    Saturday      00:00-16:00   on 6 CPUs

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

STOPPING
--------
The run is bounded by the window, not by the work: whatever is unfinished at 05:00 is abandoned and
picked up the next night. That is why the harvest writes its output before tuning starts, and why
the tuner's own progress is printed as it goes — a run cut off halfway still leaves the night's
measurements on disk instead of nothing.
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
NIGHTLY_WINDOW = (0, 5, 2)       # 00:00-05:00 on two cores

# Where GENERATED artefacts go — harvested pairs and each night's log. Deliberately separable from
# eval/, which holds the hand-written question sets: in the container those are mounted READ-ONLY
# (curated input, version-controlled) while this points at a writable volume. Sharing one directory
# would mean either making the curated sets writable by the job or having no output at all — the
# first run failed with exactly that permission error, which is the right thing to have hit.
OUT_ROOT = Path(os.environ.get("CHAVRUTA_EVAL_OUT") or (ROOT / "eval"))
LOG_DIR = OUT_ROOT / "nightly"
PAIRS = str(OUT_ROOT / "harvested_pairs_v1.jsonl")
# Re-harvesting every night would burn the window re-deriving pairs that have not changed — the
# corpus is static between loads. Refresh only when the file is missing or older than this.
PAIRS_MAX_AGE_DAYS = 14


def window_for(now: datetime) -> tuple[datetime, int] | None:
    """(when this window ends, how many CPUs) — or None if `now` is outside every window."""
    start_h, end_h, cpus = SATURDAY_WINDOW if now.weekday() == 5 else NIGHTLY_WINDOW
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


def _pairs_are_stale() -> bool:
    path = Path(PAIRS)
    if not path.exists():
        return True
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age > PAIRS_MAX_AGE_DAYS * 86400


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="run regardless of the window (for testing)")
    ap.add_argument("--cpus", type=int, default=0, help="override the window's CPU budget")
    ap.add_argument("--sample", type=int, default=150)
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
        if _pairs_are_stale():
            log.write(f"== harvest (pairs missing or older than {PAIRS_MAX_AGE_DAYS}d)\n")
            # Half the window at most: a harvest that eats the whole night leaves nothing measured.
            _run([py, str(ROOT / "scripts" / "harvest_pairs.py"),
                  "--target", str(args.target), "--out", PAIRS],
                 cpus=cpus, deadline_s=budget_s // 2, log=log)
        else:
            log.write("== harvest skipped (pairs are current)\n")

        remaining = max(60, int((ends_at - datetime.now(ISRAEL)).total_seconds()))
        log.write(f"\n== tune ({remaining // 60} min left in the window)\n")
        rc = _run([py, str(ROOT / "scripts" / "tune_retrieval.py"),
                   "--pairs", PAIRS, "--sample", str(args.sample)],
                  cpus=cpus, deadline_s=remaining, log=log)
        log.write(f"\nfinished rc={rc} at {datetime.now(ISRAEL):%H:%M}\n")

    (LOG_DIR / "latest.json").write_text(json.dumps({
        "ran_at": now.isoformat(), "cpus": cpus, "log": log_path.name,
        "window_ends": ends_at.isoformat(),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"nightly eval done → {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
