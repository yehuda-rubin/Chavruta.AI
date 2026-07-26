"""'My Shiurim' — the saved-lesson library.

The bug this pins: the list endpoint deliberately omits the Word documents (they are large), so a
caller that reads `files` off a LIST row gets nothing. Opening a lesson has to fetch the full record.
That mismatch is invisible in the API — both shapes are valid JSON — and showed up only as a lesson
that opened with no downloads attached.
"""

from __future__ import annotations

import pytest

import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "lessons.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


FILES = [
    {"name": "source-sheet.doc", "title": "גיליון מקורות", "content": "מקור א..."},
    {"name": "flow.doc", "title": "מהלך השיעור", "content": "פתיחה..."},
    {"name": "full.doc", "title": "השיעור המלא", "content": "בס\"ד..."},
]
CITATIONS = [{"ref": "Sukkah.2a", "text_he": "סוכה שהיא גבוהה"}]


def _save(d, lesson_id="L1", owner="u-1"):
    d.save_lesson(lesson_id, "שיעור על סוכה", "school", "a-c", "short", "he",
                  FILES, CITATIONS, owner_id=owner)


def test_saved_lesson_round_trips_its_word_files(fresh_db):
    _save(fresh_db)
    got = fresh_db.get_lesson("L1", "u-1")
    assert [f["name"] for f in got["files"]] == [f["name"] for f in FILES]
    assert got["files"][2]["content"].startswith("בס")
    assert len(got["citations"]) == 1


def test_the_list_omits_files_on_purpose(fresh_db):
    """Not a defect — the documents are large and the list must stay light. But it means a caller
    cannot read `files` off a list row, which is exactly what the UI was doing."""
    _save(fresh_db)
    row = fresh_db.list_lessons("u-1")[0]
    assert row["id"] == "L1" and row["topic"] == "שיעור על סוכה"
    assert "files" not in row
    assert "citations" not in row


def test_detail_is_the_only_source_of_the_files(fresh_db):
    """The contract the UI now depends on: whatever the list leaves out, the detail endpoint has."""
    _save(fresh_db)
    listed = fresh_db.list_lessons("u-1")[0]
    detail = fresh_db.get_lesson(listed["id"], "u-1")
    assert detail["files"] and len(detail["files"]) == 3


def test_lessons_are_scoped_to_their_owner(fresh_db):
    _save(fresh_db, owner="u-1")
    assert fresh_db.get_lesson("L1", "u-2") is None
    assert fresh_db.list_lessons("u-2") == []


def test_missing_lesson_reads_as_none(fresh_db):
    assert fresh_db.get_lesson("nope", "u-1") is None


def test_a_lesson_saved_without_files_does_not_crash_the_reader(fresh_db):
    """Degrade path: an empty files blob must come back as [] rather than raising."""
    fresh_db.save_lesson("L2", "נושא", "", "", "", "he", [], None, owner_id="u-1")
    got = fresh_db.get_lesson("L2", "u-1")
    assert got["files"] == [] and got["citations"] == []


def test_delete_removes_it_from_both_views(fresh_db):
    _save(fresh_db)
    assert fresh_db.delete_lesson("L1", "u-1") is True
    assert fresh_db.get_lesson("L1", "u-1") is None
    assert fresh_db.list_lessons("u-1") == []
    assert fresh_db.delete_lesson("L1", "u-1") is False      # idempotent


# ── Delete means delete: the documents are stored twice ───────────────────────
def _lesson_in_a_chat(d, owner="u-1"):
    """A lesson as it really lands: a library row AND a chat turn holding the same documents."""
    sid = d.create_session("שיעור על סוכה", owner_id=owner)
    mid = d.save_message(sid, "assistant", "📚 שיעור", intent="lesson", files=FILES)
    _save(d, owner=owner)
    d.link_lesson_message("L1", mid)
    return sid, mid


def test_deleting_a_lesson_strips_the_chat_copy_too(fresh_db):
    """The reported bug: the library entry went, and a full copy of the Word files stayed in the
    chat. Deleting has to reach both places or it hasn't deleted anything."""
    sid, _mid = _lesson_in_a_chat(fresh_db)
    assert fresh_db.get_messages(sid, "u-1")[0]["files"]        # present to begin with

    assert fresh_db.delete_lesson("L1", "u-1") is True
    msgs = fresh_db.get_messages(sid, "u-1")
    assert msgs[0]["files"] == []


def test_deleting_a_lesson_keeps_the_conversation(fresh_db):
    """Only the downloads go. Removing the whole chat because a library entry was tidied away is
    the more destructive surprise."""
    sid, _mid = _lesson_in_a_chat(fresh_db)
    fresh_db.delete_lesson("L1", "u-1")

    msgs = fresh_db.get_messages(sid, "u-1")
    assert len(msgs) == 1 and msgs[0]["text"] == "📚 שיעור"
    assert fresh_db.list_sessions("u-1")


def test_a_legacy_unlinked_lesson_still_deletes_from_the_library(fresh_db):
    """Rows saved before the link existed have no message_id — their chat copy can't be found, but
    deletion must not fail because of it."""
    _save(fresh_db)                                    # no link
    assert fresh_db.delete_lesson("L1", "u-1") is True
    assert fresh_db.get_lesson("L1", "u-1") is None


def test_delete_cannot_reach_another_owners_message(fresh_db):
    """A lesson row must never be usable to clear a message belonging to someone else."""
    sid = fresh_db.create_session("שיחה של מישהו אחר", owner_id="u-2")
    victim = fresh_db.save_message(sid, "assistant", "שיעור", intent="lesson", files=FILES)
    _save(fresh_db, owner="u-1")
    fresh_db.link_lesson_message("L1", victim)          # points at u-2's message

    fresh_db.delete_lesson("L1", "u-1")
    assert fresh_db.get_messages(sid, "u-2")[0]["files"]        # untouched
