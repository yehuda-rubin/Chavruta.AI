"""Billing: PayPlus webhook verification + the subscription state machine.

The load-bearing security check is verify_webhook — a forged callback must never activate a paid plan.
The state machine: a verified success activates 'paid' and records the subscription; cancel stops
future charges but keeps paid access until the period ends; the sweep downgrades once it lapses.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import app.db as db
import pytest
from app import plans
from app.billing import payplus, service


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bill.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def _sign(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


# ── webhook verification ──────────────────────────────────────────────────────
def test_verify_webhook_accepts_valid(monkeypatch):
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s3cret")
    body = json.dumps({"transaction": {"status_code": "000"}}).encode()
    assert payplus.verify_webhook(body, "PayPlus", _sign(body, "s3cret")) is True


def test_verify_webhook_rejects_forged_hash(monkeypatch):
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s3cret")
    body = b'{"transaction":{"status_code":"000"}}'
    assert payplus.verify_webhook(body, "PayPlus", _sign(body, "WRONG")) is False


def test_verify_webhook_rejects_bad_user_agent(monkeypatch):
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s3cret")
    body = b'{}'
    assert payplus.verify_webhook(body, "curl/8", _sign(body, "s3cret")) is False


def test_verify_webhook_rejects_missing_hash(monkeypatch):
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s3cret")
    assert payplus.verify_webhook(b'{}', "PayPlus", None) is False


def test_verify_webhook_tamper_changes_hash(monkeypatch):
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s3cret")
    body = b'{"transaction":{"status_code":"000","amount":49.9}}'
    good = _sign(body, "s3cret")
    tampered = b'{"transaction":{"status_code":"000","amount":9999}}'
    assert payplus.verify_webhook(tampered, "PayPlus", good) is False   # body changed → hash mismatch


# ── parse + state machine ─────────────────────────────────────────────────────
def test_parse_event_extracts_fields():
    ev = payplus.parse_event({"transaction": {
        "uid": "txn_1", "more_info": "u-1", "status_code": "000", "amount": 49.9,
        "recurring_charge_information": {"recurring_uid": "rec_9"}}})
    assert ev == {"owner_id": "u-1", "success": True, "transaction_uid": "txn_1",
                  "recurring_uid": "rec_9", "is_renewal": True, "amount": 49.9}


def test_handle_event_activates_paid(fresh_db, monkeypatch):
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)   # no network
    service.handle_event({"owner_id": "u-1", "success": True, "recurring_uid": "rec_9",
                          "is_renewal": False, "amount": 49.9}, now=datetime(2026, 7, 19, tzinfo=UTC))
    # No checkout row, so the tier defaults to the legacy 'pro' — but ₪49.90 is the pre-2026-08-12 pro
    # price, and even basic (repriced 2026-08-21 to ₪75) now costs more than that stale charge, so the
    # MONEY decides and it buys nothing but free. This assertion has already moved once (it used to
    # read `== "pro"`, the old ladder frozen into a test, then `== "basic"` after the first reprice);
    # granting a tier the charge does not cover is the whole defect the resolver exists to stop.
    assert fresh_db.get_plan("u-1") == "free"
    sub = fresh_db.get_subscription("u-1")
    assert sub["status"] == "active" and sub["provider_ref"] == "rec_9"
    assert sub["current_period_end"] > "2026-08"     # ~30 days out


def test_handle_event_ignores_failure(fresh_db, monkeypatch):
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)
    service.handle_event({"owner_id": "u-2", "success": False}, now=datetime(2026, 7, 19, tzinfo=UTC))
    assert fresh_db.get_plan("u-2") == "free"
    assert fresh_db.get_subscription("u-2") is None


def test_cancel_keeps_paid_until_period_end_then_sweep_downgrades(fresh_db, monkeypatch):
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)
    stopped = {}
    monkeypatch.setattr(service.payplus, "cancel_recurring",
                        lambda ref, *a, **k: stopped.update(ref=ref))   # no network
    # Activate, then cancel.
    service.handle_event({"owner_id": "u-3", "success": True, "recurring_uid": "rec_3"},
                         now=datetime(2026, 7, 19, tzinfo=UTC))
    service.cancel("u-3", now=datetime(2026, 7, 20, tzinfo=UTC))
    sub = fresh_db.get_subscription("u-3")
    assert sub["status"] == "canceled" and sub["cancel_at_period_end"] == 1
    # The terms promise the NEXT CHARGE STOPS IMMEDIATELY, so the provider must actually be told.
    # Marking the row cancelled locally while the recurring charge keeps running would go on taking
    # money from someone who cancelled — and the local state would look correct throughout.
    assert stopped["ref"] == "rec_3"
    assert fresh_db.get_plan("u-3") == "pro"         # still paid — keeps what they paid for
    # Before period end → no downgrade; after → downgraded to free.
    assert service.sweep_downgrades(now=datetime(2026, 8, 1, tzinfo=UTC)) == 0
    assert fresh_db.get_plan("u-3") == "pro"
    assert service.sweep_downgrades(now=datetime(2026, 9, 1, tzinfo=UTC)) == 1
    assert fresh_db.get_plan("u-3") == "free"


# ── Annual (a discounted rate, billed monthly) ────────────────────────────────
# The annual plan was a prepaid year until 2026-07-27. It is now twelve monthly instalments at the
# discounted rate: same total, same discount, no money held up front. The change exists so that the
# statutory cancellation rights (14 days on a distance sale, and at any time on a continuing
# transaction) have nothing to collide with — there is never a prepayment to refund.
def test_checkout_records_tier_and_cycle_before_redirecting(fresh_db, monkeypatch):
    """The callback reports a charge, not a basket — so what was bought is stored at checkout.
    Without this an annual purchase comes back and is granted a single month."""
    monkeypatch.setenv("PAYPLUS_API_KEY", "k")
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s")
    monkeypatch.setenv("PAYPLUS_PAYMENT_PAGE_UID", "uid")
    seen = {}

    def fake_page(owner, email, name, *, amount=None, cycle="monthly"):
        seen.update(owner=owner, amount=amount, cycle=cycle)
        return {"link": "https://pay.example/x"}

    monkeypatch.setattr(service.payplus, "create_payment_page", fake_page)
    service.start_checkout("u-a", "a@b.c", "A", plan="pro", cycle="annual")

    # Derived, not hardcoded. These were literals (41.58 and 499.0) tied to the pro price of the
    # day, so the 2026-08-12 repricing broke a test that is really about an INVARIANT: the customer
    # is charged one floored twelfth, and twelve of those never exceed the advertised year.
    import app.plans as plans

    assert seen["cycle"] == "annual"
    assert seen["amount"] == plans.price_ils("pro", plans.ANNUAL)   # an instalment, not the year
    assert seen["amount"] * 12 <= plans._annual_headline_ils("pro")  # never more than the headline
    sub = fresh_db.get_subscription("u-a")
    assert sub["plan"] == "pro" and sub["cycle"] == "annual" and sub["status"] == "pending"


def test_annual_charge_grants_a_month_not_a_year(fresh_db, monkeypatch):
    monkeypatch.setenv("PAYPLUS_API_KEY", "k")
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s")
    monkeypatch.setenv("PAYPLUS_PAYMENT_PAGE_UID", "uid")
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)
    monkeypatch.setattr(service.payplus, "create_payment_page",
                        lambda *a, **k: {"link": "x"})

    service.start_checkout("u-b", "b@c.d", "B", plan="pro", cycle="annual")
    service.handle_event({"owner_id": "u-b", "success": True, "recurring_uid": "rec_y"},
                         now=datetime(2026, 7, 19, tzinfo=UTC))

    sub = fresh_db.get_subscription("u-b")
    assert fresh_db.get_plan("u-b") == "pro"
    assert sub["cycle"] == "annual"
    # A month out, not a year: each instalment buys a month, so an unpaid renewal lapses in
    # weeks rather than leaving eleven months of granted access nobody paid for.
    assert sub["current_period_end"][:7] == "2026-08"


def test_cancelling_an_annual_plan_stops_the_instalments(fresh_db, monkeypatch):
    """What replaced the prepaid year: cancelling stops future charges, and the month already paid
    for is kept. Nothing is held that would have to be refunded."""
    monkeypatch.setenv("PAYPLUS_API_KEY", "k")
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s")
    monkeypatch.setenv("PAYPLUS_PAYMENT_PAGE_UID", "uid")
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)
    monkeypatch.setattr(service.payplus, "create_payment_page", lambda *a, **k: {"link": "x"})
    cancelled = {}
    monkeypatch.setattr(service.payplus, "cancel_recurring",
                        lambda ref, *a, **k: cancelled.update(ref=ref))

    service.start_checkout("u-c", "c@d.e", "C", plan="pro", cycle="annual")
    service.handle_event({"owner_id": "u-c", "success": True, "recurring_uid": "rec_c"},
                         now=datetime(2026, 7, 19, tzinfo=UTC))
    service.cancel("u-c", now=datetime(2026, 8, 1, tzinfo=UTC))

    assert cancelled["ref"] == "rec_c"                       # the recurring charge really stops
    assert fresh_db.get_subscription("u-c")["cancel_at_period_end"] == 1
    # The month that was paid for is kept…
    assert service.sweep_downgrades(now=datetime(2026, 8, 10, tzinfo=UTC)) == 0
    assert fresh_db.get_plan("u-c") == "pro"
    # …and then it lapses. No eleven months of unpaid access, and no eleven months of held money.
    assert service.sweep_downgrades(now=datetime(2026, 9, 1, tzinfo=UTC)) == 1
    assert fresh_db.get_plan("u-c") == "free"


def test_the_annual_rate_is_a_real_discount_on_the_monthly_one():
    from app import plans

    for tid in ("basic", "pro", "institution"):
        # Both figures are per-month now, so they compare directly.
        assert plans.price_ils(tid, "annual") < plans.price_ils(tid, "monthly")
        assert plans.annual_saving_pct(tid) >= 15


def test_twelve_instalments_never_exceed_the_advertised_year():
    """Dividing naively overcharges: 290/12 rounds to 24.17 and twelve of those is 290.04. The
    instalment is floored so a year costs at most its headline, never a single agora more."""
    from app import plans

    for tier in plans.TIERS:
        if tier.price_ils == 0:
            continue
        charged = round(plans.price_ils(tier.id, "annual") * plans.ANNUAL_INSTALMENTS, 2)
        assert charged <= tier.annual_price_ils, f"{tier.id} overcharges the year"
        assert tier.annual_price_ils - charged < 0.15, f"{tier.id} drifts too far below the headline"
        assert plans.annual_total_ils(tier.id) == charged      # what we display is what we charge


def test_an_annual_period_is_a_month():
    """The cycle names a price, not a horizon: one charge buys one month on either plan."""
    from app import plans

    assert plans.period_days("annual") == plans.period_days("monthly") == 30


def test_unknown_cycle_bills_monthly():
    """Resolving an ambiguous request for money must land on the cheaper, lower-commitment option."""
    from app import plans

    assert plans.canonical_cycle("gibberish") == "monthly"
    assert plans.period_days("gibberish") == 30


def test_free_tier_cannot_be_checked_out(fresh_db, monkeypatch):
    monkeypatch.setenv("PAYPLUS_API_KEY", "k")
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s")
    monkeypatch.setenv("PAYPLUS_PAYMENT_PAGE_UID", "uid")
    with pytest.raises(ValueError):
        service.start_checkout("u-d", "d@e.f", "D", plan="free")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── Paying for one tier must not grant another ───────────────────────────────
# `start_checkout` writes the SELECTED tier into the subscriptions row before any money moves, and
# `handle_event` used to read that row as the answer to "what was bought". The row is therefore a
# statement of intent that the customer can rewrite for free, as often as they like, by opening a
# checkout and walking away. Found in a security review of 2026-08-14.
def _charge(owner, amount, *, renewal=False):
    service.handle_event({"owner_id": owner, "success": True, "amount": amount,
                          "recurring_uid": "rec-" + owner, "is_renewal": renewal},
                         now=datetime(2026, 8, 14, tzinfo=UTC))


@pytest.fixture(autouse=True)
def _no_invoice_network(monkeypatch):
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)


def test_a_stale_cheap_payment_link_cannot_buy_the_expensive_tier(fresh_db):
    """Open a checkout for basic, open one for institution_100 (which overwrites the row), then pay
    the FIRST link. ₪49 arrives; the row says institution_100."""
    db.upsert_subscription("u-x", provider="payplus", status="pending", plan="basic",
                           cycle="monthly", updated_at="2026-08-14")
    db.upsert_subscription("u-x", provider="payplus", status="pending", plan="institution_100",
                           cycle="monthly", updated_at="2026-08-14")

    _charge("u-x", plans.price_ils("basic", "monthly"))

    assert fresh_db.get_plan("u-x") == "basic", "₪49 bought a ₪2,799 tier"


def test_an_abandoned_upgrade_does_not_ride_in_on_the_next_renewal(fresh_db):
    """The variant that needs no second payment link at all, and repeats every month: a ₪49
    subscriber opens a checkout for the top tier and abandons it. Their ordinary renewal — same
    mandate, same ₪49 — used to read the row and grant institution_100."""
    db.upsert_subscription("u-y", provider="payplus", status="active", plan="basic",
                           cycle="monthly", provider_ref="rec-u-y", updated_at="2026-08-14")
    db.set_plan("u-y", "basic")
    db.upsert_subscription("u-y", provider="payplus", status="pending", plan="institution_100",
                           cycle="monthly", updated_at="2026-08-14")

    _charge("u-y", plans.price_ils("basic", "monthly"), renewal=True)

    assert fresh_db.get_plan("u-y") == "basic"


@pytest.mark.parametrize("tier_id", [t.id for t in plans.TIERS if t.id != "free"])
@pytest.mark.parametrize("cycle", ["monthly", "annual"])
def test_an_honest_purchase_of_every_tier_still_works(fresh_db, tier_id, cycle):
    """The check must not cost anyone the thing they actually paid for — on either cycle, where the
    annual charge is one of twelve instalments and not the year's headline figure."""
    owner = f"buy-{tier_id}-{cycle}"
    db.upsert_subscription(owner, provider="payplus", status="pending", plan=tier_id, cycle=cycle,
                           updated_at="2026-08-14")

    _charge(owner, plans.price_ils(tier_id, cycle))

    assert fresh_db.get_plan(owner) == tier_id


