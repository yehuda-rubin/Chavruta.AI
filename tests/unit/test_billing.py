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

import pytest

import app.db as db
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
    # The webhook grants the tier recorded at checkout; with none recorded it defaults to pro,
    # which is what the legacy 'paid' value has always meant.
    assert fresh_db.get_plan("u-1") == "pro"
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
