"""Tests for admin granting plans and credits with timed expiry and in-app notices."""

import pytest
from app import api, db, plans


@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()
    return db


def test_admin_grant_timed_credits(clean_db):
    owner = "admin-tester"
    target = "user-abc-1"

    req = api.GrantIn(
        owner_id=target,
        kind="credits",
        credits=5,
        expires_in_days=30,
        note="test timed grant",
    )
    res = api.admin_grant(req, owner=owner)
    assert res["ok"] is True
    assert res["credits_added"] == 5
    assert clean_db.get_credits(target) == 5

    # Check credit grant recorded in credit_grants
    conn = clean_db.get_conn()
    row = conn.execute("SELECT * FROM credit_grants WHERE owner_id=?", (target,)).fetchone()
    assert row is not None
    assert int(row["amount"]) == 5
    assert int(row["remaining"]) == 5
    assert "test timed grant" in row["reason"]


def test_admin_grant_with_notice(clean_db):
    owner = "admin-tester"
    target = "user-abc-2"

    req = api.GrantIn(
        owner_id=target,
        kind="credits",
        credits=3,
        expires_in_days=30,
        notice_title="תודה על הדיווח!",
        notice_body="טיפלנו בדיווח שלך וקיבלת 3 קרדיטים.",
        note="reward for report",
    )
    res = api.admin_grant(req, owner=owner)
    assert res["ok"] is True
    assert clean_db.get_credits(target) == 3

    # Check unread notice delivered
    notices = clean_db.get_unread_user_notices(target)
    assert len(notices) == 1
    assert notices[0]["title"] == "תודה על הדיווח!"
    assert "טיפלנו בדיווח" in notices[0]["body"]
    assert notices[0]["kind"] == "modal"


def test_admin_grant_all_plan_tiers(clean_db):
    owner = "admin-tester"
    target = "user-abc-3"

    for tier_id in ("basic", "plus", "pro", "institution", "institution_50", "institution_100"):
        req = api.GrantIn(
            owner_id=target,
            kind="plan",
            plan=tier_id,
            days=7,
            note=f"test {tier_id}",
        )
        res = api.admin_grant(req, owner=owner)
        assert res["ok"] is True
        assert res["plan"] == tier_id
        assert clean_db.get_plan(target) == tier_id
