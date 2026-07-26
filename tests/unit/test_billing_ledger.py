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
