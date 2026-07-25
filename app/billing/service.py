"""Billing domain logic — the provider-agnostic glue between PayPlus/Green Invoice and our DB.

One place decides what a payment event means for an account: a successful charge activates the paid
plan and issues an invoice; a cancellation stops future charges but keeps paid access until the period
already paid for lapses; a background sweep then downgrades expired-cancelled subscriptions to free.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, datetime, timedelta

import app.db as db
from app.billing import greeninvoice, payplus

_log = logging.getLogger("chavruta.billing")


def enabled() -> bool:
    return payplus.enabled()


def _description() -> str:
    return os.environ.get("CHAVRUTA_SUB_DESCRIPTION", "חברותא AI — מנוי חודשי")


def _period_days() -> int:
    try:
        return max(1, int(os.environ.get("CHAVRUTA_SUB_PERIOD_DAYS", "30")))
    except ValueError:
        return 30


def start_checkout(owner_id: str, email: str, name: str) -> str:
    """Create a hosted payment page and return its URL for the client to redirect to."""
    if not payplus.enabled():
        raise RuntimeError("billing not configured")
    return payplus.create_payment_page(owner_id, email, name)["link"]


def handle_event(normalized: dict, *, now: datetime | None = None) -> None:
    """Apply a verified PayPlus callback: activate/renew the paid plan and issue an invoice. Ignores
    events with no owner id or a non-success status (logged, not raised)."""
    owner = normalized.get("owner_id")
    if not owner or not normalized.get("success"):
        _log.info("billing event ignored (owner=%s success=%s)", owner, normalized.get("success"))
        return
    now = now or datetime.now(UTC)
    period_end = (now + timedelta(days=_period_days())).isoformat()
    db.upsert_subscription(owner, provider="payplus", provider_ref=normalized.get("recurring_uid"),
                           status="active", current_period_end=period_end,
                           cancel_at_period_end=False, updated_at=now.isoformat())
    db.set_plan(owner, "paid")
    _log.info("subscription active for %s (renewal=%s) until %s",
              owner, normalized.get("is_renewal"), period_end)
    # Invoice is best-effort — the charge already went through; a failed invoice must not 500 the hook.
    amount = normalized.get("amount")
    greeninvoice.issue_receipt(
        email=normalized.get("email", "") or "", name=normalized.get("name", "") or "",
        amount=float(amount) if amount else 0.0, description=_description(), now=now.timestamp())


def cancel(owner_id: str, *, now: datetime | None = None) -> None:
    """Stop future charges and mark the subscription cancelled. Paid access is retained until the
    current period ends (Consumer Protection: billing stops, but the user keeps what they paid for)."""
    now = now or datetime.now(UTC)
    sub = db.get_subscription(owner_id)
    # Only a real provider subscription has anything to cancel upstream. A coupon-granted plan stores
    # the coupon code in provider_ref; sending that to PayPlus would be a guaranteed API error.
    if sub and sub.get("provider_ref") and sub.get("provider") == "payplus":
        try:
            payplus.cancel_recurring(sub["provider_ref"])
        except Exception:               # noqa: BLE001 — still mark cancelled locally so we stop renewing
            _log.exception("payplus cancel_recurring failed for %s", owner_id)
    db.upsert_subscription(owner_id, status="canceled", cancel_at_period_end=True,
                           updated_at=now.isoformat())
    _log.info("subscription cancelled for %s (paid access until period end)", owner_id)


def sweep_downgrades(now: datetime | None = None) -> int:
    """Downgrade cancelled subscriptions whose paid period has lapsed to the free plan. Returns count."""
    now = now or datetime.now(UTC)
    due = db.due_downgrades(now.isoformat())
    for owner in due:
        db.set_plan(owner, "free")
        db.upsert_subscription(owner, status="expired", updated_at=now.isoformat())
        _log.info("subscription expired → free plan for %s", owner)
    return len(due)


# ── Background sweeper ────────────────────────────────────────────────────────
_started = False
_lock = threading.Lock()


def start_sweeper() -> None:
    """Daemon that periodically downgrades expired-cancelled subscriptions. Idempotent.

    Runs whether or not a payment provider is configured: a coupon grants a time-boxed plan through
    the same subscriptions row, so gating this on PayPlus would leave coupon plans never expiring on
    a deployment that only issues coupons.
    """
    global _started
    with _lock:
        if _started:
            return
        _started = True

    try:
        interval = max(60.0, float(os.environ.get("CHAVRUTA_BILLING_SWEEP_INTERVAL_S", "3600")))
    except ValueError:
        interval = 3600.0

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                sweep_downgrades()
            except Exception:           # noqa: BLE001 — keep the sweeper alive
                _log.exception("billing downgrade sweep failed")

    threading.Thread(target=_loop, name="billing-sweeper", daemon=True).start()
    _log.info("billing downgrade sweeper started (every %.0fs)", interval)
