"""Operator review queue for flagged messages — both user self-reports and the automatic keyword
scan (app/moderation.py). There is no admin HTTP endpoint for this (same reasoning as
scripts/manage_coupons.py: an admin endpoint is attack surface that needs its own protecting,
issuing/reviewing from the command line needs nothing extra).

    python scripts/moderation_report.py                  # unreviewed backlog (default)
    python scripts/moderation_report.py --reviewed        # already-handled reports
    python scripts/moderation_report.py --mark-reviewed 17    # handled report #17

Point it at the same DB the API uses via CHAVRUTA_DB_PATH (defaults to ./chavruta.db).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db as db  # noqa: E402


def _print_report(r: dict) -> None:
    owner = r["owner_id"] or "(deleted account)"
    text = (r["text"] or "").replace("\n", " ")
    snippet = text[:200] + ("…" if len(text) > 200 else "")
    print(f"\n[{r['id']}] {r['source']}:{r['reason']}  ·  {r['role']}  ·  {owner}  ·  {r['created_at']}")
    print(f"    session {r['session_id']}  ·  message {r['message_id']}")
    print(f"    {snippet}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reviewed", action="store_true", help="show already-reviewed reports instead")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--mark-reviewed", type=int, metavar="ID", help="mark report ID as handled")
    args = ap.parse_args()

    if args.mark_reviewed is not None:
        ok = db.mark_report_reviewed(args.mark_reviewed)
        print(f"report {args.mark_reviewed}: {'marked reviewed' if ok else 'not found or already reviewed'}")
        return

    rows = db.list_flagged_messages(reviewed=args.reviewed, limit=args.limit)
    label = "reviewed" if args.reviewed else "awaiting review"
    if not rows:
        print(f"nothing {label}.")
        return
    print(f"═══ {len(rows)} report(s) {label} ═══")
    for r in rows:
        _print_report(r)
    if not args.reviewed:
        print(f"\nmark one handled: python scripts/moderation_report.py --mark-reviewed <id>")


if __name__ == "__main__":
    main()
