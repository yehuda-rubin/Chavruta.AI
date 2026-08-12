"""Coupon issuing and redemption.

A coupon grants one of two things:
  • a PLAN for a fixed number of days — a time-boxed tier (see app/plans.py), or
  • CREDITS — prepaid generations that outlive the day and are spent once the daily cap runs out.

Issuing is an operator action with no HTTP surface (scripts/manage_coupons.py); the only thing
exposed to users is redemption. Redemption is the interesting half security-wise: it is a public
guessing target that hands out paid access, so codes carry real entropy and attempts are throttled
per account on top of the per-IP limiter.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import string
import threading
import time
from datetime import UTC, datetime, timedelta

import app.db as db
import app.orgs as orgs
from app import plans

_log = logging.getLogger("chavruta.coupons")

# Unambiguous alphabet: no O/0, I/1, or U (which invites typos when read aloud over the phone).
_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "OI01U")
_GROUP = 4
_GROUPS = 3          # 12 chars from a 31-symbol alphabet ≈ 59 bits — not guessable
_VALID = re.compile(r"^[A-Z0-9]{4,32}$")


def normalize(code: str) -> str:
    """The stored form: upper-case, no dashes or spaces, so 'chv-a1b2-c3d4' and 'CHVA1B2C3D4' are the
    same coupon to a user typing either."""
    return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()


def generate_code(prefix: str = "") -> str:
    """A fresh random code, hyphenated for readability. The entropy is what stops enumeration — a
    short or sequential code would be found by the same loop the rate limiter is there to slow."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP * _GROUPS))
    grouped = "-".join(body[i:i + _GROUP] for i in range(0, len(body), _GROUP))
    p = normalize(prefix)
    return f"{p}-{grouped}" if p else grouped


# ── Issuing (operator) ───────────────────────────────────────────────────────
def issue_plan_coupon(*, plan: str, days: int, code: str = "", max_redemptions: int = 1,
                      expires_in_days: int | None = None, note: str = "") -> str:
    """Create a coupon granting `plan` for `days`. Returns the code as issued (with dashes)."""
    if not plans.is_valid_plan(plan):
        raise ValueError(f"unknown plan {plan!r}; valid: {[t.id for t in plans.TIERS]}")
    if days <= 0:
        raise ValueError("days must be positive")
    return _issue(kind="plan", code=code, plan=plans.canonical(plan), days=int(days),
                  credits=None, max_redemptions=max_redemptions,
                  expires_in_days=expires_in_days, note=note)


def issue_credit_coupon(*, credits: int, code: str = "", max_redemptions: int = 1,
                        expires_in_days: int | None = None, note: str = "") -> str:
    """Create a coupon granting `credits` prepaid generations."""
    if credits <= 0:
        raise ValueError("credits must be positive")
    return _issue(kind="credits", code=code, plan=None, days=None, credits=int(credits),
                  max_redemptions=max_redemptions, expires_in_days=expires_in_days, note=note)


def _issue(*, kind: str, code: str, plan: str | None, days: int | None, credits: int | None,
           max_redemptions: int, expires_in_days: int | None, note: str) -> str:
    display = code.strip() if code.strip() else generate_code()
    stored = normalize(display)
    if not _VALID.match(stored):
        raise ValueError("code must be 4-32 letters/digits (dashes are ignored)")
    now = datetime.now(UTC)
    expires_at = (now + timedelta(days=expires_in_days)).isoformat() if expires_in_days else None
    ok = db.create_coupon(stored, kind=kind, created_at=now.isoformat(), plan=plan, days=days,
                          credits=credits, max_redemptions=max(0, int(max_redemptions)),
                          expires_at=expires_at, note=note)
    if not ok:
        raise ValueError(f"coupon {display!r} already exists")
    _log.info("coupon issued: %s kind=%s plan=%s days=%s credits=%s max=%s",
              stored, kind, plan, days, credits, max_redemptions)
    return display


# ── Redemption throttle ──────────────────────────────────────────────────────
# Codes carry ~59 bits, so guessing is already impractical; this bounds the attempt rate anyway so a
# scripted hunt is not free, and so a leaked partial code cannot be completed by brute force. Keyed
# per account, in-process — the same single-instance caveat as the IP limiter in app/security.py.
_MAX_ATTEMPTS = int(os.environ.get("CHAVRUTA_COUPON_ATTEMPTS_PER_HOUR", "10"))
_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def _throttled(owner_id: str) -> bool:
    if _MAX_ATTEMPTS <= 0:
        return False
    now = time.monotonic()
    with _attempts_lock:
        hits = [t for t in _attempts.get(owner_id, ()) if t > now - 3600]
        if len(hits) >= _MAX_ATTEMPTS:
            _attempts[owner_id] = hits
            return True
        hits.append(now)
        _attempts[owner_id] = hits
        if len(_attempts) > 10_000:        # bound the dict under many distinct accounts
            for k in [k for k, v in _attempts.items() if not any(t > now - 3600 for t in v)]:
                del _attempts[k]
    return False


