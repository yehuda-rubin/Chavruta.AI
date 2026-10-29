"""Tests for user notices and timed credit grants."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
import pytest
import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_grant_credits_with_expiry(fresh_db):
    owner = "u_tester_1"
    bal = fresh_db.grant_credits_with_expiry(owner, amount=3, days=30, reason="test grant")
    assert bal == 3
    assert fresh_db.get_credits(owner) == 3

    conn = fresh_db.get_conn()
    row = conn.execute("SELECT * FROM credit_grants WHERE owner_id=?", (owner,)).fetchone()
    assert row is not None
    assert int(row["amount"]) == 3
    assert int(row["remaining"]) == 3
    assert row["reason"] == "test grant"


def test_spend_credits_consumes_grants(fresh_db):
    owner = "u_tester_2"
    fresh_db.grant_credits_with_expiry(owner, amount=5, days=30, reason="grant 5")
    assert fresh_db.get_credits(owner) == 5

    spent, bal = fresh_db.spend_credits(owner, 2)
    assert spent is True
    assert bal == 3
    assert fresh_db.get_credits(owner) == 3

    conn = fresh_db.get_conn()
    row = conn.execute("SELECT remaining FROM credit_grants WHERE owner_id=?", (owner,)).fetchone()
    assert int(row["remaining"]) == 3


def test_expire_due_credit_grants(fresh_db):
    owner = "u_tester_3"
    fresh_db.grant_credits_with_expiry(owner, amount=4, days=-1, reason="expired grant")
    assert fresh_db.get_credits(owner) == 4

    deducted = fresh_db.expire_due_credit_grants(owner)
    assert deducted == 4
    assert fresh_db.get_credits(owner) == 0

    # Running it again shouldn't deduct further
    deducted2 = fresh_db.expire_due_credit_grants(owner)
    assert deducted2 == 0


def test_expire_grants_respects_spend(fresh_db):
    owner = "u_tester_4"
    fresh_db.grant_credits_with_expiry(owner, amount=3, days=-1, reason="expired grant")
    # User spends 2 credits before expiry sweep runs
    spent, bal = fresh_db.spend_credits(owner, 2)
    assert spent is True
    assert bal == 1

    # Expiry sweep only deducts the remaining 1 credit
    deducted = fresh_db.expire_due_credit_grants(owner)
    assert deducted == 1
    assert fresh_db.get_credits(owner) == 0


def test_user_notices_lifecycle(fresh_db):
    owner = "u_tester_5"
    nid = fresh_db.add_user_notice(owner, body="שלום עליכם", title="הודעה", kind="modal")
    assert nid > 0

    unread = fresh_db.get_unread_user_notices(owner)
    assert len(unread) == 1
    assert unread[0]["id"] == nid
    assert unread[0]["body"] == "שלום עליכם"
    assert unread[0]["title"] == "הודעה"
    assert unread[0]["kind"] == "modal"

    # Other owner sees nothing
    assert fresh_db.get_unread_user_notices("u_other") == []

    # Mark as read
    ok = fresh_db.mark_user_notice_read(owner, nid)
    assert ok is True
    assert fresh_db.get_unread_user_notices(owner) == []


def test_purge_owner_removes_notices_and_grants(fresh_db):
    owner = "u_tester_6"
    fresh_db.add_user_notice(owner, body="הודעה", title="כותרת")
    fresh_db.grant_credits_with_expiry(owner, amount=3, days=30)

    fresh_db.purge_owner(owner)

    conn = fresh_db.get_conn()
    assert conn.execute("SELECT 1 FROM user_notices WHERE owner_id=?", (owner,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM credit_grants WHERE owner_id=?", (owner,)).fetchone() is None
