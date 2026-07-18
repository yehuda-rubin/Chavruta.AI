"""Account blocklist (app/db.py bans + app/accounts.py active_ban).

Pinned: a permanent block is always active; a timed block is active only until its deadline and then
lapses on its own (no cleanup needed); unban lifts it; and the raw store round-trips for the admin CLI.
"""
from __future__ import annotations

import pytest

import app.accounts as accounts
import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ban.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_no_ban_is_none(fresh_db):
    assert accounts.active_ban("nobody") is None


def test_permanent_ban_always_active(fresh_db):
    fresh_db.ban_account("u1", "2026-07-18T00:00:00+00:00", None, "ToS violation")
    ban = accounts.active_ban("u1", now_iso="2099-01-01T00:00:00+00:00")
    assert ban and ban["permanent"] is True and ban["until"] is None
    assert ban["reason"] == "ToS violation"


def test_timed_ban_active_then_expires(fresh_db):
    fresh_db.ban_account("u2", "2026-07-18T00:00:00+00:00", "2026-07-19T00:00:00+00:00", "spam")
    # Before the deadline → active.
    active = accounts.active_ban("u2", now_iso="2026-07-18T12:00:00+00:00")
    assert active and active["permanent"] is False and active["until"] == "2026-07-19T00:00:00+00:00"
    # After the deadline → lapsed on its own.
    assert accounts.active_ban("u2", now_iso="2026-07-20T00:00:00+00:00") is None


def test_unban_lifts_block(fresh_db):
    fresh_db.ban_account("u3", "2026-07-18T00:00:00+00:00", None, "")
    assert accounts.active_ban("u3", now_iso="2026-07-18T01:00:00+00:00") is not None
    assert fresh_db.unban_account("u3") is True
    assert accounts.active_ban("u3", now_iso="2026-07-18T01:00:00+00:00") is None
    assert fresh_db.unban_account("u3") is False        # already gone


def test_ban_upsert_and_list(fresh_db):
    fresh_db.ban_account("u4", "2026-07-18T00:00:00+00:00", None, "first")
    fresh_db.ban_account("u4", "2026-07-18T01:00:00+00:00", "2026-08-01T00:00:00+00:00", "second")
    row = fresh_db.get_ban("u4")
    assert row["banned_until"] == "2026-08-01T00:00:00+00:00" and row["reason"] == "second"
    assert [b["owner_id"] for b in fresh_db.list_bans()] == ["u4"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
