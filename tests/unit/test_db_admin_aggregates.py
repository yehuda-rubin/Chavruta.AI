"""db.revenue_summary() — the admin dashboard's revenue breakdown by plan and currency, built on the
same billing_ledger the accounting-focused tests in test_billing_ledger.py already cover."""

from __future__ import annotations

import app.db as db
import pytest


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "revenue.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_empty_ledger_summarizes_to_nothing(d):
    summary = d.revenue_summary()
    assert summary["by_plan"] == []
    assert summary["totals"] == {}


def test_revenue_grouped_by_plan_and_currency(d):
    d.record_charge(charged_at="2026-07-01T00:00:00+00:00", amount=49.9, plan="pro")
    d.record_charge(charged_at="2026-07-02T00:00:00+00:00", amount=49.9, plan="pro")
    d.record_charge(charged_at="2026-07-03T00:00:00+00:00", amount=199.0, plan="institution")

    summary = d.revenue_summary()
    by_plan = {(r["plan"], r["currency"]): r for r in summary["by_plan"]}
    assert by_plan[("pro", "ILS")]["total"] == pytest.approx(99.8)
    assert by_plan[("pro", "ILS")]["charges"] == 2
    assert by_plan[("institution", "ILS")]["total"] == pytest.approx(199.0)
    assert summary["totals"]["ILS"] == pytest.approx(298.8)


def test_refund_nets_against_the_total(d):
    """A refund is stored as a negative-amount row in the same table (see billing_ledger's schema
    comment) — revenue_summary must net it out, not require separate refund handling."""
    d.record_charge(charged_at="2026-07-01T00:00:00+00:00", amount=49.9, plan="pro")
    d.record_charge(charged_at="2026-07-05T00:00:00+00:00", amount=-49.9, plan="pro", note="refund")

    summary = d.revenue_summary()
    assert summary["totals"]["ILS"] == pytest.approx(0.0)


def test_since_cutoff_excludes_earlier_charges(d):
    d.record_charge(charged_at="2026-06-01T00:00:00+00:00", amount=49.9, plan="pro")
    d.record_charge(charged_at="2026-07-15T00:00:00+00:00", amount=49.9, plan="pro")

    summary = d.revenue_summary(since="2026-07-01T00:00:00+00:00")
    assert summary["totals"]["ILS"] == pytest.approx(49.9)
