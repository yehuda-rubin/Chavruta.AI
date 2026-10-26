"""School-track minors: the data foundation (specs/009-school-minors, Wave 1-A, T001-T011).

Everything here is synthetic. No LLM or network is touched: Supabase and the admin API are faked.
The invariants pinned, in the order the spec states them:

  * the age record is write-once, refuses under-12s, and `adult_from` is the first of the month after
    the 18th-birthday month;
  * NO RECORD MEANS ADULT: legacy accounts are never silently turned into minors;
  * `minor_until` is stamped at write time and never moves, so content written as a minor stays out of
    review and still expires after its author turns 18;
  * minors are excluded from review, retention is a second pass independent of activity, marketing
    skips them, admin queues redact them, and purge_owner leaves nothing behind.
"""
from __future__ import annotations

import json
import sqlite3
import types
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

import app.accounts as accounts
import app.db as db
import app.marketing as marketing
import app.minors as minors
import app.security as security

TODAY = date(2026, 10, 26)


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "minors.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.delenv("CHAVRUTA_MINOR_RETENTION_DAYS", raising=False)
    db.get_conn()
    return db


def _make_minor(owner="kid", year=2012, month=5):
    """Born May 2012 ⇒ adult_from 2030-06-01: a minor on TODAY."""
    return minors.set_age_once(owner, year, month, today=TODAY)


def _chat(owner, text="synthetic question"):
    sid = db.create_session(text, mode="qa", owner_id=owner)
    mid = db.save_message(sid, "user", text)
    return sid, mid


def _stamp(table, mid):
    return db.get_conn().execute(f"SELECT minor_until FROM {table} WHERE id=?", (mid,)).fetchone()[0]


# ── T001: schema ──────────────────────────────────────────────────────────────
def test_migration_35_creates_everything(d):
    conn = db.get_conn()
    assert db.SCHEMA_VERSION == 36
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    for t in ("age_records", "age_record_log", "org_join_requests", "parent_links",
              "content_denylist", "crisis_alerts"):
        assert db._table_exists(conn, t), t
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}  # noqa: E731
    for t in ("messages", "saved_lessons", "saved_source_sheets"):
        assert "minor_until" in cols(t)
    assert "is_minor" in cols("org_members") and "safety_contacts" in cols("orgs")
    idx = {r[1] for r in conn.execute("PRAGMA index_list(messages)")}
    assert "idx_messages_minor_until" in idx


def test_upgrading_from_34_is_idempotent_and_keeps_rows(monkeypatch, tmp_path):
    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(db, "_conn", None)
    db.create_session("old chat", owner_id="someone")
    db.get_conn().close()
    raw = sqlite3.connect(path)
    for t in ("age_records", "age_record_log", "org_join_requests", "parent_links",
              "content_denylist", "crisis_alerts"):
        raw.execute(f"DROP TABLE {t}")
    raw.execute("DROP INDEX idx_messages_minor_until")
    raw.execute("PRAGMA user_version = 34")
    raw.commit()
    raw.close()
    monkeypatch.setattr(db, "_conn", None)
    conn = db.get_conn()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert db._table_exists(conn, "age_records")
    assert db.list_sessions("someone")
    db.get_conn().close()
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()                                   # second open at the current version: no error


# ── T002: age records ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("y,m,expected", [
    (2012, 5, "2030-06-01"),
    (2012, 12, "2031-01-01"),       # December rolls into the next year
    (2008, 1, "2026-02-01"),
])
def test_adult_from_is_first_of_month_after_18th_birthday_month(y, m, expected):
    assert minors.adult_from(y, m) == expected


def test_set_age_once_is_write_once_and_logged(d):
    rec = _make_minor()
    assert rec["adult_from"] == "2030-06-01" and rec["adult_terms_accepted_at"] is None
    with pytest.raises(minors.AgeAlreadySet):
        minors.set_age_once("kid", 1990, 1, today=TODAY)       # lying on the second try changes nothing
    assert minors.get_age("kid")["birth_year"] == 2012
    log = db.get_conn().execute("SELECT actor_kind, new_birth_year FROM age_record_log").fetchall()
    assert [(r[0], r[1]) for r in log] == [("self", 2012)]


