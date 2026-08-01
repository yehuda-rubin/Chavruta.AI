"""Operator report over the usage telemetry — what the product is used for, when, and what it costs.

There is no analytics UI and no third-party tracker: the measurements sit in the same SQLite the app
uses, and this reads them. Nothing here can show a question, an answer or a source — those are never
copied into the telemetry table (see the schema comment in app/db.py).

    python scripts/usage_report.py                 # last 30 days
    python scripts/usage_report.py --days 7
    python scripts/usage_report.py --all           # everything on record

Point it at the same DB the API uses via CHAVRUTA_DB_PATH (defaults to ./chavruta.db).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db as db  # noqa: E402

_DOW = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]


def _bar(n: int, peak: int, width: int = 28) -> str:
    return "█" * max(0, round(width * n / peak)) if peak else ""


def _pct(part, whole) -> str:
    return f"{(part or 0) / whole * 100:5.1f}%" if whole else "    —"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--all", action="store_true", help="ignore --days")
    ap.add_argument("--top", type=int, default=15, help="how many accounts to list")
    args = ap.parse_args()

    since = None if args.all else (datetime.now(UTC) - timedelta(days=args.days)).isoformat()
    period = "all time" if args.all else f"last {args.days} days"

    h = db.usage_health(since)
    total = h.get("requests") or 0
    if not total:
        print(f"no usage recorded ({period}).")
        return

    accounts = db.count_accounts()

    print(f"═══ Chavruta.AI — usage report · {period} ═══\n")
    print(f"  requests        {total:,}")
    print(f"  users (active)  {h.get('users') or 0:,}  — distinct accounts with a request this period")
    print(f"  accounts (all)  {accounts['total']:,}  — registered, whether or not they've asked anything")
    for plan, n in sorted(accounts["by_plan"].items(), key=lambda kv: kv[1], reverse=True):
        print(f"      {plan or '(none)':<12}{n:,}")
    print(f"  billed tokens   {h.get('tokens') or 0:,}")
    print(f"  grounded        {h.get('grounded') or 0:,}  ({_pct(h.get('grounded'), total)})")
    print(f"  no source       {h.get('no_source') or 0:,}  ({_pct(h.get('no_source'), total)})")
    print(f"  agentic reruns  {h.get('agentic') or 0:,}  ({_pct(h.get('agentic'), total)})")
    print(f"  errors          {h.get('errors') or 0:,}  ({_pct(h.get('errors'), total)})")
    print(f"  avg latency     {(h.get('avg_ms') or 0) / 1000:.1f}s")

    conc = db.usage_concurrency(since)
    if conc.get("peak") is not None:
        # Read directly rather than importing app.api — that import pulls in torch/FlagEmbedding,
        # heavy weight for what should be a fast, read-only reporting script.
        allowed = os.environ.get("CHAVRUTA_MAX_CONCURRENT_GENERATIONS", "2")
        print(f"  concurrency     peak {int(conc['peak'])}  ·  avg {conc['avg']:.2f}"
              f"  (of {allowed} allowed at once)")

    print(f"\n── by mode {'─' * 46}")
    print(f"{'MODE':<12}{'REQ':>7}{'SHARE':>8}{'TOKENS':>12}{'AVG':>9}{'GROUNDED':>10}{'AVG s':>8}")
    for r in db.usage_by_intent(since):
        print(f"{str(r['intent'] or '?'):<12}{r['requests']:>7}{_pct(r['requests'], total):>8}"
              f"{r['tokens'] or 0:>12,}{round(r['avg_tokens'] or 0):>9,}"
              f"{_pct(r['grounded'], r['requests']):>10}{(r['avg_ms'] or 0) / 1000:>8.1f}")

    print(f"\n── by hour (Israel local) {'─' * 31}")
    hours = db.usage_by_hour(since)
    peak = max((r["requests"] for r in hours), default=0)
    for r in hours:
        print(f"  {r['hour']:02d}:00 {r['requests']:>5}  {_bar(r['requests'], peak)}")

    print(f"\n── by day of week {'─' * 39}")
    dows = db.usage_by_dow(since)
    peak = max((r["requests"] for r in dows), default=0)
    for r in dows:
        name = _DOW[r["dow"]] if r["dow"] is not None and r["dow"] < 7 else "?"
        print(f"  {name:<8}{r['requests']:>5}  {_bar(r['requests'], peak)}")

    weeks = db.usage_by_week(since)
    if len(weeks) > 1:      # a single week is just the total again — only show this when it's a trend
        print(f"\n── traction: users per week {'─' * 29}")
        print(f"{'WEEK':<10}{'REQUESTS':>10}{'USERS':>8}")
        for r in weeks:
            print(f"{r['week']:<10}{r['requests']:>10,}{r['users']:>8,}")

    lessons = db.lesson_breakdown(since)
    if lessons:
        print(f"\n── lessons: who they're built for {'─' * 23}")
        print(f"{'AUDIENCE':<12}{'GRADE':<8}{'LENGTH':<9}{'REQ':>6}{'AVG TOKENS':>12}")
        for r in lessons:
            print(f"{str(r['audience'] or '—'):<12}{str(r['grade_band'] or '—'):<8}"
                  f"{str(r['length'] or '—'):<9}{r['requests']:>6}{round(r['avg_tokens'] or 0):>12,}")

    print(f"\n── heaviest accounts {'─' * 36}")
    print(f"{'OWNER':<26}{'REQ':>6}{'TOKENS':>12}{'CALLS':>7}{'GROUNDED':>10}")
    for r in db.usage_by_owner(since, limit=args.top):
        owner = r["owner_id"] or "(deleted account)"
        print(f"{owner[:25]:<26}{r['requests']:>6}{r['tokens'] or 0:>12,}"
              f"{r['calls'] or 0:>7}{_pct(r['grounded'], r['requests']):>10}")

    print("\nNo question, answer or source text is recorded — measurements only.")


if __name__ == "__main__":
    main()
