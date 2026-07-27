"""Refunds — the code behind the 14-day cancellation the terms promise.

Until 2026-07-27 there was none: terms §10 granted a statutory right that nothing in the system could
exercise. These tests hold the two properties that make the mechanism trustworthy — the books can
always prove what was given back, and the same money cannot go back twice.
"""

from __future__ import annotations

from datetime import UTC, datetime

import app.db as db
import pytest
from app import plans
from app.billing import service


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "refunds.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No provider is reachable in a unit test. `calls` records what we WOULD have sent."""
    calls: list[tuple] = []
    monkeypatch.setattr(service.greeninvoice, "issue_receipt",
                        lambda **k: {"number": "INV-1001", "id": "doc-77"})
    monkeypatch.setattr(service.greeninvoice, "issue_credit_note",
                        lambda **k: {"number": "CN-2001", "id": "doc-88"})
    monkeypatch.setattr(service.payplus, "refund",
                        lambda uid, amount, **k: calls.append((uid, amount)) or {"ok": True})
    monkeypatch.setattr(service.payplus, "cancel_recurring", lambda *a, **k: None)
    return calls


def _charge(owner="u-1", amount=49.9, uid="txn_abc", at=datetime(2026, 7, 20, tzinfo=UTC)):
    service.handle_event({"owner_id": owner, "success": True, "recurring_uid": "rec_1",
                          "transaction_uid": uid, "amount": amount}, now=at)
    return db.list_charges()[0]["id"]


# ── the fee ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("amount,fee", [
    (49.9, 2.5),          # 5% — the percentage is what binds at these prices
    (1990.0, 99.5),       # still under the cap, just
    (4000.0, 100.0),      # the ₪100 cap: 5% would be ₪200
])
def test_the_cancellation_fee_is_the_lower_of_five_percent_and_a_hundred(amount, fee):
    assert plans.cancellation_fee_ils(amount) == fee


def test_the_quote_shows_the_consumed_days_without_deducting_them(d):
    """Both numbers matter, and they are not the same number. What may be withheld is a legal
    ceiling; what we give back is a business decision made above it."""
    q = plans.refund_quote(30.0, days_used=15, cycle="monthly")
    assert q["fee"] == 1.5
    assert q["consumed"] == 15.0                       # half of a 30-day period
    assert q["max_deduct"] == 16.5
    assert q["refund"] == 28.5                         # fee only — deliberately generous


# ── the mechanism ────────────────────────────────────────────────────────────

def test_a_refund_leaves_a_negative_row_and_never_edits_the_charge(d):
    cid = _charge(amount=49.9)
    service.refund(cid, amount=47.4, owner_id="u-1", now=datetime(2026, 7, 27, tzinfo=UTC))

    rows = db.list_charges()
    assert len(rows) == 2                              # the charge is still there, untouched
    assert sorted(r["amount"] for r in rows) == [-47.4, 49.9]
    assert db.get_charge(cid)["amount"] == 49.9
    assert db.revenue_total() == pytest.approx(2.5)     # what we actually kept


def test_the_same_payment_cannot_be_refunded_twice(d):
    cid = _charge(amount=49.9)
    service.refund(cid, owner_id="u-1")
    with pytest.raises(ValueError, match="already refunded"):
        service.refund(cid, owner_id="u-1")


def test_a_partial_refund_leaves_the_rest_refundable(d):
    cid = _charge(amount=49.9)
    out = service.refund(cid, amount=20.0)
    assert out["remaining"] == 29.9
    assert db.refunded_total("txn_abc") == 20.0

    service.refund(cid, amount=29.9)
    assert db.refunded_total("txn_abc") == 49.9
    with pytest.raises(ValueError, match="already refunded"):
        service.refund(cid, amount=0.01)


def test_refunding_more_than_the_charge_is_refused(d):
    cid = _charge(amount=49.9)
    with pytest.raises(ValueError, match="still refundable"):
        service.refund(cid, amount=60.0)


def test_a_refund_cancels_the_subscription_so_it_does_not_bill_again(d):
    """The step that is forgotten when this is done by hand: money back, subscription still live,
    and the customer is charged again in a month."""
    cid = _charge(owner="u-9")
    service.refund(cid, owner_id="u-9")
    assert db.get_subscription("u-9")["status"] == "canceled"


def test_the_subscription_can_be_kept_when_that_is_the_intent(d):
    cid = _charge(owner="u-10")
    service.refund(cid, owner_id="u-10", cancel_subscription=False)
    assert db.get_subscription("u-10")["status"] == "active"


def test_nothing_is_written_when_the_provider_refuses(d, monkeypatch):
    """The ordering that matters. If the money did not move, the books must not say it did."""
    def boom(*a, **k):
        raise RuntimeError("payplus said no")

    monkeypatch.setattr(service.payplus, "refund", boom)
    cid = _charge(owner="u-11")
    with pytest.raises(RuntimeError):
        service.refund(cid, owner_id="u-11")

    assert len(db.list_charges()) == 1                 # no refund row
    assert db.get_subscription("u-11")["status"] == "active"


def test_the_refund_survives_a_failed_credit_note(d, monkeypatch):
    """Mirror of the charge path: the money is already back, so a document failure is something to
    chase, not a reason to lose the record."""
    monkeypatch.setattr(service.greeninvoice, "issue_credit_note", lambda **k: None)
    cid = _charge()
    out = service.refund(cid)
    assert out["invoice_ref"] == ""
    assert db.refunded_total("txn_abc") > 0


def test_a_charge_with_no_transaction_uid_is_refused_with_instructions(d):
    """Rows written before the column existed. Refusing is right — but silently would leave an
    operator with no idea what to do next."""
    cid = db.record_charge(charged_at="2026-01-01T00:00:00+00:00", amount=49.9, provider="payplus")
    with pytest.raises(ValueError, match="PayPlus dashboard"):
        service.refund(cid)


def test_the_transaction_uid_is_captured_from_the_callback(d):
    """Without this the ledger stores the subscription handle and a refund has nothing to aim at."""
    from app.billing import payplus

    ev = payplus.parse_event({"transaction": {
        "uid": "txn_xyz", "more_info": "u-12", "status_code": "000", "amount": 49.9,
        "recurring_charge_information": {"recurring_uid": "rec_9"}}})
    assert ev["transaction_uid"] == "txn_xyz" and ev["recurring_uid"] == "rec_9"

    service.handle_event(ev, now=datetime(2026, 7, 26, tzinfo=UTC))
    assert db.list_charges()[0]["txn_uid"] == "txn_xyz"
