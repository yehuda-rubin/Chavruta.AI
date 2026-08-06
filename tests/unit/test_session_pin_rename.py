"""User-renamable chats + pinning (up to db.MAX_PINNED_SESSIONS).

Pinned chats must sort ahead of everything else, most-recently-pinned first; renaming must not
touch first_q (the fallback for chats that were never renamed); and pinning past the cap must be
rejected rather than silently evicting an older pin.
"""

from __future__ import annotations

import app.db as db
import pytest

ALICE, BOB = "user-alice", "user-bob"


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pin.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_new_session_has_no_title_and_falls_back_to_first_q(d):
    sid = d.create_session("מה אומר רש\"י?", owner_id=ALICE)
    row = d.list_sessions(ALICE)[0]
    assert row["title"] is None
    assert row["first_q"] == 'מה אומר רש"י?'


def test_rename_persists_and_leaves_first_q_untouched(d):
    sid = d.create_session("שאלה ראשונה", owner_id=ALICE)
    assert d.rename_session(sid, ALICE, "השיעור על פרשת השבוע") is True
    row = d.list_sessions(ALICE)[0]
    assert row["title"] == "השיעור על פרשת השבוע"
    assert row["first_q"] == "שאלה ראשונה"


def test_another_user_cannot_rename_it(d):
    sid = d.create_session("שאלה", owner_id=ALICE)
    assert d.rename_session(sid, BOB, "גניבה") is False
    assert d.list_sessions(ALICE)[0]["title"] is None


def test_another_user_cannot_pin_it(d):
    sid = d.create_session("שאלה", owner_id=ALICE)
    assert d.set_session_pinned(sid, BOB, True) is False
    assert d.list_sessions(ALICE)[0]["pinned_at"] is None


def test_pinned_sessions_sort_before_unpinned_regardless_of_activity(d):
    old = d.create_session("ישן", owner_id=ALICE)
    new = d.create_session("חדש", owner_id=ALICE)
    d.set_session_pinned(old, ALICE, True)
    ids = [s["id"] for s in d.list_sessions(ALICE)]
    assert ids == [old, new]


def test_pinning_is_idempotent(d):
    sid = d.create_session("שאלה", owner_id=ALICE)
    assert d.set_session_pinned(sid, ALICE, True) is True
    assert d.set_session_pinned(sid, ALICE, True) is True
    assert d.list_sessions(ALICE)[0]["pinned_at"] is not None


def test_unpinning_frees_a_slot(d):
    sids = [d.create_session(f"q{i}", owner_id=ALICE) for i in range(4)]
    for sid in sids[:3]:
        d.set_session_pinned(sid, ALICE, True)
    with pytest.raises(db.TooManyPinnedError):
        d.set_session_pinned(sids[3], ALICE, True)
    d.set_session_pinned(sids[0], ALICE, False)
    assert d.set_session_pinned(sids[3], ALICE, True) is True


def test_pin_limit_is_per_owner_not_global(d):
    alice_sids = [d.create_session(f"a{i}", owner_id=ALICE) for i in range(3)]
    for sid in alice_sids:
        d.set_session_pinned(sid, ALICE, True)
    bob_sid = d.create_session("b", owner_id=BOB)
    assert d.set_session_pinned(bob_sid, BOB, True) is True


# ── excluded_from_review: per-chat opt-out from the operator's post-10.8.2026 review/improvement
# use (privacy policy section 12). Default must be "included" — an opt-out default would mean
# nobody ever bothers to exclude anything, defeating the point of offering the choice.

def test_new_session_defaults_to_included(d):
    sid = d.create_session("שאלה", owner_id=ALICE)
    row = d.list_sessions(ALICE)[0]
    assert row["excluded_from_review"] == 0


def test_exclude_and_reinclude_a_session(d):
    sid = d.create_session("שאלה", owner_id=ALICE)
    assert d.set_session_excluded(sid, ALICE, True) is True
    assert d.list_sessions(ALICE)[0]["excluded_from_review"] == 1
    assert d.set_session_excluded(sid, ALICE, False) is True
    assert d.list_sessions(ALICE)[0]["excluded_from_review"] == 0


def test_another_user_cannot_exclude_it(d):
    sid = d.create_session("שאלה", owner_id=ALICE)
    assert d.set_session_excluded(sid, BOB, True) is False
    assert d.list_sessions(ALICE)[0]["excluded_from_review"] == 0