def test_under_twelve_is_refused_and_nothing_is_stored(d):
    with pytest.raises(minors.UnderMinimumAge):
        minors.set_age_once("tiny", 2016, 1, today=TODAY)
    assert minors.get_age("tiny") is None
    # Boundary: born Oct 2014 turns 12 in Oct 2026; certainty comes on 1 Nov, so still refused today.
    with pytest.raises(minors.UnderMinimumAge):
        minors.set_age_once("edge", 2014, 10, today=TODAY)
    assert minors.set_age_once("ok", 2014, 9, today=TODAY)["birth_year"] == 2014


@pytest.mark.parametrize("y,m", [(1899, 1), (2012, 0), (2012, 13), (3000, 1), ("x", 1), (True, 1), (None, 1)])
def test_nonsense_birth_values_are_refused(d, y, m):
    with pytest.raises(minors.AgeError):
        minors.set_age_once("u", y, m, today=TODAY)


def test_adult_declaration_stamps_terms_but_a_minor_does_not(d):
    adult = minors.set_age_once("grown", 1990, 3, today=TODAY)
    assert adult["adult_terms_accepted_at"]
    assert not minors.is_minor("grown", TODAY) and not minors.adult_terms_required("grown", TODAY)
    _make_minor()
    assert minors.is_minor("kid", TODAY)


def test_no_record_means_adult_never_minor(d):
    assert minors.is_minor("legacy-user", TODAY) is False
    assert minors.is_minor("local", TODAY) is False
    assert minors.adult_terms_required("legacy-user", TODAY) is False
    assert minors.minor_owner_ids(TODAY) == set()


def test_turning_18_flips_minor_and_requires_adult_terms(d):
    _make_minor()
    just_before, on_day = date(2030, 5, 31), date(2030, 6, 1)
    assert minors.is_minor("kid", just_before) and not minors.is_minor("kid", on_day)
    assert not minors.adult_terms_required("kid", just_before)
    assert minors.adult_terms_required("kid", on_day)
    with pytest.raises(minors.NotAdultYet):
        minors.accept_adult_terms("kid", just_before)
    minors.accept_adult_terms("kid", on_day)
    assert not minors.adult_terms_required("kid", on_day)
    with pytest.raises(minors.AgeNotSet):
        minors.accept_adult_terms("nobody", on_day)


def test_correct_age_needs_parent_or_operator_and_is_logged(d):
    _make_minor()
    for bad in ("self", "child", ""):
        with pytest.raises(ValueError):
            minors.correct_age("kid", 2011, 5, actor="kid", actor_kind=bad, today=TODAY)
    rec = minors.correct_age("kid", 2011, 5, actor="mum", actor_kind="parent", today=TODAY)
    assert rec["adult_from"] == "2029-06-01"
    minors.correct_age("kid", 2012, 5, actor="ops", actor_kind="operator", today=TODAY)
    rows = db.get_conn().execute(
        "SELECT actor, actor_kind, old_birth_year, new_birth_year FROM age_record_log ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("kid", "self", None, 2012), ("mum", "parent", 2012, 2011),
                                        ("ops", "operator", 2011, 2012)]
    with pytest.raises(minors.AgeNotSet):
        minors.correct_age("ghost", 2011, 5, actor="mum", actor_kind="parent", today=TODAY)
    with pytest.raises(minors.UnderMinimumAge):
        minors.correct_age("kid", 2017, 5, actor="mum", actor_kind="parent", today=TODAY)


def test_retention_days_env_and_bad_values(monkeypatch):
    assert minors.minor_retention_days() == 60
    monkeypatch.setenv("CHAVRUTA_MINOR_RETENTION_DAYS", "14")
    assert minors.minor_retention_days() == 14
    for bad in ("0", "-5", "abc", ""):
        monkeypatch.setenv("CHAVRUTA_MINOR_RETENTION_DAYS", bad)
        assert minors.minor_retention_days() >= 1


