"""Admin CLI for coupon codes.

Coupons are issued by the operator, never through the API — there is no admin HTTP surface to
protect, and one fewer privileged endpoint is one fewer thing to get wrong. Users only ever call
POST /coupons/redeem.

A coupon grants ONE of two things:
  • a PLAN for N days  — a time-boxed tier; it lapses on its own via the billing sweeper
  • CREDITS            — prepaid generations, spent only after the daily quota runs out

    # 30 days of the 'pro' tier, one person:
    python scripts/manage_coupons.py plan --plan pro --days 30 --note "R' Cohen, trial"

    # A campaign: 100 people get 14 days of 'basic', code dies after a month:
    python scripts/manage_coupons.py plan --plan basic --days 14 --max 100 --expires-in 30 \
        --note "Shavuot campaign"

    # 200 credits, single use, with a code you choose:
    python scripts/manage_coupons.py credits --credits 200 --code CHV-SHIUR-200

    python scripts/manage_coupons.py list                  # every code + how many uses are left
    python scripts/manage_coupons.py show CHV-A1B2-C3D4    # one code + who redeemed it
    python scripts/manage_coupons.py revoke CHV-A1B2-C3D4  # stop future redemptions
    python scripts/manage_coupons.py restore CHV-A1B2-C3D4
    python scripts/manage_coupons.py tiers                 # the tier table + current prices

Revoking never claws back what was already granted — it only stops the code being used again.

Point it at the same DB the API uses via CHAVRUTA_DB_PATH (defaults to ./chavruta.db).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.coupons as coupons  # noqa: E402
import app.db as db  # noqa: E402
from app import plans  # noqa: E402


def cmd_plan(args: argparse.Namespace) -> None:
    code = coupons.issue_plan_coupon(
        plan=args.plan, days=args.days, code=args.code or "", max_redemptions=args.max,
        expires_in_days=args.expires_in, note=args.note or "")
    t = plans.tier(args.plan)
    quota = plans.daily_quota(t.id)
    print(f"✅ {code}")
    print(f"   grants : {t.name_en} ({t.id}) for {args.days} days "
          f"— {'unlimited' if quota == 0 else str(quota) + '/day'}")
    print(f"   uses   : {'unlimited' if args.max == 0 else args.max}")
    if args.expires_in:
        print(f"   code expires in {args.expires_in} days")


def cmd_credits(args: argparse.Namespace) -> None:
    code = coupons.issue_credit_coupon(
        credits=args.credits, code=args.code or "", max_redemptions=args.max,
        expires_in_days=args.expires_in, note=args.note or "")
    print(f"✅ {code}")
    print(f"   grants : {args.credits} credits "
          f"(a question costs {plans.credit_cost('qa')}, a lesson {plans.credit_cost('lesson')})")
    print(f"   uses   : {'unlimited' if args.max == 0 else args.max}")
    if args.expires_in:
        print(f"   code expires in {args.expires_in} days")


def _describe(c: dict) -> str:
    if c["kind"] == "credits":
        return f"{c['credits']} credits"
    return f"{c['plan']} for {c['days']}d"


def cmd_list(args: argparse.Namespace) -> None:
    rows = db.list_coupons()
    if not rows:
        print("no coupons issued yet")
        return
    print(f"{'CODE':<20} {'GRANTS':<22} {'USED':<10} {'STATE':<9} NOTE")
    for c in rows:
        cap = int(c["max_redemptions"] or 0)
        used = f"{c['redeemed_count']}/{'∞' if cap == 0 else cap}"
        state = "active" if c["active"] else "revoked"
        if c["active"] and cap and int(c["redeemed_count"]) >= cap:
            state = "used up"
        print(f"{c['code']:<20} {_describe(c):<22} {used:<10} {state:<9} {c['note'] or ''}")


def cmd_show(args: argparse.Namespace) -> None:
    code = coupons.normalize(args.code)
    c = db.get_coupon(code)
    if not c:
        raise SystemExit(f"no such coupon: {args.code}")
    print(f"code       : {c['code']}")
    print(f"grants     : {_describe(c)}")
    print(f"redeemed   : {c['redeemed_count']} of "
          f"{'unlimited' if not c['max_redemptions'] else c['max_redemptions']}")
    print(f"state      : {'active' if c['active'] else 'REVOKED'}")
    print(f"expires    : {c['expires_at'] or 'never'}")
    print(f"created    : {c['created_at']}")
    print(f"note       : {c['note'] or ''}")
    reds = db.list_redemptions(code)
    print(f"\nredemptions ({len(reds)}):")
    for r in reds:
        print(f"  {r['redeemed_at'][:19]}  {r['owner_id']}  → {r['granted']}")


def cmd_revoke(args: argparse.Namespace) -> None:
    if not db.set_coupon_active(coupons.normalize(args.code), False):
        raise SystemExit(f"no such coupon: {args.code}")
    print(f"🚫 {args.code} revoked — no further redemptions. Already-granted access is untouched.")


def cmd_restore(args: argparse.Namespace) -> None:
    if not db.set_coupon_active(coupons.normalize(args.code), True):
        raise SystemExit(f"no such coupon: {args.code}")
    print(f"✅ {args.code} active again")


def cmd_tiers(args: argparse.Namespace) -> None:
    print(f"{'TIER':<14} {'₪/MONTH':>9} {'PER DAY':>10}")
    for t in plans.TIERS:
        q = plans.daily_quota(t.id)
        print(f"{t.id:<14} {plans.price_ils(t.id):>9.2f} {'unlimited' if q == 0 else q:>10}")
    print(f"\ncredit cost per generation: qa={plans.credit_cost('qa')} "
          f"halacha={plans.credit_cost('halacha')} lesson={plans.credit_cost('lesson')}")
    print("override any of it with env vars — see app/plans.py")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--code", help="use this code instead of a generated one")
        p.add_argument("--max", type=int, default=1, help="max redemptions (0 = unlimited)")
        p.add_argument("--expires-in", type=int, dest="expires_in",
                       help="days until the CODE stops working")
        p.add_argument("--note", help="why it was issued")

    p = sub.add_parser("plan", help="issue a coupon granting a plan for N days")
    p.add_argument("--plan", required=True, choices=[t.id for t in plans.TIERS])
    p.add_argument("--days", type=int, required=True)
    _common(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("credits", help="issue a coupon granting prepaid generations")
    p.add_argument("--credits", type=int, required=True)
    _common(p)
    p.set_defaults(func=cmd_credits)

    p = sub.add_parser("list", help="all coupons")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="one coupon + its redemptions")
    p.add_argument("code")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("revoke", help="stop future redemptions of a code")
    p.add_argument("code")
    p.set_defaults(func=cmd_revoke)

    p = sub.add_parser("restore", help="undo a revoke")
    p.add_argument("code")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("tiers", help="show the tier table and prices in effect")
    p.set_defaults(func=cmd_tiers)

    args = ap.parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(f"❌ {exc}") from exc


if __name__ == "__main__":
    main()
