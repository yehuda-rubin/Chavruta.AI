"""Spec 009 T050: a minor's text reaches ONLY the preset named by CHAVRUTA_MINOR_LLM_PRESET, never the
deployment's default backend (Nebius), never a caller's key, never the admin Mistral route. With no
approved preset every generation request from a minor fails closed (503 minor_backend_unavailable) AFTER
the crisis screen, and adults behave exactly as before.

Synthetic throughout: fake pipeline whose default LLM fails the test if touched, fake provider clients, a
temporary SQLite. No network, no model.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api as api
import app.crisis_gate as gate
import app.db as db
import app.minor_llm as minor_llm
import app.minors as minors
from chavruta.corpus import audience
from chavruta.corpus.audience import AudienceScope
from chavruta.intents import llm_planner

TODAY = date(2026, 10, 26)
DISTRESS = "I want to kill myself tonight"
BENIGN = "What does Rashi say about the first verse?"


class TrapLLM:
    """The deployment's default backend. Any use at all is a failure."""

    def __getattr__(self, name):
        pytest.fail(f"the default backend was touched ({name}) for a minor")


class Env(SimpleNamespace):
    pass


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "routing.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    for var in ("CHAVRUTA_MINOR_LLM_PRESET", "CHAVRUTA_MINOR_LLM_API_KEY", "CHAVRUTA_MISTRAL_API_KEY",
                "MISTRAL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "operator")
    monkeypatch.setattr(gate, "_RETRY_DELAYS_S", (0.0,))
    monkeypatch.setattr(gate, "_spawn", lambda fn: fn())
    monkeypatch.setattr(gate, "_email_for", lambda owner_id: None)
    monkeypatch.setattr(gate, "_send", lambda *a: True)

    default_llm = TrapLLM()
    pipeline = SimpleNamespace(
        llm=default_llm,
        profile=SimpleNamespace(llm_timeout_s=5.0, llm_max_retries=0, llm_backend="nebius",
                                llm_base_url="https://api.studio.nebius.ai/v1", llm_model="m"),
        wire_source_fetcher=lambda llm: setattr(llm, "source_fetcher", "wired"),
    )
    monkeypatch.setattr(api, "_get_pipeline", lambda: pipeline)
    quota = []
    monkeypatch.setattr(api, "_enforce_quota",
                        lambda owner, lang, intent="", user_key="": quota.append(user_key) or api.Reservation(0))
    monkeypatch.setattr(api, "_settle_tokens", lambda *a, **k: None)
    monkeypatch.setattr(api, "_source_note_enabled", lambda owner: False)
    seen = {"impl": []}

    def impl(question, lang, intent_str, history, audience="", grade_band="", length="",
             owner_id="local", llm=None):
        seen["impl"].append(llm)
        return api.QueryResponse(answer="generated answer", citations=[], grounded=True, intent="qa")

    monkeypatch.setattr(api, "_run_query_impl", impl)
    return Env(default_llm=default_llm, pipeline=pipeline, quota=quota, seen=seen)


def _minor(owner="kid", consent=True):
    minors.set_age_once(owner, 2012, 5, today=TODAY)
    assert minors.is_minor(owner, TODAY)
    if consent:        # T090: these tests are about the PROVIDER, so the parent has already approved
        now = db._now()
        db.get_conn().execute(
            "INSERT INTO parental_consents (child_owner_id, parent_email, token_hash, revoke_token_hash, "
            "status, sent_at, expires_at) VALUES (?,?,?,?,'approved',?,?)",
            (owner, "p@example.com", "h-" + owner, "r-" + owner, now, now))
        db.get_conn().commit()


def _approve(monkeypatch, name="mistral-large-3", key="minor-key"):
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", name)
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_API_KEY", key)
    # No preset is approved in code today (founder decision); a test that needs one adds it explicitly.
    monkeypatch.setattr(minor_llm, "APPROVED_MINOR_PRESETS", frozenset({name.lower()}))


def _alerts():
    return [dict(r) for r in db.get_conn().execute("SELECT * FROM crisis_alerts").fetchall()]


def _drain(resp):
    async def go():
        it = resp.body_iterator
        return [c async for c in it] if hasattr(it, "__aiter__") else list(it)

    return asyncio.run(go())


