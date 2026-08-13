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
import app.orgs as orgs
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
    # Refused BEFORE the payment page exists, not after the charge: a school member draws on the
    # org's pool, so a personal subscription would take real money and grant nothing at all. The
    # check is here rather than in the route so it holds for every caller of this function. The
    # school's own OWNER buying an institutional tier is not this case — see orgs.refuse_personal_purchase.
    # The reason matters: an owner told to "leave the institution" is being sent to a route that
    # refuses them (an owner closes their school rather than leaving it), which is a dead end.
    if (why := orgs.refuse_personal_purchase(owner_id, tier)) == "owner":
        raise ValueError("החשבון הזה מנהל מוסד ומשתמש במכסה המשותפת שלו, ולכן מנוי אישי לא יוסיף לו "
                         "כלום. אפשר לשדרג את מסלול המוסד, או לסגור אותו מפאנל המוסד.")
    if why:
        raise ValueError("החשבון משויך למוסד ומשתמש במכסה המשותפת שלו — מנוי אישי לא יוסיף לו כלום. "
                         "כדי לרכוש מנוי משלך, צא מהמוסד בהגדרות תחילה.")
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
    # A school's tier lives on the org row, and nothing used to write it after creation — so a school
    # that upgraded could not be given what it had just paid for, and one that stopped paying kept its
    # full pool forever while the panel cheerfully rendered it. Both directions run through here.
    if org_id := orgs.sync_plan_from_owner(owner, tier):
        _log.info("org %s now on %s (paid by %s)", org_id, tier, owner)
    # The reverse of the guard in start_checkout. That one refuses at the payment page; this one is
    # for the orders that were already in flight — a checkout started before joining a school, or a
    # RECURRING charge that fires months after the holder joined one. The money has already moved by
    # the time this callback arrives, so there is nothing to refuse: what matters is that it is
    # LOGGED loudly rather than silently granting a plan the request path will never consult.
    if orgs.membership(owner) and not plans.is_institutional(tier):
        _log.error("BILLING/ORG CONFLICT: %s paid for %s but belongs to a school and spends its pool "
                   "— this charge grants nothing; refund or remove the membership", owner, tier)
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
                         note="renewal" if normalized.get("is_renewal") else "new",
                         # The payment's own uid, which is what a refund is issued against. A charge
                         # recorded without it can still be refunded, but only after looking the
                         # transaction up by hand in the PayPlus dashboard.
                         txn_uid=normalized.get("transaction_uid"))
    except Exception:               # noqa: BLE001 — same reasoning; log loudly, don't fail the hook
        _log.exception("could not write the charge to the ledger (amount=%s)", amount)

    try:
        _apply_coupon_discount(owner, amount, normalized.get("transaction_uid"), tier, cycle, now)
    except Exception:               # noqa: BLE001 — a failed rebate must not fail the whole webhook
        _log.exception("coupon discount rebate failed for %s", owner)


def _apply_coupon_discount(owner: str, amount: float, txn_uid: str | None, tier: str, cycle: str,
                           now: datetime) -> None:
    """Rebate a coupon-granted ILS discount off a real charge that just succeeded, via a partial
    refund — PayPlus has no API to change an already-running recurring amount, so the charge goes
    through in full and the discount comes back as money returned, same mechanism scripts/refund.py
    already uses for operator-initiated refunds, minus the subscription cancellation."""
    if not txn_uid:
        return
    balance = float((db.get_subscription(owner) or {}).get("coupon_discount_ils") or 0.0)
    if balance <= 0:
        return
    rebate = round(min(balance, amount), 2)
    if rebate <= 0:
        return
    payplus.refund(txn_uid, rebate, description="קופון — הנחה על החיוב")   # raises ⇒ nothing below runs
    try:
        db.record_charge(charged_at=now.isoformat(), amount=-rebate, plan=tier, cycle=cycle,
                         provider="payplus", provider_ref=txn_uid,
                         note="coupon discount rebate", txn_uid=txn_uid)
    except Exception:               # noqa: BLE001 — the money already moved; never lose that fact
        _log.exception("REBATE OF ₪%.2f ON %s IS NOT IN THE LEDGER — record it by hand", rebate, txn_uid)
    db.set_coupon_discount(owner, round(balance - rebate, 2))
    _log.info("coupon discount rebate for %s: ₪%.2f (balance now ₪%.2f)",
              owner, rebate, round(balance - rebate, 2))


