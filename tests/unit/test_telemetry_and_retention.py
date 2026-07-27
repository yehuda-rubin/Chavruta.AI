"""Usage telemetry and chat retention.

Telemetry exists to answer product questions — which modes people use, when they work, what a real
answer costs, how often retrieval comes back empty. The line it must not cross is content: no
question, answer, source or attachment text is ever copied here. Those live in `messages`, where the
user can see and delete them; a second copy under a different lifetime would be a store nobody can
reach.

Retention is the other half: a conversation is kept for a bounded window rather than forever.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import app.accounts as accounts
import app.db as db
import pytest


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tel.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def _event(d, **kw):
    base = dict(at=datetime.now(UTC).isoformat(), hour_local=21, dow=1, owner_id="u-1",
                plan="pro", intent="qa", lang="he", prompt_tokens=1000, completion_tokens=200,
                billed_tokens=1600, llm_calls=1, ms=4200, grounded=1, no_source=0, citations=3,
                attachments=0)
    base.update(kw)
    d.record_usage_event(**base)


# ── What is measured ──────────────────────────────────────────────────────────
def test_an_event_is_recorded_and_aggregated(d):
    _event(d)
    h = d.usage_health()
    assert h["requests"] == 1 and h["tokens"] == 1600 and h["grounded"] == 1


def test_telemetry_stores_no_content(d):
    """The boundary. Nothing in this table may resemble a question, answer or source."""
    _event(d)
    row = d._agg("SELECT * FROM usage_events")[0]
    forbidden = {"question", "answer", "text", "prompt", "sources", "citations_text", "files"}
    assert not (forbidden & set(row)), f"content leaked into telemetry: {forbidden & set(row)}"
    assert all(not isinstance(v, str) or len(v) < 64 for v in row.values()), \
        "a long string in telemetry suggests content rather than a measurement"


def test_intent_breakdown_answers_which_modes_are_used(d):
    for intent in ("qa", "qa", "qa", "lesson", "explain"):
        _event(d, intent=intent, billed_tokens=90_000 if intent == "lesson" else 1600)
    by = {r["intent"]: r for r in d.usage_by_intent()}
    assert by["qa"]["requests"] == 3
    assert by["lesson"]["avg_tokens"] == 90_000       # the cost gap the pricing rests on


def test_hourly_breakdown_answers_when_people_work(d):
    for hour in (21, 21, 22, 8):
        _event(d, hour_local=hour)
    by = {r["hour"]: r["requests"] for r in d.usage_by_hour()}
    assert by == {8: 1, 21: 2, 22: 1}


def test_lesson_breakdown_shows_which_audiences_matter(d):
    _event(d, intent="lesson", audience="school", grade_band="a-c", length="short")
    _event(d, intent="lesson", audience="school", grade_band="a-c", length="short")
    _event(d, intent="lesson", audience="yeshiva", grade_band=None, length="long")
    rows = d.lesson_breakdown()
    assert rows[0]["audience"] == "school" and rows[0]["requests"] == 2


def test_per_owner_totals(d):
    _event(d, owner_id="u-1", billed_tokens=1000)
    _event(d, owner_id="u-1", billed_tokens=500)
    _event(d, owner_id="u-2", billed_tokens=9000)
    top = d.usage_by_owner()
    assert top[0]["owner_id"] == "u-2" and top[0]["tokens"] == 9000
    assert next(r for r in top if r["owner_id"] == "u-1")["tokens"] == 1500


def test_failures_are_visible(d):
    _event(d, error="LLMTransientError", grounded=0)
    assert d.usage_health()["errors"] == 1


def test_recording_never_raises(d):
    """Analytics must not be able to fail a request that otherwise worked."""
    d.record_usage_event(at=None, nonsense_field="x")     # bad row, no exception
    d.record_usage_event()                                 # empty, no exception


# ── Deletion ──────────────────────────────────────────────────────────────────
def test_purging_an_account_anonymises_its_events_without_losing_the_counts(d):
    """The person goes; the aggregate stays true. Deleting the rows would silently rewrite history
    for every total already reported."""
    _event(d, owner_id="u-1")
    _event(d, owner_id="u-2")

    d.purge_owner("u-1")

    assert d.usage_health()["requests"] == 2                       # nothing lost
    owners = {r["owner_id"] for r in d.usage_by_owner()}
    assert "u-1" not in owners and None in owners                  # identity detached
    assert "u-2" in owners


# ── Retention ─────────────────────────────────────────────────────────────────
def _aged_session(d, days_old: int, owner="u-1", messages: int = 0) -> str:
    """A session whose last activity was `days_old` days ago. Any messages are written FIRST, since
    saving one touches `updated_at` — which is the whole point of keying retention on it."""
    sid = d.create_session(f"שיחה בת {days_old} ימים", owner_id=owner)
    for i in range(messages):
        d.save_message(sid, "user", f"שאלה {i}")
    old = (datetime.now(UTC) - timedelta(days=days_old)).isoformat()
    with db._LOCK, db._tx(d.get_conn()) as conn:
        conn.execute("UPDATE sessions SET created_at=?, updated_at=? WHERE id=?", (old, old, sid))
    return sid


def test_chats_older_than_the_window_are_deleted(d, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CHAT_RETENTION_DAYS", "90")
    old = _aged_session(d, 120)
    recent = _aged_session(d, 10)

    assert accounts.run_retention() == 1
    ids = {s["id"] for s in d.list_sessions("u-1")}
    assert ids == {recent} and old not in ids


def test_retention_counts_from_last_activity_not_creation(d, monkeypatch):
    """An old chat someone still returns to must not be taken out from under them: posting a turn
    touches updated_at, and the window runs from there rather than from creation."""
    monkeypatch.setenv("CHAVRUTA_CHAT_RETENTION_DAYS", "90")
    sid = _aged_session(d, 200)
    d.save_message(sid, "user", "חוזר לשיחה הישנה")     # activity today

    assert accounts.run_retention() == 0
    assert [s["id"] for s in d.list_sessions("u-1")] == [sid]


def test_deleting_a_chat_takes_its_messages(d, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CHAT_RETENTION_DAYS", "90")
    sid = _aged_session(d, 120, messages=2)
    accounts.run_retention()
    assert d.get_messages(sid, "u-1") == []


def test_saved_lessons_are_not_swept(d, monkeypatch):
    """A lesson is the teacher's work product — retention tidies transcripts, not their output."""
    monkeypatch.setenv("CHAVRUTA_CHAT_RETENTION_DAYS", "90")
    _aged_session(d, 300)
    d.save_lesson("L1", "שיעור ישן", "", "", "", "he", [{"name": "a.doc"}], [], owner_id="u-1")

    accounts.run_retention()
    assert len(d.list_lessons("u-1")) == 1


def test_retention_can_be_turned_off(d, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CHAT_RETENTION_DAYS", "0")
    _aged_session(d, 999)
    assert accounts.run_retention() == 0
    assert len(d.list_sessions("u-1")) == 1


def test_the_default_window_is_ninety_days(d, monkeypatch):
    monkeypatch.delenv("CHAVRUTA_CHAT_RETENTION_DAYS", raising=False)
    assert accounts.retention_days() == 90


def test_a_dry_run_reports_what_would_go(d):
    _aged_session(d, 120)
    _aged_session(d, 10)
    cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    assert d.count_sessions_older_than(cutoff) == 1
    assert len(d.list_sessions("u-1")) == 2          # counting changes nothing