# ── the shared resolution (crisis classifier + generation) ────────────────────────
@pytest.mark.parametrize("preset,key", [
    ("", "k"), ("no-such-preset", "k"), ("mistral-large-3", ""),
    ("nebius", "k"), ("deepseek-v4-pro", "k"),            # both are hosted on Nebius
])
def test_unapproved_configurations_resolve_to_nothing(monkeypatch, preset, key):
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", preset)
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_API_KEY", key)
    backend, why = minor_llm.approved_backend()
    assert backend is None and why
    assert gate._classifier_call() is None                  # the classifier asks the same question


def test_allowlist_is_empty_in_code():
    assert minor_llm.APPROVED_MINOR_PRESETS == frozenset()


@pytest.mark.parametrize("preset", ["mistral-large-3", "gemini", "gemini-flash", "deepseek-v4-pro", "nebius"])
def test_no_preset_resolves_while_the_allowlist_is_empty(monkeypatch, preset):
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", preset)
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_API_KEY", "k")
    backend, why = minor_llm.approved_backend()
    assert backend is None and "APPROVED_MINOR_PRESETS" in why or preset in ("nebius", "deepseek-v4-pro")
    assert backend is None
    assert gate._classifier_call() is None


def test_nebius_guard_holds_even_if_allowlisted(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_PRESET", "deepseek-v4-pro")      # hosted on Nebius
    monkeypatch.setenv("CHAVRUTA_MINOR_LLM_API_KEY", "k")
    monkeypatch.setattr(minor_llm, "APPROVED_MINOR_PRESETS", frozenset({"deepseek-v4-pro"}))
    backend, why = minor_llm.approved_backend()
    assert backend is None and "not approved" in why


def test_approved_preset_resolves(monkeypatch):
    _approve(monkeypatch)
    backend, why = minor_llm.approved_backend()
    assert (backend.model, backend.base_url, backend.api_key) == (
        "mistral-large-2512", "https://api.mistral.ai/v1", "minor-key") and why == ""


# ── resolve: who gets which LLM ───────────────────────────────────────────────────
def test_minor_without_preset_gets_the_marker_not_the_default(env):
    _minor()
    res, llm, meter = api._resolve_llm_for_request("kid", "he", "qa", None)
    assert isinstance(llm, api._MinorBackendUnavailable) and llm is not env.default_llm
    assert meter == db.TOKENS


def test_minor_with_preset_gets_a_client_on_that_preset(env, monkeypatch):
    _minor()
    _approve(monkeypatch)
    _res, llm, _meter = api._resolve_llm_for_request("kid", "he", "qa", None)
    assert llm is not env.default_llm
    assert (llm.model_id, llm.base_url) == ("mistral-large-2512", "https://api.mistral.ai/v1") or \
        "mistral" in repr(vars(llm)).lower()
    assert llm.source_fetcher == "wired"                    # the agentic loop can retrieve


def test_minor_cannot_use_byok_headers_or_presets(env, monkeypatch):
    _minor()
    monkeypatch.setattr(api, "_byok_llm", lambda *a, **k: pytest.fail("BYOK reached for a minor"))
    _res, llm, _m = api._resolve_llm_for_request("kid", "he", "qa", "their-own-key",
                                                 "https://evil.example/v1", "any-model", "mistral-large-3")
    assert isinstance(llm, api._MinorBackendUnavailable)
    assert env.quota == [""]                                # the key never reached the quota/BYOK meter


def test_admin_mistral_route_does_not_apply_to_a_minor(env, monkeypatch):
    minors.set_age_once("operator", 2012, 5, today=TODAY)   # an admin account that is also a minor
    monkeypatch.setenv("CHAVRUTA_MISTRAL_API_KEY", "mistral-key")
    _res, llm, _m = api._resolve_llm_for_request("operator", "he", "qa", None)
    assert isinstance(llm, api._MinorBackendUnavailable)


def test_adult_resolution_is_unchanged(env, monkeypatch):
    res, llm, meter = api._resolve_llm_for_request("grownup", "he", "qa", None)
    assert llm is None and meter == db.TOKENS               # the pipeline's own backend, as before
    _approve(monkeypatch)                                   # a minor preset changes nothing for adults
    assert api._resolve_llm_for_request("grownup", "he", "qa", None)[1] is None
    assert api._resolve_llm_for_request("local", "he", "qa", None)[1] is None


# ── _run_query: crisis first, then 503 / the right client ─────────────────────────
def test_run_query_minor_without_backend_is_503_and_generates_nothing(env):
    _minor()
    llm = api._MinorBackendUnavailable(lang="he")
    with pytest.raises(HTTPException) as ei:
        api._run_query(BENIGN, "he", "qa", [], owner_id="kid", llm=llm)
    assert ei.value.status_code == 503
    assert ei.value.detail["error"] == "minor_backend_unavailable" and ei.value.detail["message"]
    assert env.seen["impl"] == []


def test_distress_still_gets_the_crisis_reply_when_generation_is_unavailable(env):
    _minor()
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="kid",
                          llm=api._MinorBackendUnavailable(lang="en"))
    assert resp.crisis and resp.crisis["kind"] == "crisis"
    assert env.seen["impl"] == [] and len(_alerts()) == 1