class ProviderCancelFailed(Exception):
    """The recurring charge could not be stopped at the provider. Only raised when the caller asked
    for `strict` — i.e. when it is about to destroy the handle that would let anyone try again."""


def cancel(owner_id: str, *, strict: bool = False, now: datetime | None = None) -> None:
    """Stop future charges and mark the subscription cancelled. Paid access is retained until the
    current period ends (Consumer Protection: billing stops, but the user keeps what they paid for).

    Identical on both cycles, because there is no prepaid year to unwind: since 2026-07-27 the annual
    plan is a discounted rate billed in twelve monthly instalments, so cancelling stops the next
    instalment and leaves the month already paid for intact. Nothing is held that would have to be
    refunded — which is the whole reason the plan was restructured (see app/plans.py
    ANNUAL_INSTALMENTS).

    NOT a refund — cancelling stops the next charge and gives nothing back. Money is returned by
    refund() below, which an operator runs deliberately through scripts/refund.py.

    `strict` re-raises a provider failure instead of logging it. The default is right for a user who
    clicked "cancel subscription" — we stop renewing locally and sort the provider out afterwards. It
    is wrong for account deletion, which is about to delete the subscriptions row and with it
    `provider_ref`, the only handle anyone has on the recurring charge: a swallowed error there ends
    with a person billed monthly for an account that no longer exists and no local record of what to
    cancel. See app/accounts.py::stop_billing.
    """
    now = now or datetime.now(UTC)
    sub = db.get_subscription(owner_id)
    # Only a real provider subscription has anything to cancel upstream. A coupon-granted plan stores
    # the coupon code in provider_ref; sending that to PayPlus would be a guaranteed API error.
    if sub and sub.get("provider_ref") and sub.get("provider") == "payplus":
        try:
            payplus.cancel_recurring(sub["provider_ref"])
        except Exception as exc:        # noqa: BLE001 — still mark cancelled locally so we stop renewing
            _log.exception("payplus cancel_recurring failed for %s", owner_id)
            if strict:
                raise ProviderCancelFailed(owner_id) from exc
    db.upsert_subscription(owner_id, status="canceled", cancel_at_period_end=True,
                           updated_at=now.isoformat())
    _log.info("subscription cancelled for %s (paid access until period end)", owner_id)


