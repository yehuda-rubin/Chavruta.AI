"""End-to-end HTTP test of the public-hosting stack — the real ASGI app, middleware, auth dependency,
job queue, and SQLite persistence — with ONLY generation stubbed (no bge-m3 / Qdrant / LLM).

This exercises what the unit tests can't: the async submit→202→poll→done flow over a real client, the
app-wide auth gate, and owner isolation through actual HTTP headers. Generation is replaced with a
canned QueryResponse that echoes the owner, so a leak across owners would show up in the answer text.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.db as db


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Real SQLite, but a throwaway file — so owner scoping is tested for real without touching dev data.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)

    # Stub the heavy bits the lifespan/pipeline would otherwise load.
    monkeypatch.setattr(api, "_assert_config_usable", lambda: None)
    fake_pipeline = SimpleNamespace(
        embedding=SimpleNamespace(embed_query=lambda q: SimpleNamespace(dense=[0.0], sparse={})))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake_pipeline)

    # Generation echoes the owner so any cross-owner leak is visible in the response body.
    def fake_run_query(question, lang, intent, history, *, audience="", grade_band="",
                       length="", owner_id="local"):
        return api.QueryResponse(answer=f"answer for {owner_id}", citations=[], grounded=True,
                                 intent=intent or "qa", files=[])

    monkeypatch.setattr(api, "_run_query", fake_run_query)

    # Auth off by default; individual tests enable it via CHAVRUTA_API_KEYS (read live).
    monkeypatch.delenv("CHAVRUTA_API_KEYS", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)

    with TestClient(api.app) as c:
        yield c


def _poll(client, job_id, headers=None, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/jobs/{job_id}", headers=headers or {})
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_health_open_without_auth(client):
    assert client.get("/health").status_code == 200


def test_async_session_flow_end_to_end(client):
    # 202 with a job id + the session id (available immediately, before generation finishes).
    r = client.post("/sessions/async", json={"question": "מהי ברכת המזון?", "intent": "qa", "lang": "he"})
    assert r.status_code == 202, r.text
    acc = r.json()
    assert acc["job_id"] and acc["session_id"]

    done = _poll(client, acc["job_id"])
    assert done["status"] == "done"
    assert done["result"]["result"]["answer"] == "answer for local"

    # The turn was persisted: the session now has the user + assistant messages.
    msgs = client.get(f"/sessions/{acc['session_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_async_owner_isolation_over_http(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "alice-key,bob-key")
    a = {"Authorization": "Bearer alice-key"}
    b = {"Authorization": "Bearer bob-key"}

    # Alice creates a session (async) and it completes.
    r = client.post("/sessions/async", headers=a, json={"question": "שאלת אליס", "intent": "qa"})
    acc = r.json()
    _poll(client, acc["job_id"], headers=a)

    # Bob cannot poll Alice's job (404), cannot see her session, and cannot read her messages.
    assert client.get(f"/jobs/{acc['job_id']}", headers=b).status_code == 404
    assert client.get("/sessions", headers=b).json() == []
    assert client.get(f"/sessions/{acc['session_id']}/messages", headers=b).status_code == 404
    # Alice sees exactly her own one session.
    assert len(client.get("/sessions", headers=a).json()) == 1


def test_auth_required_when_keys_set(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "the-only-key")
    # No key → 401; health still open.
    assert client.post("/sessions/async", json={"question": "x"}).status_code == 401
    assert client.get("/health").status_code == 200


def test_free_quota_blocks_over_limit_and_me_reflects_it(client, monkeypatch):
    """Quota is metered in TOKENS since the 2026-07-26 rework, not in messages.

    This test used to set CHAVRUTA_FREE_DAILY_QUOTA and count requests. That variable is dead — no
    code reads it — so the test passed no quota at all, sent three requests, got three 202s and
    failed on the third. It was red for the right reason and testing nothing, which is worse than
    absent: the integration surface that proves a free account can be cut off had no cover at all.
    """
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]

    # One turn is admitted…
    assert client.post("/query/async", headers=h, json={"question": "a"}).status_code == 202

    # …then spend the day's budget outright. Counting requests instead would race the worker: the
    # turn is admitted against an ESTIMATE and _settle_tokens corrects it to the real cost once the
    # job finishes, which under a stubbed LLM is nearly nothing — so the reservation is handed back
    # before the next request arrives and nothing appears to be metered at all.
    db.bump_usage(owner, 25_000, weekly_limit=0, units=25_000, meter=db.TOKENS)

    blocked = client.post("/query/async", headers=h, json={"question": "b"})
    assert blocked.status_code == 429, "a free account past its daily tokens must be refused"
    me = client.get("/me", headers=h).json()
    # Reported as a FRACTION remaining, never an absolute token count — see MeOut.
    assert me["authenticated"] and me["day_left"] == 0.0


def test_local_user_never_quota_limited(client, monkeypatch):
    """Quota set, but auth off ⇒ everyone is 'local' ⇒ uncapped. The offline path must not be
    metered: there is no account to bill and no provider cost to contain."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "1")
    for _ in range(3):
        assert client.post("/query/async", json={"question": "x"}).status_code == 202
    me = client.get("/me").json()
    assert me["authenticated"] is False and me["day_left"] is None


