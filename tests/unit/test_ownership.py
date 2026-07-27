"""Per-user isolation: a chat belongs to whoever created it.

The invariant, stated once: a resource is visible, readable, modifiable and deletable ONLY by its
owner. Everything a signed-in user creates carries an owner_id, and every query filters on it.

These tests exist because the failure is silent in both directions — a missing filter leaks another
account's conversations with a perfectly normal-looking 200, and there is no error anywhere to
notice. Each resource gets the same four questions asked of it, so a new one added without scoping
shows up here rather than in production.
"""

from __future__ import annotations

import app.db as db
import pytest

ALICE, BOB = "user-alice", "user-bob"


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "own.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


@pytest.fixture
def alice_session(d):
    sid = d.create_session("מה אומר רש\"י?", mode="explain", owner_id=ALICE)
    d.save_message(sid, "user", "מה אומר רש\"י?")
    d.save_message(sid, "assistant", "רש\"י מפרש...", intent="explain")
    return sid


# ── Sessions ──────────────────────────────────────────────────────────────────
def test_a_session_is_listed_only_for_its_creator(d, alice_session):
    assert [s["id"] for s in d.list_sessions(ALICE)] == [alice_session]
    assert d.list_sessions(BOB) == []


def test_another_user_cannot_read_the_messages(d, alice_session):
    assert d.get_messages(alice_session, ALICE)
    assert d.get_messages(alice_session, BOB) == []


def test_another_user_cannot_delete_it(d, alice_session):
    assert d.delete_session(alice_session, BOB) is False
    assert d.list_sessions(ALICE), "Alice's session must survive Bob's delete"
    assert d.delete_session(alice_session, ALICE) is True


def test_another_user_cannot_append_to_it(d, alice_session):
    """owns_session is the gate every continue-the-chat route checks before writing a turn."""
    assert d.owns_session(alice_session, ALICE) is True
    assert d.owns_session(alice_session, BOB) is False


def test_another_user_cannot_read_its_mode(d, alice_session):
    assert d.get_session_mode(alice_session, ALICE) == "explain"
    assert d.get_session_mode(alice_session, BOB) is None


def test_deleting_a_session_takes_its_messages(d, alice_session):
    d.delete_session(alice_session, ALICE)
    assert d.get_messages(alice_session, ALICE) == []


# ── Lessons ───────────────────────────────────────────────────────────────────
@pytest.fixture
def alice_lesson(d):
    d.save_lesson("LES1", "שיעור", "school", "a-c", "short", "he",
                  [{"name": "f.doc", "title": "t", "content": "c"}], [], owner_id=ALICE)
    return "LES1"


def test_a_lesson_is_listed_only_for_its_creator(d, alice_lesson):
    assert len(d.list_lessons(ALICE)) == 1
    assert d.list_lessons(BOB) == []


def test_another_user_cannot_open_a_lesson(d, alice_lesson):
    assert d.get_lesson(alice_lesson, ALICE) is not None
    assert d.get_lesson(alice_lesson, BOB) is None


def test_another_user_cannot_delete_a_lesson(d, alice_lesson):
    assert d.delete_lesson(alice_lesson, BOB) is False
    assert d.get_lesson(alice_lesson, ALICE) is not None


# ── Account state ─────────────────────────────────────────────────────────────
def test_plan_credits_and_usage_are_per_owner(d):
    d.set_plan(ALICE, "pro")
    d.add_credits(ALICE, 100)
    d.bump_usage(ALICE, 0, units=5_000)

    assert d.get_plan(BOB) == "free"
    assert d.get_credits(BOB) == 0
    assert d.usage_today(BOB) == 0
    # And Bob spending cannot draw on Alice's balance.
    assert d.spend_credits(BOB, 1) == (False, 0)
    assert d.get_credits(ALICE) == 100


def test_purging_one_account_leaves_the_other_intact(d, alice_session):
    bob_sid = d.create_session("שאלה של בוב", owner_id=BOB)
    d.save_lesson("LB", "שיעור של בוב", "", "", "", "he", [], [], owner_id=BOB)
    d.add_credits(BOB, 7)

    d.purge_owner(ALICE)

    assert d.list_sessions(ALICE) == [] and d.list_lessons(ALICE) == []
    assert [s["id"] for s in d.list_sessions(BOB)] == [bob_sid]
    assert len(d.list_lessons(BOB)) == 1
    assert d.get_credits(BOB) == 7


# ── The local/offline user ────────────────────────────────────────────────────
def test_local_mode_is_its_own_owner_not_a_wildcard(d, alice_session):
    """Unauthenticated local use is the single-user 'local' identity — it must not see, or be seen
    by, a signed-in account."""
    local_sid = d.create_session("שאלה מקומית", owner_id="local")
    assert [s["id"] for s in d.list_sessions("local")] == [local_sid]
    assert d.get_messages(alice_session, "local") == []
    assert d.owns_session(local_sid, ALICE) is False


def test_purge_refuses_to_wipe_the_local_user(d):
    """Guard against a misconfigured deployment purging the shared local store."""
    sid = d.create_session("שיחה מקומית", owner_id="local")
    d.purge_owner("local")
    assert [s["id"] for s in d.list_sessions("local")] == [sid]
