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
from app import plans
from app.billing import greeninvoice, payplus

_log = logging.getLogger("chavruta.billing")


def enabled() -> bool:
    return payplus.enabled()


def _description(cycle: str = plans.MONTHLY) -> str:
    """Invoice line. Must say which period was actually charged — an annual receipt reading
    "monthly subscription" is a bookkeeping problem, not a cosmetic one."""
    if env := os.environ.get("CHAVRUTA_SUB_DESCRIPTION", "").strip():
        return env
    return ("חברותא AI — מנוי שנתי" if plans.canonical_cycle(cycle) == plans.ANNUAL
            else "חברותא AI — מנוי חודשי")


def start_checkout(owner_id: str, email: str, name: str, *,
                   plan: str = "pro", cycle: str = plans.MONTHLY) -> str:
    """Create a hosted payment page and return its URL for the client to redirect to.

    The chosen tier and cycle are recorded as 'pending' BEFORE the redirect: the webhook only tells
    us a charge succeeded and for whom, not what was bought, so without this an annual purchase
    would come back and be granted a month.
    """
    if not payplus.enabled():
        raise RuntimeError("billing not configured")
    tier = plans.canonical(plan)
    cyc = plans.canonical_cycle(cycle)
    if tier == "free":
        raise ValueError("cannot check out the free tier")
    db.upsert_subscription(owner_id, provider="payplus", status="pending", plan=tier, cycle=cyc,
                           updated_at=datetime.now(UTC).isoformat())
    return payplus.create_payment_page(owner_id, email, name,
                                       amount=plans.price_ils(tier, cyc), cycle=cyc)["link"]


def handle_event(normalized: dict, *, now: datetime | None = None) -> None:
    """Apply a verified PayPlus callback: activate/renew the paid plan and issue an invoice. Ignores
    events with no owner id or a non-success status (logged, not raised)."""
    owner = normalized.get("owner_id")
    if not owner or not normalized.get("success"):
        _log.info("billing event ignored (owner=%s success=%s)", owner, normalized.get("success"))
        return
    now = now or datetime.now(UTC)
    # What was bought was decided at checkout, not here — the callback carries a charge, not a
    # basket. A renewal reads the same stored row — and on either cycle that grants another MONTH,
    # since an annual plan is twelve monthly instalments rather than one yearly charge.
    sub = db.get_subscription(owner) or {}
    tier = plans.canonical(sub.get("plan") or "pro")
    cycle = plans.canonical_cycle(sub.get("cycle"))
    period_end = (now + timedelta(days=plans.period_days(cycle))).isoformat()
    db.upsert_subscription(owner, provider="payplus", provider_ref=normalized.get("recurring_uid"),
                           status="active", plan=tier, cycle=cycle, current_period_end=period_end,
                           cancel_at_period_end=False, updated_at=now.isoformat())
    db.set_plan(owner, tier)
    _log.info("subscription active for %s: %s/%s (renewal=%s) until %s",
              owner, tier, cycle, normalized.get("is_renewal"), period_end)
    amount = float(normalized.get("amount") or 0.0)

    # Record the charge in the accounting ledger BEFORE issuing the invoice. The money has already
    # moved by the time this callback arrives, so the record of it must not depend on a third-party
    # call succeeding — and unlike the subscription row, the ledger survives the account being
    # deleted, because the bookkeeping obligation outlives the customer relationship.
    invoice_ref = ""
    try:
        # Invoice is best-effort: the charge went through; a failed invoice must not 500 the hook.
        doc = greeninvoice.issue_receipt(
            email=normalized.get("email", "") or "", name=normalized.get("name", "") or "",
            amount=amount, description=_description(cycle), now=now.timestamp())
        # The human-facing document NUMBER is what an accountant reconciles against, so prefer it
        # over the internal id. Empty when invoicing is unconfigured or failed — the charge is still
        # recorded, since a missing invoice is a gap to chase, not a reason to lose the row.
        if doc:
            invoice_ref = str(doc.get("number") or doc.get("id") or "")
    except Exception:               # noqa: BLE001 — never let invoicing break a paid subscription
        _log.exception("issuing the receipt failed (amount=%s cycle=%s)", amount, cycle)
    try:
        db.record_charge(charged_at=now.isoformat(), amount=amount, plan=tier, cycle=cycle,
                         provider="payplus", provider_ref=normalized.get("recurring_uid"),
                         invoice_ref=invoice_ref,
                         note="renewal" if normalized.get("is_renewal") else "new")
    except Exception:               # noqa: BLE001 — same reasoning; log loudly, don't fail the hook
        _log.exception("could not write the charge to the ledger (amount=%s)", amount)


def cancel(owner_id: str, *, now: datetime | None = None) -> None:
    """Stop future charges and mark the subscription cancelled. Paid access is retained until the
    current period ends (Consumer Protection: billing stops, but the user keeps what they paid for).

    Identical on both cycles, because there is no prepaid year to unwind: since 2026-07-27 the annual
    plan is a discounted rate billed in twelve monthly instalments, so cancelling stops the next
    instalment and leaves the month already paid for intact. Nothing is held that would have to be
    refunded — which is the whole reason the plan was restructured (see app/plans.py
    ANNUAL_INSTALMENTS).

    NOT a refund. The statutory 14-day cancellation right on a distance sale is handled manually via
    the contact address in the terms; there is no refund call in payplus.py. See finding A in
    docs/legal/REVIEW-2026-07-27.md."""
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