def test_account_deletion_schedule_reflect_cancel(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    h = {"Authorization": "Bearer k"}
    # Not scheduled initially.
    assert client.get("/me", headers=h).json()["deletion_scheduled_for"] is None
    # Schedule → a future deadline is returned and surfaced on /me.
    when = client.post("/account/delete", headers=h).json()["deletion_scheduled_for"]
    assert when and client.get("/me", headers=h).json()["deletion_scheduled_for"] == when
    # Cancel → cleared.
    client.post("/account/delete/cancel", headers=h)
    assert client.get("/me", headers=h).json()["deletion_scheduled_for"] is None


def test_account_deletion_rejected_in_local_mode(client):
    # No auth ⇒ owner 'local' ⇒ no account to delete.
    assert client.post("/account/delete").status_code == 400


def test_blocked_account_403d_but_can_see_status(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]
    # Block permanently, then generation is 403'd while /me still works and reports the block.
    db.ban_account(owner, "2026-07-18T00:00:00+00:00", None, "abuse")
    assert client.post("/query/async", headers=h, json={"question": "x"}).status_code == 403
    assert client.post("/sessions/async", headers=h, json={"question": "x"}).status_code == 403
    me = client.get("/me", headers=h).json()
    assert me["blocked"] is True and me["blocked_until"] is None and me["blocked_reason"] == "abuse"
    # Lifting the block restores access.
    db.unban_account(owner)
    assert client.post("/query/async", headers=h, json={"question": "x"}).status_code == 202


def test_billing_config_disabled_by_default(client):
    cfg = client.get("/billing/config").json()
    assert cfg["enabled"] is False
    # `tiers` rides along so the frontend never hardcodes a price. It carries no absolute
    # allowance — that separation is the whole point of public_catalogue (legal review finding B).
    assert not any(k for t in cfg["tiers"] for k in t if "token" in k or "lesson" in k)


def test_billing_checkout_local_and_unconfigured(client, monkeypatch):
    # Local (no auth) ⇒ 400 (must sign in to subscribe).
    assert client.post("/billing/checkout", json={"email": "a@b.co"}).status_code == 400
    # Authed but billing not configured ⇒ 503.
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    assert client.post("/billing/checkout", headers={"Authorization": "Bearer k"},
                       json={"email": "a@b.co"}).status_code == 503


def test_billing_webhook_rejects_unsigned(client):
    # No valid PayPlus HMAC/user-agent ⇒ 400 (a forged callback can't activate a plan).
    r = client.post("/billing/webhook", json={"transaction": {"status_code": "000", "more_info": "x"}})
    # 503, not 400: with no signing secret configured the webhook FAILS CLOSED and refuses to
    # process at all, rather than parsing an unverifiable body. Tightened after a security review
    # found the endpoint forgeable; this test predated that and still expected the softer answer.
    assert r.status_code == 503


def test_plan_based_quota_switch(client, monkeypatch):
    """Upgrading the plan must widen the allowance — and NO tier is unlimited.

    This asserted `daily_quota is None` on the paid plan, i.e. unlimited. That is no longer true and
    must not become true again: on a product whose marginal cost is tokens, unlimited is an
    open-ended liability (see app/plans.py). Every tier now carries a real number, so the check is
    that the paid tier is strictly larger than free, not that it is boundless.
    """
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    me = client.get("/me", headers=h).json()
    assert me["plan"] == "free" and me["multiple"] == 1

    # A billing webhook would call db.set_plan; simulate it and re-check the tier.
    db.set_plan(me["owner"], "paid")
    me2 = client.get("/me", headers=h).json()
    assert me2["plan"] == "pro"     # 'paid' is the legacy alias; canonical() resolves it to the pro tier
    assert me2["multiple"] > me["multiple"], "a paid plan must actually buy more"
    assert me2["day_left"] is not None, "no tier is unlimited"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
