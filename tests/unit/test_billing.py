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
        "more_info": "u-1", "status_code": "000", "amount": 49.9,
        "recurring_charge_information": {"recurring_uid": "rec_9"}}})
    assert ev == {"owner_id": "u-1", "success": True, "recurring_uid": "rec_9",
                  "is_renewal": True, "amount": 49.9}


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
    monkeypatch.setattr(service.payplus, "cancel_recurring", lambda *a, **k: None)   # no network
    # Activate, then cancel.
    service.handle_event({"owner_id": "u-3", "success": True, "recurring_uid": "rec_3"},
                         now=datetime(2026, 7, 19, tzinfo=UTC))
    service.cancel("u-3", now=datetime(2026, 7, 20, tzinfo=UTC))
    sub = fresh_db.get_subscription("u-3")
    assert sub["status"] == "canceled" and sub["cancel_at_period_end"] == 1
    assert fresh_db.get_plan("u-3") == "pro"         # still paid — keeps what they paid for
    # Before period end → no downgrade; after → downgraded to free.
    assert service.sweep_downgrades(now=datetime(2026, 8, 1, tzinfo=UTC)) == 0
    assert fresh_db.get_plan("u-3") == "pro"
    assert service.sweep_downgrades(now=datetime(2026, 9, 1, tzinfo=UTC)) == 1
    assert fresh_db.get_plan("u-3") == "free"


# ── Annual (prepaid year) ─────────────────────────────────────────────────────
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

    assert seen["cycle"] == "annual"
    assert seen["amount"] == 499.0            # the year up front, not 49.90
    sub = fresh_db.get_subscription("u-a")
    assert sub["plan"] == "pro" and sub["cycle"] == "annual" and sub["status"] == "pending"


def test_annual_charge_grants_a_year(fresh_db, monkeypatch):
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
    assert sub["current_period_end"][:4] == "2027"      # a year out, not a month


def test_cancelling_a_prepaid_year_keeps_access_to_the_end_of_it(fresh_db, monkeypatch):
    """The promise made when selling the annual plan: cancelling stops the renewal, it does not
    refund-by-lockout. Every remaining day of the paid year stays."""
    monkeypatch.setenv("PAYPLUS_API_KEY", "k")
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "s")
    monkeypatch.setenv("PAYPLUS_PAYMENT_PAGE_UID", "uid")
    monkeypatch.setattr(service.greeninvoice, "issue_receipt", lambda **k: None)
    monkeypatch.setattr(service.payplus, "create_payment_page", lambda *a, **k: {"link": "x"})
    monkeypatch.setattr(service.payplus, "cancel_recurring", lambda *a, **k: None)

    service.start_checkout("u-c", "c@d.e", "C", plan="pro", cycle="annual")
    service.handle_event({"owner_id": "u-c", "success": True, "recurring_uid": "rec_c"},
                         now=datetime(2026, 7, 19, tzinfo=UTC))
    service.cancel("u-c", now=datetime(2026, 8, 1, tzinfo=UTC))     # cancels a month in

    assert fresh_db.get_subscription("u-c")["cancel_at_period_end"] == 1
    # Ten months later: still paid for, so still pro.
    assert service.sweep_downgrades(now=datetime(2027, 5, 1, tzinfo=UTC)) == 0
    assert fresh_db.get_plan("u-c") == "pro"
    # Past the year: it lapses, and does not renew.
    assert service.sweep_downgrades(now=datetime(2027, 8, 1, tzinfo=UTC)) == 1
    assert fresh_db.get_plan("u-c") == "free"


def test_annual_is_cheaper_than_twelve_months():
    from app import plans

    for t in ("basic", "pro", "institution"):
        assert plans.price_ils(t, "annual") < plans.price_ils(t, "monthly") * 12
        assert plans.annual_saving_pct(t) >= 15


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