def test_run_query_backstop_for_a_caller_that_passed_no_llm(env, monkeypatch):
    _minor()
    with pytest.raises(HTTPException) as ei:                # llm=None would mean "the default backend"
        api._run_query(BENIGN, "he", "qa", [], owner_id="kid")
    assert ei.value.detail["error"] == "minor_backend_unavailable" and env.seen["impl"] == []
    _approve(monkeypatch)
    api._run_query(BENIGN, "he", "qa", [], owner_id="kid")
    got = env.seen["impl"][0]
    assert got is not None and got is not env.default_llm


def test_run_query_adult_passes_llm_through_untouched(env):
    sentinel = object()
    api._run_query(BENIGN, "he", "qa", [], owner_id="grownup", llm=sentinel)
    api._run_query(BENIGN, "he", "qa", [], owner_id="grownup")
    assert env.seen["impl"] == [sentinel, None]


# ── the routes ────────────────────────────────────────────────────────────────────
def test_sync_query_route_is_503_for_a_minor(env):
    _minor()
    with pytest.raises(HTTPException) as ei:
        api.query(api.QueryRequest(question=BENIGN, lang="he"), owner="kid")
    assert ei.value.status_code == 503 and ei.value.detail["error"] == "minor_backend_unavailable"
    assert env.seen["impl"] == []


def test_sync_query_route_crisis_still_answers(env):
    _minor()
    out = api.query(api.QueryRequest(question=DISTRESS, lang="en"), owner="kid")
    assert out.crisis and env.seen["impl"] == []


def test_sync_query_route_uses_the_minor_client(env, monkeypatch):
    _minor()
    _approve(monkeypatch)
    api.query(api.QueryRequest(question=BENIGN, lang="he"), owner="kid")
    got = env.seen["impl"][0]
    assert got is not None and got is not env.default_llm


def test_session_sync_routes_are_503_and_a_failed_first_turn_leaves_no_session(env):
    _minor()
    with pytest.raises(HTTPException) as ei:
        api.create_session(api.QueryRequest(question=BENIGN, lang="he"), owner="kid")
    assert ei.value.status_code == 503
    assert db.get_conn().execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_async_routes_are_503_at_submit_and_queue_nothing(env, monkeypatch):
    _minor()
    monkeypatch.setattr(api.jobs, "submit", lambda *a, **k: pytest.fail("a job was queued"))
    sid = db.create_session(BENIGN, mode="qa", owner_id="kid")
    db.save_message(sid, "user", BENIGN)
    req = api.QueryRequest(question=BENIGN, lang="he")
    for call in (lambda: api.query_async(req, owner="kid"),
                 lambda: api.create_session_async(req, owner="kid"),
                 lambda: api.session_query_async(sid, req, owner="kid")):
        with pytest.raises(HTTPException) as ei:
            call()
        assert ei.value.status_code == 503 and ei.value.detail["error"] == "minor_backend_unavailable"


def test_async_distress_is_queued_and_answered_by_the_crisis_gate_once(env, monkeypatch):
    _minor()
    queued = []
    monkeypatch.setattr(api.jobs, "submit", lambda owner, fn, **k: queued.append(fn) or "job1")
    out = api.query_async(api.QueryRequest(question=DISTRESS, lang="en"), owner="kid")
    assert out.job_id == "job1" and len(queued) == 1
    result = queued[0]()
    assert result["crisis"]["kind"] == "crisis" and env.seen["impl"] == []
    assert len(_alerts()) == 1                              # screened at submit, not again in the worker