# ── T003: minor_until at write time ───────────────────────────────────────────
def test_minor_content_is_stamped_adult_content_is_not(d):
    minors.set_age_once("kid", 2012, 5)                    # a minor until 2030 (real clock)
    minors.set_age_once("grown", 1990, 3)
    _, kid_msg = _chat("kid")
    _, grown_msg = _chat("grown")
    _, legacy_msg = _chat("no-record")
    _, local_msg = _chat("local")
    stamp = _stamp("messages", kid_msg)
    assert stamp is not None
    delta = datetime.fromisoformat(stamp) - datetime.now(UTC)
    assert timedelta(days=59) < delta <= timedelta(days=60)
    assert _stamp("messages", grown_msg) is None and _stamp("messages", legacy_msg) is None
    assert _stamp("messages", local_msg) is None
    db.save_lesson("L-kid", "t", "", "", "", "he", [{"name": "x"}], owner_id="kid")
    db.save_lesson("L-grown", "t", "", "", "", "he", [{"name": "x"}], owner_id="grown")
    db.save_source_sheet("S-kid", "t", "raw", [], [], owner_id="kid")
    db.save_source_sheet("S-grown", "t", "raw", [], [], owner_id="grown")
    q = lambda t, i: db.get_conn().execute(f"SELECT minor_until FROM {t} WHERE id=?", (i,)).fetchone()[0]  # noqa: E731
    assert q("saved_lessons", "L-kid") and q("saved_lessons", "L-grown") is None
    assert q("saved_source_sheets", "S-kid") and q("saved_source_sheets", "S-grown") is None


