"""Spec 009 T051: the crisis gate in front of generation, for minors only.

Synthetic throughout: fake LLM callables, a fake email sender, a temporary SQLite. No network, no real
email, no model. Generation is replaced by a stub that counts calls.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

import app.api as api
import app.crisis as crisis
import app.crisis_gate as gate
import app.db as db
import app.minors as minors
import app.orgs as orgs

TODAY = date(2026, 10, 26)
DISTRESS = "I want to kill myself tonight"
BENIGN = "What is the halacha about the death penalty in the Torah?"


class _Env:
    def __init__(self):
        self.sent: list[tuple[str, str, str, str]] = []
        self.calls = {"impl": 0}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "crisis.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "operator")
    monkeypatch.delenv("CHAVRUTA_MINOR_LLM_PRESET", raising=False)
    monkeypatch.delenv("CHAVRUTA_MINOR_LLM_API_KEY", raising=False)
    monkeypatch.setattr(gate, "_RETRY_DELAYS_S", (0.0, 0.0))
    monkeypatch.setattr(gate, "_spawn", lambda fn: fn())      # run the "background" delivery inline
    e = _Env()
    emails = {"operator": "op@example.org", "teacher": "t@example.org"}
    monkeypatch.setattr(gate, "_email_for", lambda owner_id: emails.get(owner_id))
    monkeypatch.setattr(gate, "_send", lambda to, subject, body_html, body_text:
                        e.sent.append((to, subject, body_html, body_text)) or True)

    def impl(*a, **k):
        e.calls["impl"] += 1
        return api.QueryResponse(answer="generated answer", citations=[], grounded=True, intent="qa")

    monkeypatch.setattr(api, "_run_query_impl", impl)
    monkeypatch.setattr(api, "_source_note_enabled", lambda owner: False)
    return e


def _minor(owner="kid"):
    # Born May 2012 -> adult_from 2030-06-01: a minor today. Written directly so the test does not
    # depend on the wall clock for the minimum-age check.
    minors.set_age_once(owner, 2012, 5, today=TODAY)
    assert minors.is_minor(owner, TODAY)


def _school_with_kid():
    oid = orgs.create_org("principal", "school", "school")
    conn = db.get_conn()
    for who, role in (("teacher", orgs.TEACHER), ("kid", orgs.STUDENT)):
        conn.execute("INSERT INTO org_members (org_id, owner_id, role, invited_at, accepted_at) "
                     "VALUES (?,?,?,?,?)", (oid, who, role, db._now(), db._now()))
    conn.commit()
    assert orgs.set_safety_contacts(oid, ["teacher"]) == ["teacher"]
    return oid


def _alerts():
    return [dict(r) for r in db.get_conn().execute("SELECT * FROM crisis_alerts").fetchall()]


# ── adults ────────────────────────────────────────────────────────────────────
def test_adult_is_never_screened(env, monkeypatch):
    monkeypatch.setattr(crisis, "check", lambda *a, **k: pytest.fail("an adult's text was screened"))
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="grownup")
    assert resp.answer == "generated answer" and resp.crisis is None
    assert env.calls["impl"] == 1 and env.sent == [] and _alerts() == []


def test_local_user_is_never_screened(env):
    assert gate.screen_message("local", DISTRESS, "en") is None


# ── minors: positive ──────────────────────────────────────────────────────────
def test_minor_distress_gets_crisis_payload_and_no_generation(env):
    oid = _school_with_kid()
    _minor()
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="kid")
    assert env.calls["impl"] == 0                      # nothing generated
    assert resp.crisis and resp.crisis["kind"] == "crisis" and resp.crisis["category"] == "suicide"
    assert resp.answer == resp.crisis["message"] and resp.citations == [] and resp.grounded is False
    assert resp.crisis["contacts"]
    rows = _alerts()
    assert len(rows) == 1 and rows[0]["org_id"] == oid and rows[0]["owner_id"] == "kid"
    assert rows[0]["delivered_at"]
    assert not any(isinstance(v, str) and "kill" in v for v in rows[0].values())   # no text in the row
    assert sorted(s[0] for s in env.sent) == ["op@example.org", "t@example.org"]
    for _to, subject, body_html, body_text in env.sent:
        blob = subject + body_html + body_text
        assert "kid" in blob and "kill" not in blob and "2012" not in blob


def test_unlinked_minor_alerts_operator_only(env):
    _minor()
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="kid")
    assert resp.crisis and env.calls["impl"] == 0
    assert _alerts()[0]["org_id"] is None
    assert [s[0] for s in env.sent] == ["op@example.org"]


def test_failed_send_is_retried_and_never_raises(env, monkeypatch):
    _minor()
    attempts = []

    def flaky(to, subject, html, text):
        attempts.append(to)
        if len(attempts) == 1:
            raise RuntimeError("smtp down")
        return True

    monkeypatch.setattr(gate, "_send", flaky)
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="kid")
    assert resp.crisis and len(attempts) == 2 and _alerts()[0]["delivered_at"]


def test_undeliverable_alert_leaves_delivered_at_empty(env, monkeypatch):
    _minor()
    monkeypatch.setattr(gate, "_send", lambda *a: False)
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="kid")
    assert resp.crisis and _alerts()[0]["delivered_at"] is None


def test_attached_sources_are_not_screened(env):
    _minor()
    q = BENIGN + "\n\n## Sources the user attached (not from the corpus)\n" + DISTRESS
    assert gate.screen_message("kid", q, "en") is None


# ── minors: classifier stage ──────────────────────────────────────────────────
def test_classifier_disabled_phrase_layer_still_works(env):
    _minor()
    assert gate._classifier_call() is None
    assert gate.screen_message("kid", DISTRESS, "en")["kind"] == "crisis"
    assert gate.screen_message("kid", BENIGN, "en") is None


def test_nebius_preset_is_refused_for_minors(env, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", "nebius")
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_API_KEY", "x")
    assert gate._classifier_call() is None


def test_unknown_or_keyless_preset_means_no_classifier(env, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", "no-such-preset")
    assert gate._classifier_call() is None
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", "mistral-large-3")
    assert gate._classifier_call() is None            # no CHAVRUTA_MINOR_LLM_API_KEY


def test_classifier_positive_triggers_crisis(env, monkeypatch):
    _minor()
    monkeypatch.setattr(gate, "_classifier_call",
                        lambda: (lambda p: '{"category": "abuse", "immediate_danger": false}'))
    resp = api._run_query("an indirect wording with no listed phrase", "en", "qa", [], owner_id="kid")
    assert resp.crisis["category"] == "abuse" and env.calls["impl"] == 0
    assert _alerts()[0]["detector"] == "classifier"


def test_classifier_error_answers_normally_and_logs_without_text(env, monkeypatch, caplog):
    _minor()

    def boom(prompt):
        raise RuntimeError("provider down")

    monkeypatch.setattr(gate, "_classifier_call", lambda: boom)
    secret = "an ordinary question about shabbat candles"
    with caplog.at_level("WARNING", logger="chavruta.crisis"):
        resp = api._run_query(secret, "en", "qa", [], owner_id="kid")
    assert resp.crisis is None and resp.answer == "generated answer" and env.calls["impl"] == 1
    assert _alerts() == [] and env.sent == []
    assert crisis.SCREEN_UNAVAILABLE_TAG in caplog.text and "shabbat" not in caplog.text


def test_benign_sensitive_study_question_gets_a_normal_answer(env, monkeypatch):
    _minor()
    monkeypatch.setattr(gate, "_classifier_call", lambda: (lambda p: '{"category": null}'))
    resp = api._run_query(BENIGN, "en", "qa", [], owner_id="kid")
    assert resp.crisis is None and resp.answer == "generated answer"
    assert _alerts() == [] and env.sent == []


def test_gate_failure_never_blocks_the_request(env, monkeypatch):
    _minor()
    monkeypatch.setattr(crisis, "check", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bug")))
    resp = api._run_query(BENIGN, "en", "qa", [], owner_id="kid")
    assert resp.crisis is None and resp.answer == "generated answer"


# ── history + streaming routes ────────────────────────────────────────────────
def test_session_route_saves_the_fixed_message_as_assistant_turn(env):
    _minor()
    sid = db.create_session(DISTRESS, mode="qa", owner_id="kid")
    db.save_message(sid, "user", DISTRESS)
    req = api.QueryRequest(question=DISTRESS, lang="en")
    out = api._continue_query_work(sid, req, [], "qa", "kid")
    msgs = db.get_messages(sid, "kid")
    assert out.crisis and msgs[-1]["role"] == "assistant" and msgs[-1]["text"] == out.crisis["message"]
    assert msgs[0]["text"] == DISTRESS and env.calls["impl"] == 0


def test_session_stream_emits_one_event_and_ends(env, monkeypatch):
    _minor()
    monkeypatch.setattr(api, "_settle_tokens", lambda *a, **k: None)
    monkeypatch.setattr(api, "_get_pipeline", lambda: pytest.fail("pipeline touched"))
    sid = db.create_session(DISTRESS, mode="qa", owner_id="kid")
    db.save_message(sid, "user", DISTRESS)
    req = api.QueryRequest(question=DISTRESS, lang="en")
    events = list(api._stream_query_generator(sid, req, [], "qa", "kid", None, None, db.TOKENS))
    assert len(events) == 1 and events[0].startswith("event: done")
    data = json.loads(events[0].split("data: ", 1)[1])
    assert data["crisis"]["kind"] == "crisis" and data["session_id"] == sid
    assert db.get_messages(sid, "kid")[-1]["text"] == data["answer"]
    assert len(_alerts()) == 1


def test_stateless_stream_emits_one_event_and_ends(env, monkeypatch):
    _minor()
    monkeypatch.setattr(api, "_settle_tokens", lambda *a, **k: None)
    monkeypatch.setattr(api, "_get_pipeline", lambda: pytest.fail("pipeline touched"))
    monkeypatch.setattr(api, "_resolve_llm_for_request", lambda *a, **k: (None, None, db.TOKENS))
    resp = api.query_stream(api.QueryRequest(question=DISTRESS, lang="en"), owner="kid")

    async def drain():
        it = resp.body_iterator
        if hasattr(it, "__aiter__"):
            return [c async for c in it]
        return list(it)

    events = asyncio.run(drain())
    assert len(events) == 1 and json.loads(events[0].split("data: ", 1)[1])["crisis"]["kind"] == "crisis"


def test_stream_adult_is_unchanged(env, monkeypatch):
    monkeypatch.setattr(api, "_settle_tokens", lambda *a, **k: None)
    seen = []

    def reached():
        seen.append(1)
        raise RuntimeError("stop here: the adult reached the pipeline")

    monkeypatch.setattr(api, "_get_pipeline", reached)
    sid = db.create_session(DISTRESS, mode="qa", owner_id="grownup")
    req = api.QueryRequest(question=DISTRESS, lang="en")
    with pytest.raises(RuntimeError):
        list(api._stream_query_generator(sid, req, [], "qa", "grownup", None, None, db.TOKENS))
    assert seen == [1] and _alerts() == []
