"""Operator CLI for refunds.

Terms §10 promises a refund on cancellation within 14 days of a distance sale. This is the tool that
keeps that promise, and the only place in the system that gives money back.

Like coupons, refunds are deliberately NOT an HTTP surface. A refund is irreversible, and there is no
version of a self-service refund button that is safer than an operator reading one charge and typing
its id. So the flow is: find the charge, look at the quote, confirm.

    python scripts/refund.py list                        # recent charges, newest first
    python scripts/refund.py list --days 30
    python scripts/refund.py quote 12                    # what may be withheld from charge #12
    python scripts/refund.py pay 12 --owner u_abc123     # refund it and cancel the subscription
    python scripts/refund.py pay 12 --amount 20 --reason "ביטול תוך 14 יום"
    python scripts/refund.py pay 12 --keep-subscription  # refund without cancelling

`pay` asks for confirmation unless --yes is given. The default amount is the whole charge MINUS the
lawful cancellation fee (5% or ₪100, the lower) — see plans.refund_quote for why the pro-rata share
of days already used is shown but not deducted by default.

--owner matters: the ledger is deliberately anonymous, so nothing in a charge row says whose it is.
Without it the money goes back and the subscription keeps billing them next month. Find the owner id
in the subscriptions table, or pass --keep-subscription when you mean it.

Point it at the same DB the API uses via CHAVRUTA_DB_PATH (defaults to ./chavruta.db), and give it
the same PAYPLUS_* environment the server runs with — including PAYPLUS_MODE, since 'sandbox' will
happily pretend.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db as db  # noqa: E402
from app import plans  # noqa: E402
from app.billing import payplus, service  # noqa: E402


def _days_since(iso: str) -> int:
    try:
        then = datetime.fromisoformat(iso)
        if then.tzinfo is None:
            then = then.replace(tzinfo=UTC)
        return max(0, (datetime.now(UTC) - then).days)
    except (TypeError, ValueError):
        return 0


def cmd_list(args: argparse.Namespace) -> None:
    since = (datetime.now(UTC) - timedelta(days=args.days)).isoformat()
    rows = db.list_charges(since=since)
    if not rows:
        print(f"no charges in the last {args.days} days")
        return
    print(f"{'id':>5}  {'when':<20} {'amount':>9}  {'plan':<12} {'txn':<38} note")
    for r in rows:
        amount = float(r["amount"])
        refunded = db.refunded_total(r.get("txn_uid") or "") if amount > 0 else 0.0
        flag = "  ↩ refunded" if refunded >= amount > 0 else (
            f"  ↩ ₪{refunded:.2f} back" if refunded else "")
        print(f"{r['id']:>5}  {str(r['charged_at'])[:19]:<20} {amount:>9.2f}  "
              f"{str(r.get('plan') or ''):<12} {str(r.get('txn_uid') or '—'):<38} "
              f"{r.get('note') or ''}{flag}")


def _quote(charge_id: int) -> tuple[dict, dict]:
    row = db.get_charge(charge_id)
    if not row:
        raise SystemExit(f"no such charge: {charge_id}")
    q = plans.refund_quote(float(row["amount"]), days_used=_days_since(row["charged_at"]),
                           cycle=row.get("cycle"))
    return row, q


def cmd_quote(args: argparse.Namespace) -> None:
    row, q = _quote(args.charge_id)
    days = _days_since(row["charged_at"])
    already = db.refunded_total(row.get("txn_uid") or "")
    print(f"charge #{row['id']} — {str(row['charged_at'])[:19]} — {row.get('plan')}/{row.get('cycle')}")
    print(f"  paid            ₪{q['amount']:.2f}")
    print(f"  days used       {days} of {plans.period_days(row.get('cycle'))}")
    print(f"  cancellation fee ₪{q['fee']:.2f}   (5% or ₪100, the lower — Consumer Protection Law)")
    print(f"  days consumed   ₪{q['consumed']:.2f}   (shown, NOT deducted by default)")
    print(f"  max withholding ₪{q['max_deduct']:.2f}")
    if already:
        print(f"  already refunded ₪{already:.2f}")
    print(f"  → we refund     ₪{max(0.0, q['refund'] - already):.2f}")
    if days > 14:
        print("  note: past the 14-day distance-sale window; refunding is a goodwill decision, "
              "not an obligation.")
    if not row.get("txn_uid"):
        print("  ⚠ no transaction uid on this row — refund it from the PayPlus dashboard.")


def cmd_pay(args: argparse.Namespace) -> None:
    row, q = _quote(args.charge_id)
    already = db.refunded_total(row.get("txn_uid") or "")
    give = args.amount if args.amount is not None else round(max(0.0, q["refund"] - already), 2)
    mode = "PRODUCTION" if not payplus._sandbox() else "sandbox"   # noqa: SLF001 — operator needs it
    print(f"about to refund ₪{give:.2f} of charge #{row['id']} (₪{q['amount']:.2f}, "
          f"{str(row['charged_at'])[:19]}) via PayPlus [{mode}]")
    if args.owner:
        print(f"  and cancel the subscription of {args.owner}")
    elif not args.keep_subscription:
        print("  ⚠ NO --owner given: the subscription will NOT be cancelled and will bill again.")
    if not args.yes:
        if input("type 'refund' to proceed: ").strip().lower() != "refund":
            raise SystemExit("aborted")
    out = service.refund(row["id"], amount=give, email=args.email or "", name=args.name or "",
                         reason=args.reason or "", owner_id=args.owner,
                         cancel_subscription=not args.keep_subscription)
    print(f"✅ refunded ₪{out['refunded']:.2f} (ledger #{out['ledger_id']}, "
          f"credit note {out['invoice_ref'] or '—'}, ₪{out['remaining']:.2f} still refundable)")
    print("   verify it in the PayPlus dashboard — the provider's response shape is not documented "
          "and this is read from the HTTP status.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="recent charges")
    pl.add_argument("--days", type=int, default=60)
    pl.set_defaults(func=cmd_list)

    pq = sub.add_parser("quote", help="what may lawfully be withheld from a charge")
    pq.add_argument("charge_id", type=int)
    pq.set_defaults(func=cmd_quote)

    pp = sub.add_parser("pay", help="actually refund a charge")
    pp.add_argument("charge_id", type=int)
    pp.add_argument("--amount", type=float, default=None, help="default: charge minus the fee")
    pp.add_argument("--owner", default="", help="owner id, so the subscription is cancelled too")
    pp.add_argument("--keep-subscription", action="store_true")
    pp.add_argument("--reason", default="", help="goes on the credit note and the ledger row")
    pp.add_argument("--email", default="", help="for the credit note")
    pp.add_argument("--name", default="", help="for the credit note")
    pp.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    pp.set_defaults(func=cmd_pay)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