def test_retention_env_changes_the_stamp(d, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_MINOR_RETENTION_DAYS", "7")
    minors.set_age_once("kid", 2012, 5)
    _, mid = _chat("kid")
    delta = datetime.fromisoformat(_stamp("messages", mid)) - datetime.now(UTC)
    assert timedelta(days=6) < delta <= timedelta(days=7)


def test_the_stamp_never_moves_after_the_author_turns_18(d):
    minors.set_age_once("kid", 2012, 5)
    sid, old = _chat("kid", "written as a minor")
    before = _stamp("messages", old)
    # The author becomes an adult (parent corrects the age): old content keeps its stamp...
    minors.correct_age("kid", 1990, 5, actor="ops", actor_kind="operator")
    assert not minors.is_minor("kid")
    new = db.save_message(sid, "user", "written as an adult")
    assert _stamp("messages", old) == before and before is not None
    assert _stamp("messages", new) is None                       # ...and new content is not stamped
    # ...and nothing in db.py ever rewrites the column.
    import inspect
    src = inspect.getsource(db)
    assert "SET minor_until" not in src


def test_a_session_is_stamped_for_its_owner_not_the_caller(d):
    minors.set_age_once("kid", 2012, 5)
    sid = db.create_session("q", owner_id="kid")
    mid = db.save_message(sid, "assistant", "reply")             # assistant rows too
    assert _stamp("messages", mid) is not None


# ── T004: review ──────────────────────────────────────────────────────────────
def test_reviewable_questions_excludes_minors_forever(d):
    minors.set_age_once("kid", 2012, 5)
    minors.set_age_once("grown", 1990, 3)
    _chat("kid", "kid question")
    _chat("grown", "grown question")
    _chat("no-record", "legacy question")
    got = {r["text"] for r in db.reviewable_questions(since="2026-08-10T00:00:00", opted_out_owners=())}
    assert got == {"grown question", "legacy question"}
    # Even after the kid is corrected to an adult, the stamped rows stay out.
    minors.correct_age("kid", 1990, 5, actor="ops", actor_kind="operator")
    _chat("kid", "kid as adult")
    got = {r["text"] for r in db.reviewable_questions(since="2026-08-10T00:00:00", opted_out_owners=())}
    assert "kid question" not in got and "kid as adult" in got


def test_review_guard_also_covers_unstamped_rows_of_a_current_minor(d):
    """Belt and braces: a row with no stamp (written before the record existed) by someone who is a
    minor NOW is still excluded."""
    _, mid = _chat("kid", "pre-record text")
    minors.set_age_once("kid", 2012, 5)
    assert _stamp("messages", mid) is None
    assert db.reviewable_questions(since="2026-08-10T00:00:00", opted_out_owners=()) == []


# ── T005: retention second pass ───────────────────────────────────────────────
def test_second_pass_deletes_by_stamp_not_by_activity(d, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CHAT_RETENTION_DAYS", "0")      # general retention OFF
    minors.set_age_once("kid", 2012, 5)
    minors.set_age_once("grown", 1990, 3)
    sid, expired = _chat("kid", "will expire")
    _, fresh = _chat("kid", "still valid")
    _, adult_msg = _chat("grown", "adult text")
    db.save_lesson("L-kid", "t", "", "", "", "he", [{"name": "x"}], owner_id="kid")
    db.save_source_sheet("S-kid", "t", "raw", [], [], owner_id="kid")
    db.report_message(expired, "kid", "oops")
    conn = db.get_conn()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    conn.execute("UPDATE messages SET minor_until=? WHERE id=?", (past, expired))
    conn.execute("UPDATE saved_lessons SET minor_until=?", (past,))
    conn.execute("UPDATE saved_source_sheets SET minor_until=?", (past,))
    conn.commit()
    accounts.run_retention()
    ids = {r[0] for r in conn.execute("SELECT id FROM messages")}
    assert expired not in ids and fresh in ids and adult_msg in ids
    assert db.list_lessons("kid") == [] and db.list_source_sheets("kid") == []
    assert conn.execute("SELECT COUNT(*) FROM message_reports").fetchone()[0] == 0
    # A session left with surviving messages loses the quoted title; an emptied one is gone.
    assert conn.execute("SELECT COUNT(*) FROM sessions WHERE id=?", (sid,)).fetchone()[0] == 0


def test_second_pass_scrubs_the_title_of_a_session_that_survives(d):
    minors.set_age_once("kid", 2012, 5)
    sid, first = _chat("kid", "title text")
    second = db.save_message(sid, "assistant", "reply")
    conn = db.get_conn()
    conn.execute("UPDATE messages SET minor_until=? WHERE id=?",
                 ((datetime.now(UTC) - timedelta(days=1)).isoformat(), first))
    conn.commit()
    accounts.run_retention()
    row = conn.execute("SELECT first_q, title FROM sessions WHERE id=?", (sid,)).fetchone()
    assert "title text" not in (row[0] or "") and row[1] is None
    assert conn.execute("SELECT 1 FROM messages WHERE id=?", (second,)).fetchone()


def test_second_pass_leaves_unexpired_and_adult_rows_alone(d):
    minors.set_age_once("kid", 2012, 5)
    _, mid = _chat("kid")
    assert accounts._run_minor_retention(None)["messages"] == 0
    assert db.get_conn().execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone()


# ── T006: purge_owner ─────────────────────────────────────────────────────────
def test_purge_owner_clears_the_new_tables_and_the_referral_gap(d):
    conn = db.get_conn()
    now = db._now()
    minors.set_age_once("kid", 2012, 5)
    minors.correct_age("kid", 2012, 5, actor="mum", actor_kind="parent")
    conn.execute("INSERT INTO orgs (id,name,owner_id,plan,created_at) VALUES ('o','S','boss','institution',?)", (now,))
    conn.execute("INSERT INTO org_join_requests (org_id,owner_id,requested_by,status,created_at) "
                 "VALUES ('o','kid','teacher','pending',?)", (now,))
    conn.execute("INSERT INTO parent_links VALUES ('mum','kid','active',?,?)", (now, now))
    conn.execute("INSERT INTO content_denylist VALUES ('parent','kid','work','w1','mum',?)", (now,))
    conn.execute("INSERT INTO content_denylist VALUES ('org','o','work','w2','teacher',?)", (now,))
    conn.execute("INSERT INTO crisis_alerts (owner_id,org_id,category,detector,created_at) "
                 "VALUES ('kid','o','self_harm','phrase',?)", (now,))
    conn.execute("UPDATE orgs SET safety_contacts=? WHERE id='o'", (json.dumps(["kid", "teacher"]),))
    # referral: kid is a referred user AND a partner; "other" referred by kid; reward rows both ways
    conn.execute("INSERT INTO referral_partners (owner_id,code,created_at) VALUES ('kid','KIDCODE',?)", (now,))
    conn.execute("INSERT INTO referral_redemptions VALUES ('kid','partner1','P1',?)", (now,))
    conn.execute("INSERT INTO referral_redemptions VALUES ('other','kid','KIDCODE',?)", (now,))
    conn.execute("INSERT INTO referral_rewards (referrer_owner_id,referred_owner_id,charge_amount_ils,"
                 "reward_ils,created_at) VALUES ('kid','other',100,10,?)", (now,))
    conn.commit()

    db.purge_owner("kid")
    c = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    assert c("SELECT * FROM age_records WHERE owner_id='kid'") == []
    assert c("SELECT * FROM age_record_log WHERE owner_id='kid'") == []
    assert c("SELECT * FROM org_join_requests WHERE owner_id='kid'") == []
    assert c("SELECT * FROM parent_links") == []
    assert c("SELECT * FROM content_denylist WHERE scope_id='kid'") == []
    assert len(c("SELECT * FROM content_denylist WHERE scope_id='o'")) == 1       # org setting stays
    assert c("SELECT * FROM crisis_alerts") == []
    assert json.loads(conn.execute("SELECT safety_contacts FROM orgs WHERE id='o'").fetchone()[0]) == ["teacher"]
    assert c("SELECT * FROM referral_partners WHERE owner_id='kid'") == []
    assert c("SELECT * FROM referral_redemptions WHERE referred_owner_id='kid'") == []
    # The other party's attribution row and the money row stay, minus the departed id.
    assert c("SELECT referrer_owner_id FROM referral_redemptions WHERE referred_owner_id='other'")[0][0] == db.DELETED_OWNER
    r = c("SELECT referrer_owner_id, reward_ils FROM referral_rewards")[0]
    assert r[0] == db.DELETED_OWNER and r[1] == 10


def test_purging_a_parent_removes_their_switches_and_names_not_the_childs_age(d):
    conn = db.get_conn()
    now = db._now()
    minors.set_age_once("kid", 2012, 5)
    minors.correct_age("kid", 2012, 6, actor="mum", actor_kind="parent")
    conn.execute("INSERT INTO parent_links VALUES ('mum','kid','active',?,?)", (now, now))
    db.purge_owner("mum")
    assert conn.execute("SELECT COUNT(*) FROM parent_links").fetchone()[0] == 0
    assert minors.get_age("kid")                                            # the child's record stays
    actors = {r[0] for r in conn.execute("SELECT actor FROM age_record_log")}
    assert "mum" not in actors and db.DELETED_OWNER in actors


# ── T007: marketing ───────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, body): self._b = body
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _fake_admin_users(monkeypatch, users):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(json.dumps({"users": users}).encode()))


def test_marketing_recipients_skip_minors_and_non_consenting(d, monkeypatch):
    minors.set_age_once("kid", 2012, 5)
    minors.set_age_once("grown", 1990, 3)
    consent = {"marketing_consent": True}
    _fake_admin_users(monkeypatch, [
        {"id": "kid", "email": "kid@example.invalid", "user_metadata": consent},
        {"id": "grown", "email": "grown@example.invalid", "user_metadata": consent},
        {"id": "legacy", "email": "legacy@example.invalid", "user_metadata": consent},
        {"id": "no", "email": "no@example.invalid", "user_metadata": {}},
    ])
    assert marketing.list_marketing_recipients() == [("grown", "grown@example.invalid"),
                                                     ("legacy", "legacy@example.invalid")]


def test_a_minor_whose_birthday_passed_is_mailable_again(d, monkeypatch):
    minors.set_age_once("kid", 2012, 5)
    db.get_conn().execute("UPDATE age_records SET adult_from='2000-01-01'")
    db.get_conn().commit()
    _fake_admin_users(monkeypatch, [{"id": "kid", "email": "k@example.invalid",
                                     "user_metadata": {"marketing_consent": True}}])
    assert marketing.list_marketing_recipients() == [("kid", "k@example.invalid")]


def test_broadcast_script_uses_the_consent_and_minor_filter():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "scripts" / "send_broadcast.py").read_text(encoding="utf-8")
    assert "list_marketing_recipients" in src and "list_supabase_user_emails" not in src