def test_stream_route_emits_one_error_event_then_ends(env):
    _minor()
    events = _drain(api.query_stream(api.QueryRequest(question=BENIGN, lang="he"), owner="kid"))
    assert len(events) == 1 and events[0].startswith("event: error")
    assert json.loads(events[0].split("data: ", 1)[1])["error"] == "minor_backend_unavailable"


def test_stream_route_distress_still_gets_the_crisis_event(env):
    _minor()
    events = _drain(api.query_stream(api.QueryRequest(question=DISTRESS, lang="en"), owner="kid"))
    assert len(events) == 1 and json.loads(events[0].split("data: ", 1)[1])["crisis"]["kind"] == "crisis"


def test_session_stream_one_error_event_then_ends(env):
    _minor()
    sid = db.create_session(BENIGN, mode="qa", owner_id="kid")
    db.save_message(sid, "user", BENIGN)
    req = api.QueryRequest(question=BENIGN, lang="he")
    events = _drain(api.session_query_stream(sid, req, owner="kid"))
    assert len(events) == 1 and events[0].startswith("event: error")
    events = _drain(api.session_create_stream(req, owner="kid"))
    assert len(events) == 1 and events[0].startswith("event: error")


# ── the helper calls that build their own client from the default provider ────────
class _Boom:
    def __init__(self, *a, **k):
        pytest.fail("a client on the default provider was built for a minor")


def test_distiller_and_followup_classifier_never_use_the_default_provider_for_a_minor(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_LLM_API_KEY", "default-key")
    monkeypatch.setattr("openai.OpenAI", _Boom)
    long_q = "please explain at length the relationship between these two opinions " * 3
    with audience.use(AudienceScope(minor=True)):
        res = llm_planner.classify_and_distill(long_q, intent="qa")
        assert res.action == "study"
        dec = llm_planner.classify_lesson_followup("שנה את מהלך השיעור", last_lesson_topic="x")
        assert dec.action in ("chat", "edit_file", "rebuild_all")
        assert llm_planner.LLMQueryPlanner("m", "https://x", "k").plan("anything") == {
            "refs": [], "commentators": [], "intent": None}


def test_distiller_for_an_adult_still_builds_the_default_client(monkeypatch):
    built = []

    class Fake:
        def __init__(self, *a, **k):
            built.append(1)
            raise RuntimeError("stop")                      # the planner swallows this: study result

    monkeypatch.setenv("CHAVRUTA_LLM_API_KEY", "default-key")
    monkeypatch.setattr("openai.OpenAI", Fake)
    long_q = "please explain at length the relationship between these two opinions " * 3
    llm_planner.classify_and_distill(long_q, intent="qa")
    assert built == [1]


def test_wants_full_lesson_never_calls_the_default_classifier_for_a_minor(env, monkeypatch):
    monkeypatch.setattr(api, "_classifier_llm", lambda: pytest.fail("default classifier reached"))
    with audience.use(AudienceScope(minor=True)):
        assert api._wants_full_lesson("תבנה לי שיעור על הפרשה") is False
        yes = SimpleNamespace(generate=lambda *a, **k: SimpleNamespace(text="כן"))
        assert api._wants_full_lesson("תבנה לי שיעור על הפרשה", llm=yes) is True
    assert api._minor_only("x") is None                     # adult scope: the caller's llm is dropped
    with audience.use(AudienceScope(minor=True)):
        assert api._minor_only("x") == "x"


def test_session_stream_distiller_runs_under_the_minor_scope(env, monkeypatch):
    """The distiller call in the session stream sits outside _run_query, so it must set the scope itself."""
    _minor()
    _approve(monkeypatch)
    seen = []
    monkeypatch.setattr(api, "classify_and_distill",
                        lambda *a, **k: seen.append(audience.current().minor) or
                        SimpleNamespace(action="chitchat", answer="hi", distilled_query="", requested_files=[]))
    sid = db.create_session(BENIGN, mode="qa", owner_id="kid")
    db.save_message(sid, "user", BENIGN)
    list(api._stream_query_generator(sid, api.QueryRequest(question=BENIGN, lang="he"), [], "qa", "kid",
                                     None, api._build_minor_llm(), db.TOKENS))
    assert seen == [True]
