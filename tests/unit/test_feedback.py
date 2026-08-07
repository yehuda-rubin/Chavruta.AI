"""General comment/correction/suggestion channel (app/db.py: submit_feedback / list_feedback /
mark_feedback_reviewed) — not tied to any specific message, unlike message_reports
(see test_moderation.py / test_ownership.py for that one).
"""

from __future__ import annotations

import app.db as db
import pytest


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "feedback.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_submitted_feedback_starts_unreviewed(d):
    d.submit_feedback("alice", "יש טעות בציטוט של רש\"י על בראשית א:א")
    unreviewed = d.list_feedback(reviewed=False)
    assert len(unreviewed) == 1
    assert unreviewed[0]["owner_id"] == "alice"
    assert unreviewed[0]["text"] == "יש טעות בציטוט של רש\"י על בראשית א:א"
    assert unreviewed[0]["reviewed_at"] is None
    assert d.list_feedback(reviewed=True) == []


def test_marking_feedback_reviewed_moves_it_off_the_backlog(d):
    d.submit_feedback("alice", "הצעה לשיפור")
    feedback_id = d.list_feedback()[0]["id"]
    assert d.mark_feedback_reviewed(feedback_id) is True
    assert d.list_feedback(reviewed=False) == []
    assert len(d.list_feedback(reviewed=True)) == 1


def test_marking_already_reviewed_feedback_again_is_a_no_op(d):
    d.submit_feedback("alice", "הערה")
    feedback_id = d.list_feedback()[0]["id"]
    assert d.mark_feedback_reviewed(feedback_id) is True
    assert d.mark_feedback_reviewed(feedback_id) is False


def test_feedback_from_multiple_owners_lists_newest_first(d):
    d.submit_feedback("alice", "ראשון")
    d.submit_feedback("bob", "שני")
    items = d.list_feedback()
    assert [f["owner_id"] for f in items] == ["bob", "alice"]


def test_marking_a_nonexistent_feedback_id_is_a_no_op(d):
    assert d.mark_feedback_reviewed(999) is False