# ── T008: admin queues ────────────────────────────────────────────────────────
def test_flagged_messages_redact_minor_rows_only(d):
    minors.set_age_once("kid", 2012, 5)
    minors.set_age_once("grown", 1990, 3)
    _, kid_mid = _chat("kid", "contact me at x@example.invalid or 0501234567 about a long private matter indeed")
    _, grown_mid = _chat("grown", "adult text")
    db.report_message(kid_mid, "kid", "wrong")
    db.report_message(grown_mid, "grown", "also wrong")
    rows = {r["id"]: r for r in db.list_flagged_messages()}
    kid_row = next(r for r in rows.values() if r.get("minor"))
    assert set(kid_row) == {"id", "category", "snippet_redacted", "created_at", "minor"}
    assert kid_row["category"] == "wrong" and kid_row["minor"] is True
    assert "example.invalid" not in kid_row["snippet_redacted"] and "0501" not in kid_row["snippet_redacted"]
    assert len(kid_row["snippet_redacted"]) <= db.REDACTED_SNIPPET_CHARS + 1
    adult_row = next(r for r in rows.values() if not r.get("minor"))
    assert adult_row["owner_id"] == "grown" and adult_row["text"] == "adult text"


def test_flagged_rows_stay_redacted_after_the_author_turns_18(d):
    minors.set_age_once("kid", 2012, 5)
    _, mid = _chat("kid", "stamped as a minor")
    db.report_message(mid, "kid", "r")
    minors.correct_age("kid", 1990, 5, actor="ops", actor_kind="operator")
    (row,) = db.list_flagged_messages()
    assert row["minor"] is True and "owner_id" not in row and "text" not in row