def refund(charge_id: int, *, amount: float | None = None, email: str = "", name: str = "",
           reason: str = "", owner_id: str | None = None, cancel_subscription: bool = True,
           now: datetime | None = None) -> dict:
    """Give money back for one recorded charge, and leave the books able to prove it.

    Terms §10 promises a refund on cancellation within 14 days of a distance sale. Until now there
    was no code path that could produce one — the promise rested entirely on someone remembering to
    log into PayPlus. This is that path. It is still OPERATOR-INITIATED, not a route a user can call:
    a refund moves real money irreversibly and there is no undo, so it is run from
    scripts/refund.py, which prints the charge and the lawful quote and asks before proceeding.

    Order matters and is not arbitrary:

      1. refuse if this payment was already refunded (in full, or beyond the remainder),
      2. move the money at the provider — the only step that can fail in a way that must abort,
      3. append a NEGATIVE ledger row, whatever happens next,
      4. issue a credit note, best-effort,
      5. cancel the subscription so the next instalment does not immediately re-charge them.

    Step 3 comes before 4 and 5 because at that point the money is gone from our account: a ledger
    that omits it is wrong in the direction that overstates our income. Step 5 is the one people
    forget by hand — refunding the last charge while leaving the subscription live gives the customer
    their money back and then takes it again in a month.

    `amount` defaults to the whole charge. Pass a smaller figure to keep the lawful cancellation fee
    (plans.refund_quote gives it) or to refund part of a period.
    """
    now = now or datetime.now(UTC)
    row = db.get_charge(charge_id)
    if not row:
        raise ValueError(f"no such charge: {charge_id}")
    if float(row["amount"]) <= 0:
        raise ValueError(f"charge {charge_id} is itself a refund (amount {row['amount']})")
    txn_uid = row.get("txn_uid") or ""
    if not txn_uid:
        # Not a failure of ours to record it — pre-2026-07-27 rows predate the column. The operator
        # can still refund it, by finding the transaction in the PayPlus dashboard and passing it.
        raise ValueError(
            f"charge {charge_id} has no transaction uid; look it up in the PayPlus dashboard and "
            f"pass it explicitly (charged_at={row['charged_at']} amount={row['amount']})")

    charged = round(float(row["amount"]), 2)
    already = db.refunded_total(txn_uid)
    remaining = round(charged - already, 2)
    if remaining <= 0:
        raise ValueError(f"charge {charge_id} was already refunded in full (₪{already:.2f})")
    give = remaining if amount is None else round(float(amount), 2)
    if give <= 0 or give > remaining:
        raise ValueError(f"refund of ₪{give:.2f} is outside the ₪{remaining:.2f} still refundable")

    description = reason.strip() or f"החזר — {_description(row.get('cycle') or plans.MONTHLY)}"
    resp = payplus.refund(txn_uid, give, description=description)   # raises ⇒ nothing below runs

    invoice_ref = ""
    ledger_id = 0
    try:
        ledger_id = db.record_charge(
            charged_at=now.isoformat(), amount=-give, plan=row.get("plan"), cycle=row.get("cycle"),
            provider=row.get("provider") or "payplus", provider_ref=row.get("provider_ref"),
            note=f"refund of #{charge_id}" + (f" — {reason.strip()}" if reason.strip() else ""),
            txn_uid=txn_uid)
    except Exception:               # noqa: BLE001 — the money is already back; never lose that fact
        _log.exception("REFUND OF ₪%.2f ON %s IS NOT IN THE LEDGER — record it by hand", give, txn_uid)

    try:
        doc = greeninvoice.issue_credit_note(email=email, name=name, amount=give,
                                             description=description, now=now.timestamp())
        if doc:
            invoice_ref = str(doc.get("number") or doc.get("id") or "")
    except Exception:               # noqa: BLE001 — issue_credit_note already swallows; belt and braces
        _log.exception("credit note failed for refund of ₪%.2f", give)

    if cancel_subscription and owner_id:
        try:
            cancel(owner_id, now=now)
        except Exception:           # noqa: BLE001 — refund stands even if the cancel call fails
            _log.exception("refunded %s but could not cancel their subscription", owner_id)

    _log.info("refunded ₪%.2f of charge #%s (txn %s, ledger #%s, credit note %s)",
              give, charge_id, txn_uid, ledger_id, invoice_ref or "—")
    return {"charge_id": charge_id, "txn_uid": txn_uid, "refunded": give,
            "remaining": round(remaining - give, 2), "ledger_id": ledger_id,
            "invoice_ref": invoice_ref, "provider_response": resp}


def sweep_downgrades(now: datetime | None = None) -> int:
    """Downgrade cancelled subscriptions whose paid period has lapsed to the free plan. Returns count."""
    now = now or datetime.now(UTC)
    due = db.due_downgrades(now.isoformat())
    for owner in due:
        db.set_plan(owner, "free")
        db.upsert_subscription(owner, status="expired", updated_at=now.isoformat())
        # A school whose payer lapses degrades its pool — it does NOT dissolve. Members keep their
        # accounts, their history and their seats, and the tier comes straight back when payment
        # resumes: nobody is locked out of their own study by a billing failure. Before this, an
        # unpaid school simply kept its full institution pool, indefinitely and invisibly.
        if org_id := orgs.sync_plan_from_owner(owner, "free", degrade=True):
            _log.warning("org %s degraded to free — its subscription (%s) lapsed", org_id, owner)
        _log.info("subscription expired → free plan for %s", owner)
    return len(due)


def sweep_coupon_reverts(now: datetime | None = None) -> int:
    """Revert accounts whose coupon-driven temporary plan boost has ended, back to the plan their
    real PayPlus subscription actually pays for. Returns count."""
    now = now or datetime.now(UTC)
    due = db.due_coupon_reverts(now.isoformat())
    for row in due:
        db.set_plan(row["owner_id"], row["revert_plan"])
        # degrade=True: a boost ENDING is a real lapse back to what is actually paid for, unlike
        # an unrelated personal renewal.
        orgs.sync_plan_from_owner(row["owner_id"], row["revert_plan"], degrade=True)
        db.clear_coupon_revert(row["owner_id"], updated_at=now.isoformat())
        _log.info("coupon boost ended for %s → reverted to %s", row["owner_id"], row["revert_plan"])
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
            try:
                sweep_coupon_reverts()
            except Exception:           # noqa: BLE001 — one sweep failing must not stop the other
                _log.exception("billing coupon revert sweep failed")

    threading.Thread(target=_loop, name="billing-sweeper", daemon=True).start()
    _log.info("billing downgrade sweeper started (every %.0fs)", interval)
