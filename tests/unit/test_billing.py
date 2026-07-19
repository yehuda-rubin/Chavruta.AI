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
    assert fresh_db.get_plan("u-1") == "paid"
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
    assert fresh_db.get_plan("u-3") == "paid"        # still paid — keeps what they paid for
    # Before period end → no downgrade; after → downgraded to free.
    assert service.sweep_downgrades(now=datetime(2026, 8, 1, tzinfo=UTC)) == 0
    assert fresh_db.get_plan("u-3") == "paid"
    assert service.sweep_downgrades(now=datetime(2026, 9, 1, tzinfo=UTC)) == 1
    assert fresh_db.get_plan("u-3") == "free"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