def test_feedback_from_a_minor_is_redacted(d):
    minors.set_age_once("kid", 2012, 5)
    db.submit_feedback("kid", "a suggestion from a child")
    db.submit_feedback("grown", "a suggestion from an adult")
    by_minor = {r["minor"] if "minor" in r else False: r for r in db.list_feedback()}
    assert set(by_minor[True]) == {"id", "category", "snippet_redacted", "created_at", "minor"}
    assert by_minor[False]["owner_id"] == "grown" and by_minor[False]["text"].startswith("a suggestion")


# ── T009 / T011: require_auth ─────────────────────────────────────────────────
def _req(path="/query", method="GET"):
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path), state=types.SimpleNamespace(),
                                 method=method)


@pytest.fixture
def sb_mode(monkeypatch, d):
    """Supabase mode with a controllable token payload; no network, no keys."""
    holder = {"payload": None}
    monkeypatch.setattr(security.sb, "enabled", lambda: True)
    monkeypatch.setattr(security.sb, "verify", lambda tok: holder["payload"])
    return holder


def _call(holder, meta, path="/query", method="GET", sub="u1"):
    holder["payload"] = {"sub": sub, "user_metadata": meta}
    req = _req(path, method)
    security.require_auth(req, "Bearer x", None)
    return req


LEGACY = {"age_confirmed_18": True, "terms_version": "1.6"}
NEW = {"terms_version": "1.6"}


def _error(holder, meta, path="/query", method="GET", sub="u1"):
    with pytest.raises(HTTPException) as e:
        _call(holder, meta, path, method, sub)
    assert e.value.status_code == 403
    return e.value.detail["error"]


def test_legacy_adult_is_unaffected(sb_mode):
    req = _call(sb_mode, LEGACY, "/query", "POST")
    assert req.state.owner == "u1" and security.legacy_adult(req) is True


def test_new_account_without_age_gets_age_required(sb_mode):
    assert _error(sb_mode, NEW) == "age_required"
    assert _error(sb_mode, NEW, "/query", "POST") == "age_required"


def test_me_and_account_stay_reachable_without_an_age(sb_mode):
    _call(sb_mode, NEW, "/me")
    _call(sb_mode, NEW, "/account/age", "POST")
    _call(sb_mode, NEW, "/account/adult-terms", "POST")


def test_missing_terms_is_still_consent_required_not_age_required(sb_mode):
    assert _error(sb_mode, {}) == "consent_required"
    assert _error(sb_mode, {"age_confirmed_18": True}) == "consent_required"


def test_declaring_an_age_lifts_age_required(sb_mode):
    minors.set_age_once("u1", 2012, 5)
    _call(sb_mode, NEW)                                    # now a minor with a record: allowed
    _call(sb_mode, NEW, "/query", "POST")                  # a minor may send messages


def test_adult_terms_gate_applies_to_every_message_route_only(sb_mode):
    minors.set_age_once("u1", 2012, 5)
    db.get_conn().execute("UPDATE age_records SET adult_from='2020-01-01'")     # turned 18, not accepted
    db.get_conn().commit()
    for path in ("/query", "/query/stream", "/query/async", "/sessions", "/sessions/stream",
                 "/sessions/async", "/sessions/abc/query", "/sessions/abc/stream",
                 "/sessions/abc/query/async"):
        assert _error(sb_mode, NEW, path, "POST") == "adult_terms_required", path
    for path, method in (("/me", "GET"), ("/sessions", "GET"), ("/sessions/abc/messages", "GET"),
                         ("/sessions/abc/cancel", "POST"), ("/lessons", "GET"),
                         ("/account/adult-terms", "POST")):
        _call(sb_mode, NEW, path, method)
    minors.accept_adult_terms("u1")
    _call(sb_mode, NEW, "/query", "POST")


def test_legacy_adult_never_sees_adult_terms_required(sb_mode):
    _call(sb_mode, LEGACY, "/query", "POST")


