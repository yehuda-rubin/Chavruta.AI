"""quality_report.py — what the system's answer quality actually looks like in production.

The eval harness (scripts/run_eval.py) measures a fixed question set. This measures the REAL
traffic: every answer already writes a row to `usage_events` carrying the signals that say whether
it was any good — `grounded`, `no_source`, `citations`, `llm_calls`, `error`. Nobody was reading
them as a quality number, so the honest answer to "is the product getting better or worse?" was a
feeling.

This is also step one of any future RL work (docs/REINFORCEMENT_LEARNING.md §5): the same columns
are the verifiable reward signal, and a reward you cannot yet measure is a reward you cannot train
on. Worth running whether or not training ever happens.

    python scripts/quality_report.py                     # last 30 days
    python scripts/quality_report.py --since 7d --json   # machine-readable

Reads the DB named by CHAVRUTA_DB_PATH (same as the API). Read-only — it never writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta

_WINDOWS = {"7d": 7, "30d": 30, "90d": 90}


def _cutoff(since: str) -> str | None:
    if since == "all":
        return None
    days = _WINDOWS.get(since)
    if days is None:
        raise SystemExit(f"--since must be one of {sorted(_WINDOWS)} or 'all'")
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def collect(db_path: str, since: str) -> dict:
    cutoff = _cutoff(since)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    where, args = ("WHERE at >= ?", (cutoff,)) if cutoff else ("", ())

    def q(sql: str, extra: tuple = ()):
        return conn.execute(sql, args + extra).fetchall()

    total = q(f"SELECT COUNT(*) c FROM usage_events {where}")[0]["c"]
    if not total:
        return {"since": since, "requests": 0}

    row = q(f"""
        SELECT
          SUM(CASE WHEN grounded = 1 THEN 1 ELSE 0 END)          AS grounded,
          SUM(CASE WHEN no_source = 1 THEN 1 ELSE 0 END)         AS no_source,
          SUM(CASE WHEN error IS NOT NULL AND error != '' THEN 1 ELSE 0 END) AS errors,
          SUM(CASE WHEN llm_calls > 1 THEN 1 ELSE 0 END)         AS multi_round,
          AVG(citations)                                          AS avg_citations,
          AVG(ms)                                                 AS avg_ms
        FROM usage_events {where}
    """)[0]

    grounded, no_source = row["grounded"] or 0, row["no_source"] or 0
    errors, multi_round = row["errors"] or 0, row["multi_round"] or 0
    # Answered-but-ungrounded is the number that matters most: not an honest "no source found", not
    # a crash — an answer that went out with nothing citable behind it (Principle I's failure mode).
    ungrounded = max(0, total - grounded - no_source - errors)

    by_intent = [
        {"intent": r["intent"] or "?", "requests": r["c"],
         "grounded_rate": round((r["g"] or 0) / r["c"], 4) if r["c"] else 0.0,
         "no_source_rate": round((r["ns"] or 0) / r["c"], 4) if r["c"] else 0.0}
        for r in q(f"""
            SELECT intent, COUNT(*) c,
                   SUM(CASE WHEN grounded = 1 THEN 1 ELSE 0 END) g,
                   SUM(CASE WHEN no_source = 1 THEN 1 ELSE 0 END) ns
            FROM usage_events {where} GROUP BY intent ORDER BY c DESC
        """)
    ]
    conn.close()

    return {
        "since": since,
        "requests": total,
        "grounded_rate": round(grounded / total, 4),
        "no_source_rate": round(no_source / total, 4),
        "ungrounded_rate": round(ungrounded / total, 4),
        "error_rate": round(errors / total, 4),
        "multi_round_rate": round(multi_round / total, 4),
        "avg_citations": round(row["avg_citations"] or 0, 2),
        "avg_ms": int(row["avg_ms"] or 0),
        "by_intent": by_intent,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Answer-quality report from production usage")
    ap.add_argument("--since", default="30d", help="7d | 30d | 90d | all")
    ap.add_argument("--db", default=os.environ.get("CHAVRUTA_DB_PATH", "chavruta.db"))
    ap.add_argument("--json", action="store_true", help="print the raw JSON")
    args = ap.parse_args()

    try:
        rep = collect(args.db, args.since)
    except sqlite3.OperationalError as exc:
        raise SystemExit(f"cannot read {args.db!r}: {exc}") from exc

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return

    if not rep["requests"]:
        print(f"no requests in the last {args.since}")
        return

    pct = lambda x: f"{100 * x:5.1f}%"  # noqa: E731 — a formatting alias, not a policy
    print(f"\nAnswer quality — last {rep['since']} · {rep['requests']} requests\n")
    print(f"  grounded (cited a real source)   {pct(rep['grounded_rate'])}")
    print(f"  honest 'no source found'         {pct(rep['no_source_rate'])}")
    print(f"  ANSWERED WITHOUT GROUNDING       {pct(rep['ungrounded_rate'])}   <- the one to drive down")
    print(f"  errors                           {pct(rep['error_rate'])}")
    print(f"  needed a second retrieval round  {pct(rep['multi_round_rate'])}   <- round-one retrieval missed")
    print(f"\n  avg citations per answer  {rep['avg_citations']}")
    print(f"  avg latency               {rep['avg_ms'] / 1000:.1f}s\n")
    print("  by mode:")
    for r in rep["by_intent"]:
        print(f"    {r['intent']:<10} {r['requests']:>6} req   grounded {pct(r['grounded_rate'])}"
              f"   no-source {pct(r['no_source_rate'])}")
    print()


if __name__ == "__main__":
    sys.exit(main())