def _clear_throttle(owner_id: str) -> None:
    """A successful redemption shouldn't count against the user's attempts."""
    with _attempts_lock:
        _attempts.pop(owner_id, None)


# ── Redemption (user) ────────────────────────────────────────────────────────
class RedeemError(Exception):
    """Redemption refused. `reason` is a stable machine code; the API maps it to a message."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def redeem(owner_id: str, code: str, *, now: datetime | None = None,
           bypass_throttle: bool = False) -> dict:
    """Apply a coupon to an account. Returns a summary of what was granted, with a `mode` of
    "grant" (time-boxed plan, no active paid subscription), "discount" (ILS credit rebated off the
    next PayPlus charge(s), because the coupon's plan is at or below what's already being paid for),
    or "boost" (temporary upgrade layered on top of an active PayPlus subscription, reverting to the
    real paid plan when the coupon's days run out) — or "credits" for a credits coupon.

    Raises RedeemError with one of: throttled · invalid · already_redeemed · exhausted · expired ·
    downgrade.

    `bypass_throttle` is for the operator grant path (/admin/grant), which issues a fresh code and
    redeems it on the account's behalf. The throttle exists because redemption is a public guessing
    target; an admin handing out access is not guessing, and an operator granting to several accounts
    in a row would otherwise lock themselves out after ten.
    """
    if owner_id == "local":
        raise RedeemError("sign_in_required")
    stored = normalize(code)
    if not _VALID.match(stored):
        raise RedeemError("invalid")
    if not bypass_throttle and _throttled(owner_id):
        raise RedeemError("throttled")

    now = now or datetime.now(UTC)
    c = db.get_coupon(stored)
    if c is None:
        raise RedeemError("invalid")

    kind = c["kind"]
    # A school member spends the org's pool and nothing else — there is no personal allowance, no
    # credit fallback and no BYOK path behind it (app/api.py::_reserve_tokens branches on
    # orgs.quota_context BEFORE any of those). So a personal plan here would grant a tier that
    # changes nothing, and credits would be handed out that can never be spent. Refusing is the
    # honest answer; granting silently would look like it worked. This also covers /admin/grant,
    # which mints a code and redeems it on the account's behalf through this same function.
    #
    # Checked HERE rather than at the top because the answer depends on what the coupon grants: the
    # account that owns the school must be able to receive the school's own institutional plan, which
    # is exactly how the operator provisions or extends one.
    if orgs.refuse_personal_purchase(owner_id, c["plan"] if kind == "plan" else None):
        raise RedeemError("org_member")

    set_plan_to = period_end = None
    add_credits = 0

    if kind == "credits":
        add_credits = int(c["credits"] or 0)
        granted = f"{add_credits} credits"
    elif kind == "plan":
        target = plans.canonical(c["plan"])
        current = plans.canonical(db.get_plan(owner_id))
        sub = db.get_subscription(owner_id) or {}
        days = int(c["days"] or 0)
        # A live PayPlus subscription keeps its own period and provider_ref — overwriting them here
        # would silently detach the account from the recurring charge it is still paying. So a coupon
        # redeemed on top of one never touches plan/provider_ref/current_period_end directly; instead
        # it becomes a discount (target at or below what's already paid for) or a temporary boost
        # (target above it) — see _redeem_against_active_subscription.
        if sub.get("provider") == "payplus" and sub.get("status") == "active":
            return _redeem_against_active_subscription(
                owner_id, stored, kind, target=target, current=current, days=days,
                sub=sub, now=now)
        # No active paid subscription (free account, or a coupon-granted plan only): a coupon may
        # only add access. Redeeming a 'basic' code while on 'pro' would otherwise be a
        # self-inflicted downgrade — refuse instead of quietly taking access away.
        if plans.rank(target) < plans.rank(current):
            raise RedeemError("downgrade")
        # Extend from whatever paid period is still running, not from today, so redeeming two codes
        # stacks instead of the second one throwing away the remainder of the first.
        base = now
        existing_end = sub.get("current_period_end")
        if existing_end and plans.rank(current) == plans.rank(target):
            try:
                parsed = datetime.fromisoformat(existing_end)
                base = max(base, parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC))
            except ValueError:
                pass
        set_plan_to = target
        period_end = (base + timedelta(days=days)).isoformat()
        granted = f"plan {target} for {days} days"
    else:
        _log.error("coupon %s has unknown kind %r", stored, kind)
        raise RedeemError("invalid")

    status = db.redeem_coupon(stored, owner_id, now.isoformat(), granted,
                              set_plan_to=set_plan_to, period_end=period_end,
                              add_credits_amount=add_credits)
    if status != "ok":
        # not_found/inactive both mean "no such usable code" to the user — saying which would let a
        # prober tell a real-but-revoked code from a wrong guess.
        raise RedeemError({"not_found": "invalid", "inactive": "invalid"}.get(status, status))

    _clear_throttle(owner_id)
    # A school provisioned or extended by coupon — the path refuse_personal_purchase deliberately
    # allows — has to reach the org row too. Only the PAID path synced it, while the coupon's expiry
    # DID degrade the org (a grant is stored as 'canceled' with a future period end, which is exactly
    # what the downgrade sweep selects). So grants were invisible to the school and revocations were
    # not: the asymmetry ran only in the direction that takes capacity away.
    if set_plan_to:
        orgs.sync_plan_from_owner(owner_id, set_plan_to)
    _log.info("coupon %s redeemed by %s (%s)", stored, owner_id, granted)
    return {
        "kind": kind,
        "mode": "grant",
        "plan": set_plan_to,
        "until": period_end,
        "credits_added": add_credits,
        "credits_balance": db.get_credits(owner_id),
        "discount_added_ils": 0.0,
    }


def _redeem_against_active_subscription(owner_id: str, stored: str, kind: str, *, target: str,
                                        current: str, days: int, sub: dict, now: datetime) -> dict:
    """The two outcomes a plan coupon can have on an account that already has a live, billing
    PayPlus subscription. Either way `plan`/`provider_ref`/`current_period_end` on the real
    subscription are left untouched — only the discount/boost side-fields move."""
    is_discount = plans.rank(target) <= plans.rank(current)
    granted = (f"{target} discount for {days} days" if is_discount
              else f"plan {target} boost for {days} days")
    # set_plan_to is deliberately None here: db.redeem_coupon()'s existing plan-write path would
    # write a `provider='coupon'` subscription row whenever set_plan_to is truthy, clobbering the
    # real PayPlus row. Consuming the code (throttle/expiry/exhaustion/already-redeemed checks +
    # the redemption row) and applying the discount/boost are therefore two separate calls — a
    # crash between them could leave the code consumed without its effect applied, which is a
    # known, accepted gap (same one a webhook failure after a charge would already produce).
    status = db.redeem_coupon(stored, owner_id, now.isoformat(), granted,
                              set_plan_to=None, period_end=None, add_credits_amount=0)
    if status != "ok":
        raise RedeemError({"not_found": "invalid", "inactive": "invalid"}.get(status, status))
    _clear_throttle(owner_id)

    if is_discount:
        discount_ils = round(days * plans.price_ils(target) / plans.period_days(), 2)
        db.add_coupon_discount(owner_id, discount_ils, updated_at=now.isoformat())
        balance = (db.get_subscription(owner_id) or {}).get("coupon_discount_ils", discount_ils)
        _log.info("coupon %s redeemed by %s (discount %.2f ILS, balance %.2f)",
                  stored, owner_id, discount_ils, balance)
        return {
            "kind": kind, "mode": "discount", "plan": target, "until": None,
            "credits_added": 0, "credits_balance": db.get_credits(owner_id),
            "discount_added_ils": discount_ils, "discount_balance_ils": balance,
        }

    # Boost: if already mid-boost to this exact target, extend the existing revert point and keep
    # the ORIGINAL revert_plan — not the currently-boosted one — so a chain of same-tier boost
    # codes still lands back on the plan the account actually pays for.
    existing_revert_at = sub.get("coupon_revert_at")
    if existing_revert_at and current == target:
        try:
            parsed = datetime.fromisoformat(existing_revert_at)
            revert_at = (parsed + timedelta(days=days)).isoformat()
        except ValueError:
            revert_at = (now + timedelta(days=days)).isoformat()
        revert_plan = sub["coupon_revert_plan"]
    else:
        revert_plan = current
        revert_at = (now + timedelta(days=days)).isoformat()
    db.set_plan(owner_id, target)
    orgs.sync_plan_from_owner(owner_id, target)      # same reason as the grant path above
    db.set_coupon_boost(owner_id, revert_plan=revert_plan, revert_at=revert_at,
                        updated_at=now.isoformat())
    _log.info("coupon %s redeemed by %s (boost to %s until %s, reverts to %s)",
              stored, owner_id, target, revert_at, revert_plan)
    return {
        "kind": kind, "mode": "boost", "plan": target, "until": revert_at,
        "credits_added": 0, "credits_balance": db.get_credits(owner_id),
        "discount_added_ils": 0.0,
    }