def test_minor_cannot_buy_redeem_or_refer(sb_mode):
    minors.set_age_once("u1", 2012, 5)
    for path, method in (("/billing/checkout", "POST"), ("/coupons/redeem", "POST"),
                         ("/referral/status", "GET"), ("/referrals/status", "GET"),
                         ("/api/referral/status", "GET"), ("/referral/settings", "POST"),
                         ("/api/referral/generate", "POST"), ("/referrals/claim", "POST")):
        assert _error(sb_mode, NEW, path, method) == "minor_no_purchase", path
    for path, method in (("/billing/config", "GET"), ("/billing/limits", "GET"),
                         ("/billing/cancel", "POST"), ("/me", "GET")):
        _call(sb_mode, NEW, path, method)


def test_adults_and_legacy_accounts_can_still_buy(sb_mode):
    _call(sb_mode, LEGACY, "/billing/checkout", "POST")
    minors.set_age_once("u2", 1990, 3)
    _call(sb_mode, NEW, "/coupons/redeem", "POST", sub="u2")


def test_api_key_and_local_mode_never_gate(monkeypatch, d):
    monkeypatch.setattr(security.sb, "enabled", lambda: False)
    monkeypatch.delenv("CHAVRUTA_API_KEYS", raising=False)
    security.require_auth(_req("/query", "POST"), None, None)
    security.require_auth(_req("/billing/checkout", "POST"), None, None)


def test_age_gate_does_not_run_for_legacy_adults_database_lookup(sb_mode, monkeypatch):
    """Legacy accounts pass on the JWT alone — an unreadable age table must not lock them out of /query."""
    monkeypatch.setattr(minors, "get_age", lambda owner: (_ for _ in ()).throw(RuntimeError("db down")))
    _call(sb_mode, LEGACY, "/me")


# ── T010: endpoints ───────────────────────────────────────────────────────────
def test_account_age_endpoint_contract(d):
    import app.api as api

    out = api.set_account_age(api.AgeIn(birth_year=2012, birth_month=5), owner="u1")
    assert out["is_minor"] is True and out["adult_from"] == "2030-06-01"
    with pytest.raises(HTTPException) as e:
        api.set_account_age(api.AgeIn(birth_year=1990, birth_month=1), owner="u1")
    assert e.value.status_code == 409 and e.value.detail["error"] == "age_already_set"
    with pytest.raises(HTTPException) as e:
        api.set_account_age(api.AgeIn(birth_year=2024, birth_month=1), owner="u2")
    assert e.value.status_code == 422 and e.value.detail["error"] == "under_minimum_age"
    assert minors.get_age("u2") is None
    with pytest.raises(HTTPException) as e:
        api.set_account_age(api.AgeIn(birth_year=1990, birth_month=1), owner="local")
    assert e.value.status_code == 400


def test_adult_terms_endpoint_contract(d):
    import app.api as api

    with pytest.raises(HTTPException) as e:
        api.accept_adult_terms(api.AdultTermsIn(terms_version="1.6"), owner="nobody")
    assert e.value.status_code == 409 and e.value.detail["error"] == "age_required"
    api.set_account_age(api.AgeIn(birth_year=2012, birth_month=5), owner="u1")
    with pytest.raises(HTTPException) as e:
        api.accept_adult_terms(api.AdultTermsIn(terms_version="1.6"), owner="u1")
    assert e.value.detail["error"] == "not_adult_yet"
    db.get_conn().execute("UPDATE age_records SET adult_from='2020-01-01'")
    db.get_conn().commit()
    assert api.accept_adult_terms(api.AdultTermsIn(terms_version="1.6"), owner="u1") == {"ok": True}
    assert not minors.adult_terms_required("u1")


def test_me_reports_the_new_fields(d, monkeypatch):
    import app.api as api

    monkeypatch.setattr(api.sb, "enabled", lambda: True)
    req = types.SimpleNamespace(state=types.SimpleNamespace(age_confirmed_18=False))
    assert api.me(req, owner="fresh").age_required is True
    api.set_account_age(api.AgeIn(birth_year=2012, birth_month=5), owner="fresh")
    m = api.me(req, owner="fresh")
    assert (m.is_minor, m.age_required, m.adult_terms_required, m.school_linked) == (True, False, False, False)
    legacy = types.SimpleNamespace(state=types.SimpleNamespace(age_confirmed_18=True))
    m = api.me(legacy, owner="old")
    assert (m.is_minor, m.age_required, m.adult_terms_required) == (False, False, False)
