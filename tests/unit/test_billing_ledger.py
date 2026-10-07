"""The accounting ledger — the record of what was charged, kept apart from who was charged.

Two obligations pull in opposite directions: bookkeeping records must be retained for years, and a
user may ask to be forgotten well before that. The ledger resolves it by holding the money and not
the person, so purging an account never destroys a revenue record and the record never re-identifies
anyone.
"""

from __future__ import annotations

from datetime import UTC, datetime

import app.db as db
import pytest
from app.billing import service


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ledger.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(service.greeninvoice, "issue_receipt",
                        lambda **k: {"number": "INV-1001", "id": "doc-77"})


def test_a_charge_is_recorded(d):
    d.record_charge(charged_at="2026-07-26T10:00:00+00:00", amount=49.9, plan="pro",
                    cycle="monthly", provider="payplus", invoice_ref="INV-1")
    rows = d.list_charges()
    assert len(rows) == 1
    assert rows[0]["amount"] == 49.9 and rows[0]["plan"] == "pro"
    assert rows[0]["currency"] == "ILS"


def test_the_ledger_holds_no_identity(d):
    """The point of the design: nothing here says who paid."""
    d.record_charge(charged_at="2026-07-26T10:00:00+00:00", amount=49.9)
    row = d.list_charges()[0]
    assert "owner_id" not in row
    assert not any("owner" in k for k in row)


def test_a_purged_account_leaves_its_charges_behind(d):
    """The obligation this table exists for. Deleting the customer must not delete the revenue."""
    service.handle_event({"owner_id": "u-1", "success": True, "recurring_uid": "rec_1",
                          "amount": 49.9}, now=datetime(2026, 7, 26, tzinfo=UTC))
    assert len(d.list_charges()) == 1

    d.purge_owner("u-1")

    assert d.get_subscription("u-1") is None          # the customer record is gone
    assert len(d.list_charges()) == 1                 # the accounting record is not
    assert d.list_charges()[0]["amount"] == 49.9


def test_renewals_are_recorded_too(d):
    """A ledger that only held first payments would understate revenue by most of it."""
    at = datetime(2026, 7, 26, tzinfo=UTC)
    service.handle_event({"owner_id": "u-2", "success": True, "recurring_uid": "r", "amount": 49.9,
                          "is_renewal": False}, now=at)
    service.handle_event({"owner_id": "u-2", "success": True, "recurring_uid": "r", "amount": 49.9,
                          "is_renewal": True}, now=at.replace(month=8))

    rows = d.list_charges()
    assert len(rows) == 2
    assert {r["note"] for r in rows} == {"new", "renewal"}
    assert d.revenue_total() == 99.8


def test_a_failed_charge_is_not_recorded(d):
    service.handle_event({"owner_id": "u-3", "success": False, "amount": 49.9},
                         now=datetime(2026, 7, 26, tzinfo=UTC))
    assert d.list_charges() == []


def test_the_invoice_number_is_stored_for_reconciliation(d):
    service.handle_event({"owner_id": "u-4", "success": True, "recurring_uid": "r", "amount": 29.0},
                         now=datetime(2026, 7, 26, tzinfo=UTC))
    assert d.list_charges()[0]["invoice_ref"] == "INV-1001"


def test_the_charge_survives_an_invoicing_failure(d, monkeypatch):
    """The money already moved. A third-party outage must not cost us the record of it."""
    def boom(**k):
        raise RuntimeError("green-invoice down")

    monkeypatch.setattr(service.greeninvoice, "issue_receipt", boom)
    service.handle_event({"owner_id": "u-5", "success": True, "recurring_uid": "r", "amount": 199.0},
                         now=datetime(2026, 7, 26, tzinfo=UTC))

    rows = d.list_charges()
    assert len(rows) == 1 and rows[0]["amount"] == 199.0
    assert rows[0]["invoice_ref"] == ""      # flagged as missing, to be chased


