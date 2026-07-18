"""Admin CLI for the account blocklist.

There is no admin UI — blocking is an operator action. This is the tool for it. An owner id is the
value the API scopes data to: a Supabase user id (the JWT `sub`) in Supabase mode, or "u_<hash>" in
API-key mode (see the server logs / your users table to find it).

    # Block for a bounded window (hours / days / months) or forever:
    python scripts/manage_bans.py ban <owner_id> --hours 6      --reason "spam"
    python scripts/manage_bans.py ban <owner_id> --days 30      --reason "abuse"
    python scripts/manage_bans.py ban <owner_id> --months 3
    python scripts/manage_bans.py ban <owner_id> --forever      --reason "ToS violation"

    python scripts/manage_bans.py unban <owner_id>
    python scripts/manage_bans.py list

Point it at the same DB the API uses via CHAVRUTA_DB_PATH (defaults to ./chavruta.db).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db as db   # noqa: E402


def _until(args: argparse.Namespace) -> str | None:
    if args.forever:
        return None
    now = datetime.now(UTC)
    if args.hours:
        return (now + timedelta(hours=args.hours)).isoformat()
    if args.days:
        return (now + timedelta(days=args.days)).isoformat()
    if args.months:
        return (now + timedelta(days=30 * args.months)).isoformat()   # 1 month ≈ 30 days
    raise SystemExit("specify a duration: --hours / --days / --months / --forever")


def cmd_ban(args: argparse.Namespace) -> None:
    until = _until(args)
    db.ban_account(args.owner_id, datetime.now(UTC).isoformat(), until, args.reason or "")
    when = "permanently" if until is None else f"until {until}"
    print(f"blocked {args.owner_id} {when}" + (f" — {args.reason}" if args.reason else ""))


def cmd_unban(args: argparse.Namespace) -> None:
    print("unblocked" if db.unban_account(args.owner_id) else "no block found", args.owner_id)


def cmd_list(_args: argparse.Namespace) -> None:
    rows = db.list_bans()
    if not rows:
        print("(no blocks)")
        return
    for r in rows:
        until = r["banned_until"] or "PERMANENT"
        print(f"{r['owner_id']:20}  until={until}  reason={r['reason'] or ''}")


def main() -> None:
    p = argparse.ArgumentParser(description="Manage the account blocklist.")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("ban", help="block an account")
    b.add_argument("owner_id")
    b.add_argument("--hours", type=int)
    b.add_argument("--days", type=int)
    b.add_argument("--months", type=int)
    b.add_argument("--forever", action="store_true")
    b.add_argument("--reason", default="")
    b.set_defaults(func=cmd_ban)

    u = sub.add_parser("unban", help="lift a block")
    u.add_argument("owner_id")
    u.set_defaults(func=cmd_unban)

    lst = sub.add_parser("list", help="list all blocks")
    lst.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
