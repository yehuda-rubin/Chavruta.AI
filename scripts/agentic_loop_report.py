"""Aggregate the "agentic request done" lines captured by agentic_log_capture.sh into a report.

Reads lines shaped like (docker --timestamps + agentic.py's log line):
    2026-08-23T19:32:40.225362337Z 19:32:40 INFO ... fetched=72 rounds_out_tokens=8370 ...

fetched=0 means the loop answered in one round (no ===NEED_SOURCES=== fired). fetched>0 means
at least one extra round was needed. rounds_out_tokens + rounds_prompt_tokens is the request's
whole token cost across every round it took — the thing that answers "did this get cheaper".

Usage:
    ssh ... "cat ~/chavruta/logs/agentic_requests.log" | python scripts/agentic_loop_report.py
    python scripts/agentic_loop_report.py logs/agentic_requests.log
    python scripts/agentic_loop_report.py logs/agentic_requests.log --split-at 2026-09-01T00:00:00Z
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

_LINE_RE = (
    r"^(?P<ts>\S+)\s.*agentic request done: "
    r"(?:rounds=(?P<rounds>\d+)\s+)?"     # added later — older captured lines won't have it
    r"rounds_out_tokens=(?P<out>\d+) rounds_prompt_tokens=(?P<prompt>\d+) "
    r"budget=\S+ fetched=(?P<fetched>\d+)"
)


@dataclass(frozen=True)
class Row:
    ts: datetime
    out_tokens: int
    prompt_tokens: int
    fetched: int
    rounds: int | None


def parse(lines: list[str]) -> list[Row]:
    import re

    pat = re.compile(_LINE_RE)
    seen: set[str] = set()
    rows: list[Row] = []
    for line in lines:
        line = line.rstrip("\n")
        if not line or line in seen:
            continue          # exact-line dedup: --since overlap re-captures the boundary line
        seen.add(line)
        m = pat.match(line)
        if not m:
            continue
        ts = datetime.fromisoformat(m["ts"].replace("Z", "+00:00"))
        rounds = int(m["rounds"]) if m["rounds"] is not None else None
        rows.append(Row(ts, int(m["out"]), int(m["prompt"]), int(m["fetched"]), rounds))
    rows.sort(key=lambda r: r.ts)
    return rows


def report(rows: list[Row], label: str) -> str:
    if not rows:
        return f"{label}: no requests"
    n = len(rows)
    single_round = sum(1 for r in rows if r.fetched == 0)
    totals = [r.out_tokens + r.prompt_tokens for r in rows]
    span = f"{rows[0].ts.isoformat()} .. {rows[-1].ts.isoformat()}"
    lines = [
        f"{label} (n={n}, {span})",
        f"  single-round (no NEED_SOURCES): {single_round}/{n} ({single_round / n:.0%})",
        f"  avg total tokens/request: {statistics.fmean(totals):.0f}"
        f" (median {statistics.median(totals):.0f})",
        f"  avg out tokens: {statistics.fmean(r.out_tokens for r in rows):.0f}"
        f" | avg prompt tokens: {statistics.fmean(r.prompt_tokens for r in rows):.0f}",
    ]
    with_rounds = [r.rounds for r in rows if r.rounds is not None]
    if with_rounds:
        lines.append(
            f"  avg rounds: {statistics.fmean(with_rounds):.2f}"
            f" (median {statistics.median(with_rounds):.0f}, n={len(with_rounds)}"
            f"{'' if len(with_rounds) == n else f'/{n} — older lines predate rounds= logging'})"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="log file to read (default: stdin)")
    ap.add_argument("--split-at", help="ISO timestamp — report before/after separately (e.g. a deploy time)")
    args = ap.parse_args()

    lines = (open(args.path, encoding="utf-8") if args.path else sys.stdin).readlines()
    rows = parse(lines)

    if not rows:
        print("no matching lines found")
        return 0

    if args.split_at:
        cutoff = datetime.fromisoformat(args.split_at.replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        before = [r for r in rows if r.ts < cutoff]
        after = [r for r in rows if r.ts >= cutoff]
        print(report(before, "BEFORE"))
        print()
        print(report(after, "AFTER"))
    else:
        print(report(rows, "ALL"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
