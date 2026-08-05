"""Scheduled account deletion with a grace period (app/db.py + app/accounts.py).

Pinned: scheduling records a future deadline; cancel clears it; the sweeper purges ONLY accounts past
their deadline and ONLY the target owner's data (sessions/messages/lessons/usage), leaving everyone
else — and the always-exempt 'local' user — untouched.
"""
from __future__ import annotations

import urllib.request

import pytest

import app.accounts as accounts
import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "acct.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def _seed_owner(d, owner):
    sid = d.create_session("q", mode="qa", owner_id=owner)
    d.save_message(sid, "user", "hi")
    d.save_lesson(f"L-{owner}", "topic", "", "", "", "he", [{"name": "x"}], owner_id=owner)
    d.bump_usage(owner, 0)
    return sid


def test_schedule_and_cancel(fresh_db):
    fresh_db.schedule_deletion("u1", "2026-07-18T00:00:00+00:00", "2026-08-17T00:00:00+00:00")
    acct = fresh_db.get_account("u1")
    assert acct["deletion_scheduled_for"] == "2026-08-17T00:00:00+00:00"
    fresh_db.cancel_deletion("u1")
    assert fresh_db.get_account("u1")["deletion_scheduled_for"] is None


def test_due_deletions_only_returns_past_deadlines(fresh_db):
    fresh_db.schedule_deletion("past", "2026-01-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00")
    fresh_db.schedule_deletion("future", "2026-07-01T00:00:00+00:00", "2027-01-01T00:00:00+00:00")
    due = fresh_db.due_deletions("2026-07-18T00:00:00+00:00")
    assert due == ["past"]


def test_purge_owner_removes_only_that_owner(fresh_db):
    _seed_owner(fresh_db, "alice")
    _seed_owner(fresh_db, "bob")
    fresh_db.purge_owner("alice")
    assert fresh_db.list_sessions("alice") == [] and fresh_db.list_lessons("alice") == []
    assert fresh_db.usage_today("alice") == 0
    assert fresh_db.get_account("alice") is None
    # Bob is untouched.
    assert len(fresh_db.list_sessions("bob")) == 1
    assert len(fresh_db.list_lessons("bob")) == 1
    assert fresh_db.usage_today("bob") == 1


def test_purge_owner_never_touches_local(fresh_db):
    _seed_owner(fresh_db, "local")
    fresh_db.purge_owner("local")           # must be a no-op guard
    assert len(fresh_db.list_sessions("local")) == 1


def test_run_due_purges_wipes_expired_accounts(fresh_db, monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)   # no auth-user delete in tests
    _seed_owner(fresh_db, "gone")
    _seed_owner(fresh_db, "stays")
    fresh_db.schedule_deletion("gone", "2026-01-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00")
    fresh_db.schedule_deletion("stays", "2026-07-01T00:00:00+00:00", "2027-01-01T00:00:00+00:00")

    n = accounts.run_due_purges("2026-07-18T00:00:00+00:00")
    assert n == 1
    assert fresh_db.list_sessions("gone") == []            # expired account purged
    assert len(fresh_db.list_sessions("stays")) == 1       # not-yet-due account survives


def test_schedule_sets_future_deadline(fresh_db, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_ACCOUNT_DELETION_GRACE_DAYS", "30")
    when = accounts.schedule("u9")
    assert fresh_db.get_account("u9")["deletion_scheduled_for"] == when
    # The deadline is in the future (grace period ahead of the request time).
    assert when > "2026-07-18"


# ── Subscription plan (billing groundwork) ────────────────────────────────────
def test_plan_defaults_to_free(fresh_db):
    assert fresh_db.get_plan("newcomer") == "free"


def test_set_plan_upserts_and_survives_deletion_schedule(fresh_db):
    fresh_db.set_plan("u1", "paid")
    assert fresh_db.get_plan("u1") == "paid"
    # Scheduling deletion (a separate upsert on the same row) must not clobber the plan.
    fresh_db.schedule_deletion("u1", "2026-07-18T00:00:00+00:00", "2026-08-17T00:00:00+00:00")
    assert fresh_db.get_plan("u1") == "paid"
    assert fresh_db.get_account("u1")["deletion_scheduled_for"] is not None
    # …and setting the plan doesn't wipe a pending deletion.
    fresh_db.set_plan("u1", "free")
    assert fresh_db.get_account("u1")["deletion_scheduled_for"] is not None
    assert fresh_db.get_plan("u1") == "free"


def test_purge_clears_plan(fresh_db):
    fresh_db.set_plan("u2", "paid")
    fresh_db.purge_owner("u2")
    assert fresh_db.get_plan("u2") == "free"     # row gone → back to the default


# ── Subscriptions (billing) ───────────────────────────────────────────────────
def test_subscription_partial_update_preserves_fields(fresh_db):
    # First write: provider + token from checkout.
    fresh_db.upsert_subscription("u1", provider="payplus", provider_ref="tok_123",
                                 status="active", current_period_end="2026-08-19T00:00:00+00:00",
                                 updated_at="2026-07-19T00:00:00+00:00")
    # A later webhook updates only status + period — must NOT wipe the stored token/provider.
    fresh_db.upsert_subscription("u1", status="past_due",
                                 current_period_end="2026-09-19T00:00:00+00:00",
                                 updated_at="2026-08-19T00:00:00+00:00")
    sub = fresh_db.get_subscription("u1")
    assert sub["provider"] == "payplus" and sub["provider_ref"] == "tok_123"
    assert sub["status"] == "past_due"
    assert sub["current_period_end"] == "2026-09-19T00:00:00+00:00"


def test_subscription_purged_with_account(fresh_db):
    fresh_db.upsert_subscription("u2", provider="payplus", status="active",
                                 updated_at="2026-07-19T00:00:00+00:00")
    fresh_db.purge_owner("u2")
    assert fresh_db.get_subscription("u2") is None


# ── count_supabase_users: the admin dashboard's real "how many accounts" figure ──────────────────
# Bug (caught live 2026-08-05): the dashboard showed db.count_accounts()'s total (3) next to
# "usage this week from 27 distinct owners" — because that local `accounts` table only gets a row
# on a plan change or credit grant (db.set_plan/add_credits), so almost every free signup never
# touches it. Supabase's own user list is the real signup count.

class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _users_page(n: int) -> bytes:
    import json
    return json.dumps({"users": [{"id": str(i)} for i in range(n)]}).encode()


def test_supabase_user_count_none_when_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert accounts.count_supabase_users() is None


def test_supabase_user_count_single_page(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _FakeResponse(_users_page(27)))
    assert accounts.count_supabase_users() == 27


def test_supabase_user_count_paginates(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    pages = iter([_users_page(1000), _users_page(1000), _users_page(42)])
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _FakeResponse(next(pages)))
    assert accounts.count_supabase_users() == 2042


def test_supabase_user_count_network_failure_is_none(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")

    def boom(req, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert accounts.count_supabase_users() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