def test_a_renewal_below_todays_list_price_does_not_downgrade_a_customer(fresh_db):
    """Prices were raised on 2026-08-12 and will be again. A customer renewing on the rate they
    signed up at must keep their tier: their renewal is measured against what they hold, never
    against today's price list."""
    db.upsert_subscription("u-old", provider="payplus", status="active", plan="pro",
                           cycle="monthly", provider_ref="rec-u-old", updated_at="2026-08-14")
    db.set_plan("u-old", "pro")

    _charge("u-old", 49.90, renewal=True)      # the price pro used to cost

    assert fresh_db.get_plan("u-old") == "pro"


def test_a_callback_with_no_amount_grants_the_selected_tier_rather_than_downgrading(fresh_db):
    """The failure mode of a price check is worse than the hole it closes. If the callback carries
    no figure — an unparsed payload, a provider change — we cannot conclude the customer underpaid,
    and turning that into "downgrade to free" would take out the whole paying base in one deploy."""
    db.upsert_subscription("u-z", provider="payplus", status="pending", plan="pro",
                           cycle="monthly", updated_at="2026-08-14")

    service.handle_event({"owner_id": "u-z", "success": True, "recurring_uid": "rec-z"},
                         now=datetime(2026, 8, 14, tzinfo=UTC))

    assert fresh_db.get_plan("u-z") == "pro"


def test_an_underpaid_upgrade_never_takes_away_the_tier_already_held(fresh_db):
    """Declining to upgrade is this function's job; confiscating what someone already uses is not."""
    db.upsert_subscription("u-w", provider="payplus", status="active", plan="pro",
                           cycle="monthly", provider_ref="rec-u-w", updated_at="2026-08-14")
    db.set_plan("u-w", "pro")
    db.upsert_subscription("u-w", provider="payplus", status="pending", plan="institution_100",
                           cycle="monthly", updated_at="2026-08-14")

    _charge("u-w", 5.0)        # a new charge, nowhere near anything

    assert fresh_db.get_plan("u-w") == "pro"
