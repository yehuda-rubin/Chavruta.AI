"""Unit tests for weekly credit stop refunds (capped at 3/week) and job cancellation."""
from __future__ import annotations

import app.db as db
import pytest
from app.jobs import JobRegistry


@pytest.fixture
def test_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_credits.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_refund_stopped_credits_weekly_cap(test_db):
    owner = "user_1"
    # Initial balance is 0
    assert test_db.get_credits(owner) == 0

    # First refund of 1 credit
    ref1 = test_db.refund_stopped_credits(owner, credits_spent=1, max_weekly=3, day="2026-09-06")
    assert ref1 == 1
    assert test_db.get_credits(owner) == 1

    # Second refund of 1 credit
    ref2 = test_db.refund_stopped_credits(owner, credits_spent=1, max_weekly=3, day="2026-09-07")
    assert ref2 == 1
    assert test_db.get_credits(owner) == 2

    # Third refund of 1 credit
    ref3 = test_db.refund_stopped_credits(owner, credits_spent=1, max_weekly=3, day="2026-09-08")
    assert ref3 == 1
    assert test_db.get_credits(owner) == 3

    # Fourth refund in same week: weekly cap reached!
    ref4 = test_db.refund_stopped_credits(owner, credits_spent=1, max_weekly=3, day="2026-09-09")
    assert ref4 == 0
    # Balance stays at 3, no additional credit added
    assert test_db.get_credits(owner) == 3


def test_refund_stopped_credits_partial_cap(test_db):
    owner = "user_2"
    # User spent 5 credits on a lesson, but max_weekly is 3
    ref = test_db.refund_stopped_credits(owner, credits_spent=5, max_weekly=3, day="2026-09-07")
    # Only 3 can be refunded
    assert ref == 3
    assert test_db.get_credits(owner) == 3

    # Any subsequent refund in same week gives 0
    ref_next = test_db.refund_stopped_credits(owner, credits_spent=1, max_weekly=3, day="2026-09-08")
    assert ref_next == 0
    assert test_db.get_credits(owner) == 3


def test_refund_stopped_credits_resets_next_sunday(test_db):
    owner = "user_3"
    # Week 1 (Sunday 2026-09-06 to Saturday 2026-09-12): use all 3 credits
    ref1 = test_db.refund_stopped_credits(owner, credits_spent=3, max_weekly=3, day="2026-09-10")
    assert ref1 == 3
    assert test_db.get_credits(owner) == 3

    # Still in week 1
    assert test_db.refund_stopped_credits(owner, credits_spent=1, max_weekly=3, day="2026-09-12") == 0

    # Week 2 starts Sunday 2026-09-13
    ref_week2 = test_db.refund_stopped_credits(owner, credits_spent=2, max_weekly=3, day="2026-09-13")
    assert ref_week2 == 2
    assert test_db.get_credits(owner) == 5


def test_job_registry_credits_and_cancellation():
    import time
    reg = JobRegistry(max_workers=2)

    # Submit job with 1 credit spent (sleeps so it's in-flight when cancelled)
    jid = reg.submit("alice", lambda: time.sleep(0.5) or {"ok": True}, credits_spent=1)
    job = reg.get(jid, "alice")
    assert job is not None
    assert job.credits_spent == 1

    # Cancel job: returns (True, 1) and zeros credits_spent to prevent double refund
    ok, spent = reg.cancel_job(jid, "alice")
    assert ok is True
    assert spent == 1
    assert job.credits_spent == 0

    # Second cancel call returns (False, 0)
    ok2, spent2 = reg.cancel_job(jid, "alice")
    assert ok2 is False
    assert spent2 == 0

    # Normal cancel method returns bool
    jid2 = reg.submit("alice", lambda: time.sleep(0.5) or {"ok": True})
    assert reg.cancel(jid2, "alice") is True
