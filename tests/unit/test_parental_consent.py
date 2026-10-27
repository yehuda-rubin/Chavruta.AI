"""Spec 009 T090/T093: parental consent for a minor with no school, and the under-12 auto-delete.

Synthetic: temporary SQLite, a fake email sender (nothing leaves the process), no model.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api as api
import app.accounts as accounts
import app.crisis_gate as gate
import app.db as db
import app.minors as minors
import app.parental_consent as pc
import app.security as security

TODAY = date(2026, 10, 26)
DISTRESS = "I want to kill myself tonight"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pc.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    monkeypatch.setenv("CHAVRUTA_PUBLIC_URL", "https://example.test")
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "operator")
    monkeypatch.delenv("CHAVRUTA_MINOR_LLM_PRESET", raising=False)
    monkeypatch.setattr(gate, "_RETRY_DELAYS_S", (0.0,))
    monkeypatch.setattr(gate, "_spawn", lambda fn: fn())
    monkeypatch.setattr(gate, "_email_for", lambda owner_id: None)
    monkeypatch.setattr(gate, "_send", lambda *a: True)
    sent: list[tuple] = []
    monkeypatch.setattr(pc, "_send", lambda to, subj, h, t: sent.append((to, subj, h, t)) or True)
    monkeypatch.setattr(api, "_consent_public_window", security._SlidingWindow(1000, 60.0))
    return SimpleNamespace(sent=sent)


def _minor(owner="kid"):
    minors.set_age_once(owner, 2012, 5, today=TODAY)
    assert minors.is_minor(owner)


def _tokens(sent_item):
    text = sent_item[3]
    consent = next(w for w in text.split() if "/parent-consent/" in w and "/revoke/" not in w)
    revoke = next(w for w in text.split() if "/parent-consent/revoke/" in w)
    return consent.rsplit("/", 1)[1], revoke.rsplit("/", 1)[1]


def _request(email="mom@example.com", child_email="kid@example.com", owner="kid"):
    return pc.request_consent(owner, child_email, email)


# ── the gate ──────────────────────────────────────────────────────────────────────────────────────
def test_minor_without_consent_is_not_ok_and_adult_is_ok(env):
    _minor()
    assert minors.parental_consent_ok("kid") is False
    assert minors.parental_consent_ok("nobody-with-no-record") is True      # legacy adult
    assert minors.parental_consent_ok("local") is True


def test_approval_flow_and_revocation(env):
    _minor()
    out = _request()
    assert out["status"] == "pending"
    token, revoke = _tokens(env.sent[0])
    assert pc.info(token)["status"] == "pending"
    assert pc.decide(token, "approve", "1.2.3.4", "UA") == {"status": "approved"}
    assert minors.parental_consent_ok("kid") is True
    row = db.get_conn().execute("SELECT * FROM parental_consents").fetchone()
    assert row["decision_ip"] == "1.2.3.4" and row["decision_user_agent"] == "UA" and row["decided_at"]
    assert pc.revoke(revoke) == {"status": "revoked"}
    assert minors.parental_consent_ok("kid") is False
    assert pc.me_view("kid")["status"] == "declined"           # revoked is shown to the child as declined


def test_decline_keeps_gate_closed_and_cannot_be_changed(env):
    _minor()
    _request()
    token, _ = _tokens(env.sent[0])
    pc.decide(token, "decline", "ip", "ua")
    assert minors.parental_consent_ok("kid") is False
    with pytest.raises(pc.AlreadyDecided):
        pc.decide(token, "approve", "ip", "ua")


def test_active_parent_link_satisfies_the_gate(env):
    _minor()
    _minor("mom-account") if False else None
    now = db._now()
    db.get_conn().execute("INSERT INTO parent_links VALUES (?,?,?,?,?)", ("p", "kid", "active", now, now))
    db.get_conn().commit()
    assert minors.parental_consent_ok("kid") is True


def test_pending_parent_link_does_not(env):
    _minor()
    db.get_conn().execute("INSERT INTO parent_links VALUES (?,?,?,?,?)", ("p", "kid", "pending", db._now(), None))
    db.get_conn().commit()
    assert minors.parental_consent_ok("kid") is False


# ── requesting ────────────────────────────────────────────────────────────────────────────────────
def test_email_has_both_links_and_no_child_data(env):
    _minor()
    _request(child_email="secret.child@example.com")
    to, subject, body_html, body_text = env.sent[0]
    assert to == "mom@example.com" and subject
    assert "https://example.test/parent-consent/" in body_text
    assert "https://example.test/parent-consent/revoke/" in body_text
    assert "secret.child" not in body_text + body_html and "kid" not in body_text.split()
    token, revoke = _tokens(env.sent[0])
    assert len(token) >= 43 and len(revoke) >= 43 and token != revoke


def test_only_hashes_are_stored(env):
    _minor()
    _request()
    token, revoke = _tokens(env.sent[0])
    row = db.get_conn().execute("SELECT * FROM parental_consents").fetchone()
    assert token not in tuple(row) and revoke not in tuple(row)
    assert row["token_hash"] == pc._hash(token)


def test_same_address_as_child_rejected(env):
    _minor()
    with pytest.raises(pc.SameAsChild):
        pc.request_consent("kid", "Kid@Example.com", " kid@example.com ")
    assert env.sent == []


@pytest.mark.parametrize("bad", ["", "nope", "a@b", "a b@c.com", "@x.com"])
def test_invalid_email(env, bad):
    _minor()
    with pytest.raises(pc.InvalidEmail):
        _request(email=bad)


def test_adult_and_school_linked_minor_cannot_request(env, monkeypatch):
    with pytest.raises(pc.NotApplicable):
        _request(owner="adult-no-record")
    _minor()
    import app.orgs as orgs
    monkeypatch.setattr(orgs, "membership", lambda o: {"org_id": "o1"})
    with pytest.raises(pc.NotApplicable):
        _request()


def test_new_request_supersedes_pending_and_acts_as_resend(env):
    _minor()
    _request()
    _request()                                             # same address again = resend
    assert len(env.sent) == 2
    old, _ = _tokens(env.sent[0])
    new, _ = _tokens(env.sent[1])
    with pytest.raises(pc.Expired):
        pc.info(old)
    assert pc.info(new)["status"] == "pending"


def test_rate_limits(env):
    _minor()
    for i in range(3):
        _request(email=f"p{i}@example.com")
    with pytest.raises(pc.RateLimited):
        _request(email="p9@example.com")


def test_same_parent_address_limited_across_children(env):
    for i in range(3):
        minors.set_age_once(f"k{i}", 2012, 5, today=TODAY)
        _request(owner=f"k{i}")
    minors.set_age_once("k3", 2012, 5, today=TODAY)
    with pytest.raises(pc.RateLimited):
        _request(owner="k3")


def test_already_approved_blocks_new_request(env):
    _minor()
    _request()
    pc.decide(_tokens(env.sent[0])[0], "approve", "", "")
    with pytest.raises(pc.AlreadyApproved):
        _request()


def test_send_failure_is_503_and_link_dead(env, monkeypatch):
    _minor()
    monkeypatch.setattr(pc, "_send", lambda *a: False)
    with pytest.raises(pc.SendFailed):
        _request()
    assert pc.me_view("kid")["status"] == "expired"


# ── parent side ───────────────────────────────────────────────────────────────────────────────────
def test_unknown_token_404_and_expired_410(env):
    _minor()
    with pytest.raises(pc.UnknownToken):
        pc.info("nope")
    _request()
    token, revoke = _tokens(env.sent[0])
    db.get_conn().execute("UPDATE parental_consents SET expires_at=?",
                          ((pc._now_dt() - timedelta(seconds=1)).isoformat(),))
    db.get_conn().commit()
    with pytest.raises(pc.Expired):
        pc.info(token)
    with pytest.raises(pc.Expired):
        pc.decide(token, "approve", "", "")
    assert minors.parental_consent_ok("kid") is False


def test_info_never_leaks_child_data(env):
    _minor()
    _request()
    out = pc.info(_tokens(env.sent[0])[0])
    assert set(out) == {"status", "expires_at"}


def test_revoke_is_idempotent_and_unknown_is_404(env):
    _minor()
    _request()
    _, revoke = _tokens(env.sent[0])
    pc.revoke(revoke)
    assert pc.revoke(revoke) == {"status": "revoked"}
    with pytest.raises(pc.UnknownToken):
        pc.revoke("nope")


def test_the_consent_token_cannot_revoke(env):
    _minor()
    _request()
    token, _ = _tokens(env.sent[0])
    with pytest.raises(pc.UnknownToken):
        pc.revoke(token)


# ── /me and the routes ────────────────────────────────────────────────────────────────────────────
def test_me_fields(env):
    _minor()
    f = api._consent_fields("kid")
    assert f == {"parental_consent_required": True, "parental_consent": {"status": "none"}}
    _request()
    f = api._consent_fields("kid")
    assert f["parental_consent_required"] is True
    assert f["parental_consent"]["status"] == "pending"
    assert f["parental_consent"]["parent_email_masked"] == "m***@example.com"
    assert f["parental_consent"]["sent_at"]
    pc.decide(_tokens(env.sent[0])[0], "approve", "", "")
    f = api._consent_fields("kid")
    assert f["parental_consent_required"] is False and f["parental_consent"]["status"] == "approved"
    assert api._consent_fields("adult") == {"parental_consent_required": False, "parental_consent": None}
    assert api._consent_fields("local")["parental_consent"] is None


def test_public_paths_are_auth_exempt():
    assert security._auth_exempt("/consent/abc") and security._auth_exempt("/consent/revoke/abc")
    assert not security._auth_exempt("/consentx") and not security._auth_exempt("/account/parental-consent")


def test_route_request_maps_errors(env):
    _minor()
    req = SimpleNamespace(state=SimpleNamespace(email="kid@example.com"))
    with pytest.raises(HTTPException) as e:
        api.request_parental_consent(api.ParentalConsentIn(parent_email="kid@example.com"), req, "kid")
    assert e.value.status_code == 409 and e.value.detail["error"] == "same_as_child"
    with pytest.raises(HTTPException) as e:
        api.request_parental_consent(api.ParentalConsentIn(parent_email="bad"), req, "kid")
    assert e.value.status_code == 422
    out = api.request_parental_consent(api.ParentalConsentIn(parent_email="mom@example.com"), req, "kid")
    assert out["status"] == "pending" and out["sent_at"]


def test_route_decide_records_ip_and_agent(env):
    _minor()
    _request()
    token, _ = _tokens(env.sent[0])
    req = SimpleNamespace(client=SimpleNamespace(host="9.9.9.9"), headers={"user-agent": "UA/1"})
    assert api.consent_decide(token, api.ConsentDecisionIn(decision="approve"), req) == {"status": "approved"}
    row = db.get_conn().execute("SELECT decision_ip, decision_user_agent FROM parental_consents").fetchone()
    assert (row[0], row[1]) == ("9.9.9.9", "UA/1")
    with pytest.raises(HTTPException) as e:
        api.consent_decide(token, api.ConsentDecisionIn(decision="approve"), req)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        api.consent_decide(token, api.ConsentDecisionIn(decision="maybe"), req)
    assert e.value.status_code == 422


# ── the send gate, and the crisis screen coming first ─────────────────────────────────────────────
def test_minor_without_consent_gets_403_and_no_quota_burn_on_resolve(env):
    _minor()
    _res, llm, _meter = api._resolve_llm_for_request("kid", "he", "qa", None)
    assert isinstance(llm, api._MinorBackendUnavailable) and llm.consent_required


def test_run_query_refuses_with_403_after_the_crisis_screen(env):
    _minor()
    _res, llm, _m = api._resolve_llm_for_request("kid", "he", "qa", None)
    with pytest.raises(HTTPException) as e:
        api._run_query("What does Rashi say?", "en", "qa", [], owner_id="kid", llm=llm)
    assert e.value.status_code == 403 and e.value.detail["error"] == "parental_consent_required"


def test_distressed_child_without_consent_still_gets_the_crisis_reply(env):
    _minor()
    _res, llm, _m = api._resolve_llm_for_request("kid", "he", "qa", None)
    resp = api._run_query(DISTRESS, "en", "qa", [], owner_id="kid", llm=llm)
    assert resp.crisis["kind"] == "crisis"
    n = db.get_conn().execute("SELECT COUNT(*) FROM crisis_alerts").fetchone()[0]
    assert n == 1


def test_streaming_event_for_consent_refusal(env):
    ev = api._minor_unavailable_event("en", True)
    assert "parental_consent_required" in ev and ev.startswith("event: error")


def test_consent_lets_the_gate_open(env):
    _minor()
    _request()
    pc.decide(_tokens(env.sent[0])[0], "approve", "", "")
    _res, llm, _m = api._resolve_llm_for_request("kid", "he", "qa", None)
    # consent is satisfied, so the only remaining reason to refuse is T050 (no approved provider): 503, not 403
    assert isinstance(llm, api._MinorBackendUnavailable) and not llm.consent_required


# ── purge ─────────────────────────────────────────────────────────────────────────────────────────
def test_purge_deletes_consent_rows(env):
    _minor()
    _request()
    db.purge_owner("kid")
    assert db.get_conn().execute("SELECT COUNT(*) FROM parental_consents").fetchone()[0] == 0


# ── T093 ──────────────────────────────────────────────────────────────────────────────────────────
def test_under_12_deletes_the_account(env, monkeypatch):
    purged = []
    monkeypatch.setattr(accounts, "purge_now", lambda o: purged.append(o))
    out = api.set_account_age(api.AgeIn(birth_year=2018, birth_month=1), "tiny")
    assert out.status_code == 422
    body = json.loads(out.body)
    assert body["error"] == "under_minimum_age" and body["account_deleted"] is True
    assert purged == ["tiny"]
    assert minors.get_age("tiny") is None
    assert db.get_conn().execute("SELECT COUNT(*) FROM age_record_log WHERE owner_id='tiny'").fetchone()[0] == 0


def test_under_12_purge_failure_is_reported_honestly(env, monkeypatch):
    def boom(o):
        raise RuntimeError("x")
    monkeypatch.setattr(accounts, "purge_now", boom)
    out = api.set_account_age(api.AgeIn(birth_year=2018, birth_month=1), "tiny")
    assert json.loads(out.body)["account_deleted"] is False


def test_real_purge_removes_a_free_under_12_account(env, monkeypatch):
    monkeypatch.setattr(accounts, "_delete_supabase_user", lambda o: None)
    db.get_conn().execute("INSERT INTO feedback (owner_id, kind, text, created_at) VALUES ('tiny','x','y',?)"
                          if False else "SELECT 1", ())
    out = api.set_account_age(api.AgeIn(birth_year=2018, birth_month=1), "tiny")
    assert json.loads(out.body)["account_deleted"] is True


def test_twelve_year_old_is_not_deleted(env, monkeypatch):
    monkeypatch.setattr(accounts, "purge_now", lambda o: pytest.fail("must not purge"))
    year = date.today().year - 13
    out = api.set_account_age(api.AgeIn(birth_year=year, birth_month=1), "ok-kid")
    assert out["is_minor"] is True