def test_the_annual_cycle_is_recorded_as_sold(d):
    """An annual charge booked as monthly would misstate both revenue timing and the receipt."""
    d.upsert_subscription("u-6", plan="pro", cycle="annual",
                          updated_at="2026-07-26T00:00:00+00:00")
    service.handle_event({"owner_id": "u-6", "success": True, "recurring_uid": "r", "amount": 499.0},
                         now=datetime(2026, 7, 26, tzinfo=UTC))
    row = d.list_charges()[0]
    assert row["cycle"] == "annual" and row["amount"] == 499.0


def test_charges_can_be_read_for_a_period(d):
    for day, amt in (("2026-05-10", 10.0), ("2026-06-10", 20.0), ("2026-07-10", 30.0)):
        d.record_charge(charged_at=f"{day}T00:00:00+00:00", amount=amt)
    assert d.revenue_total(since="2026-06-01", until="2026-07-31") == 50.0
    assert len(d.list_charges(since="2026-07-01")) == 1


# ── Replay protection ─────────────────────────────────────────────────────────
# The webhook is signed over its body alone — no timestamp, no nonce — so the same signed delivery
# can arrive twice (a provider retry, or a captured request replayed). Applying it again must be a
# no-op: no second ledger row, no second receipt, and above all no reactivating a cancelled plan.

def _success(txn="txn_replay_1", **extra):
    ev = {"owner_id": "u-rp", "success": True, "recurring_uid": "rec_rp", "amount": 49.9,
          "transaction_uid": txn, "email": "a@b.c", "name": "A"}
    ev.update(extra)
    return ev


def test_the_same_charge_delivered_twice_is_applied_once(d, monkeypatch):
    receipts = []
    monkeypatch.setattr(service.greeninvoice, "issue_receipt",
                        lambda **k: receipts.append(k) or {"number": "INV-1"})
    service.handle_event(_success(), now=datetime(2026, 7, 26, tzinfo=UTC))
    first_end = d.get_subscription("u-rp")["current_period_end"]

    service.handle_event(_success(), now=datetime(2026, 8, 20, tzinfo=UTC))

    assert len(d.list_charges()) == 1
    assert len(receipts) == 1
    assert d.get_subscription("u-rp")["current_period_end"] == first_end


def test_a_replay_after_cancel_does_not_reactivate(d, monkeypatch):
    monkeypatch.setattr(service.payplus, "cancel_recurring", lambda ref: {})
    service.handle_event(_success(), now=datetime(2026, 7, 26, tzinfo=UTC))
    service.cancel("u-rp", now=datetime(2026, 7, 27, tzinfo=UTC))

    service.handle_event(_success(), now=datetime(2026, 7, 28, tzinfo=UTC))

    sub = d.get_subscription("u-rp")
    assert sub["status"] == "canceled"
    assert sub["cancel_at_period_end"]
    assert len(d.list_charges()) == 1
    # The period was not pushed out, so the sweep still takes the lapsed plan away.
    assert service.sweep_downgrades(now=datetime(2026, 9, 1, tzinfo=UTC)) == 1


def test_a_different_transaction_is_still_applied(d):
    """The guard keys on the payment, not the subscription: each instalment carries a new uid."""
    service.handle_event(_success("txn_a"), now=datetime(2026, 7, 26, tzinfo=UTC))
    service.handle_event(_success("txn_b", is_renewal=True), now=datetime(2026, 8, 26, tzinfo=UTC))
    assert len(d.list_charges()) == 2


def test_a_refund_row_is_not_mistaken_for_the_charge(d):
    """Refunds and coupon rebates share the txn_uid with a negative amount; they are not the charge."""
    d.record_charge(charged_at="2026-07-26T10:00:00+00:00", amount=-10.0, txn_uid="txn_neg")
    assert not d.charge_exists("txn_neg")
    service.handle_event(_success("txn_neg"), now=datetime(2026, 7, 26, tzinfo=UTC))
    assert d.charge_exists("txn_neg")


def test_events_without_a_transaction_uid_keep_the_old_behaviour(d):
    ev = {"owner_id": "u-nouid", "success": True, "recurring_uid": "r", "amount": 49.9}
    service.handle_event(dict(ev), now=datetime(2026, 7, 26, tzinfo=UTC))
    service.handle_event(dict(ev), now=datetime(2026, 7, 27, tzinfo=UTC))
    assert len(d.list_charges()) == 2
