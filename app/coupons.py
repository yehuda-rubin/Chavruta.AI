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


def redeem(owner_id: str, code: str, *, now: datetime | None = None) -> dict:
    """Apply a coupon to an account. Returns a summary of what was granted.

    Raises RedeemError with one of: throttled · invalid · already_redeemed · exhausted · expired ·
    has_paid_subscription · downgrade.
    """
    if owner_id == "local":
        raise RedeemError("sign_in_required")
    stored = normalize(code)
    if not _VALID.match(stored):
        raise RedeemError("invalid")
    if _throttled(owner_id):
        raise RedeemError("throttled")

    now = now or datetime.now(UTC)
    c = db.get_coupon(stored)
    if c is None:
        raise RedeemError("invalid")

    kind = c["kind"]
    set_plan_to = period_end = None
    add_credits = 0

    if kind == "credits":
        add_credits = int(c["credits"] or 0)
        granted = f"{add_credits} credits"
    elif kind == "plan":
        target = plans.canonical(c["plan"])
        current = plans.canonical(db.get_plan(owner_id))
        sub = db.get_subscription(owner_id) or {}
        # Never let a coupon interfere with money already changing hands: a live PayPlus subscription
        # keeps its own period and provider_ref, and overwriting them here would silently detach the
        # account from the recurring charge it is still paying.
        if sub.get("provider") == "payplus" and sub.get("status") == "active":
            raise RedeemError("has_paid_subscription")
        # A coupon may only add access. Redeeming a 'basic' code while on 'pro' would otherwise be a
        # self-inflicted downgrade — refuse instead of quietly taking access away.
        if plans.rank(target) < plans.rank(current):
            raise RedeemError("downgrade")
        days = int(c["days"] or 0)
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
    _log.info("coupon %s redeemed by %s (%s)", stored, owner_id, granted)
    return {
        "kind": kind,
        "plan": set_plan_to,
        "until": period_end,
        "credits_added": add_credits,
        "credits_balance": db.get_credits(owner_id),
    }
