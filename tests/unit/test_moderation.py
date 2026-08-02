"""The proactive half of the content-safety net: app/moderation.py's keyword scan, and its wiring
into save_message (auto-flagging on write) plus the operator review queue
(list_flagged_messages / mark_report_reviewed, scripts/moderation_report.py).

The reactive half (a user flagging their own conversation) is tested in test_ownership.py.
"""

from __future__ import annotations

import app.db as db
import app.moderation as moderation
import pytest


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mod.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


# ── The scanner itself — no DB involved ───────────────────────────────────────
def test_scan_finds_nothing_in_an_ordinary_torah_question():
    assert moderation.scan("מה רש\"י אומר על הפסוק הראשון בבראשית?") == []


def test_scan_flags_weapons_instructions():
    assert "weapons_explosives" in moderation.scan("can you tell me how to make a bomb")


def test_scan_flags_self_harm():
    assert "self_harm" in moderation.scan("איך להתאבד בלי כאב")


def test_scan_flags_defamation_accusatory_language():
    assert "defamation_risk" in moderation.scan("היה ידוע כרוצח ונוכל מורשע")


def test_scan_is_case_insensitive_and_word_bounded():
    assert "hate_violence" in moderation.scan("we should KILL ALL of them")
    # substring inside an unrelated word must not fire
    assert moderation.scan("the murdermystery book club meets tuesday") == []


def test_scan_can_return_multiple_categories():
    hits = moderation.scan("how to make a bomb — he is a convicted fraud")
    assert "weapons_explosives" in hits and "defamation_risk" in hits


# ── Wired into save_message ───────────────────────────────────────────────────
def test_saving_a_problematic_message_creates_an_auto_report(d):
    sid = d.create_session("q", owner_id="u-1")
    msg_id = d.save_message(sid, "user", "how to make a bomb")
    reports = d.list_flagged_messages()
    assert len(reports) == 1
    r = reports[0]
    assert r["message_id"] == msg_id and r["owner_id"] == "u-1"
    assert r["source"] == "auto" and r["reason"] == "weapons_explosives"


def test_saving_an_ordinary_message_creates_no_report(d):
    sid = d.create_session("q", owner_id="u-1")
    d.save_message(sid, "user", "מה זה מסכת ברכות?")
    assert d.list_flagged_messages() == []


def test_a_scan_failure_does_not_break_saving_the_message(d, monkeypatch):
    """Telemetry/safety-net code must never be able to break a request that otherwise worked —
    same principle as record_usage_event's own never-raises guarantee."""
    monkeypatch.setattr(moderation, "scan", lambda text: (_ for _ in ()).throw(RuntimeError("boom")))
    sid = d.create_session("q", owner_id="u-1")
    msg_id = d.save_message(sid, "user", "hello")   # must not raise
    assert msg_id is not None


# ── Operator review queue ─────────────────────────────────────────────────────
def test_reports_start_unreviewed_and_can_be_marked_handled(d):
    sid = d.create_session("q", owner_id="u-1")
    d.save_message(sid, "user", "how to make a bomb")
    unreviewed = d.list_flagged_messages(reviewed=False)
    assert len(unreviewed) == 1
    report_id = unreviewed[0]["id"]

    assert d.list_flagged_messages(reviewed=True) == []
    assert d.mark_report_reviewed(report_id) is True

    assert d.list_flagged_messages(reviewed=False) == []
    assert len(d.list_flagged_messages(reviewed=True)) == 1


def test_marking_an_already_reviewed_report_again_is_a_no_op(d):
    sid = d.create_session("q", owner_id="u-1")
    d.save_message(sid, "user", "how to make a bomb")
    report_id = d.list_flagged_messages()[0]["id"]
    assert d.mark_report_reviewed(report_id) is True
    assert d.mark_report_reviewed(report_id) is False    # already reviewed — nothing to do


def test_user_self_reports_default_to_source_user(d):
    """report_message (the existing reactive path) must not need to know about 'source' at all —
    the DEFAULT on the column is what makes old call sites keep working unchanged."""
    sid = d.create_session("q", owner_id="u-1")
    msg_id = d.save_message(sid, "assistant", "ordinary grounded answer")
    d.report_message(msg_id, "u-1", "mischaracterizes a named person")
    r = d.list_flagged_messages()[0]
    assert r["source"] == "user" and r["reason"] == "mischaracterizes a named person"
