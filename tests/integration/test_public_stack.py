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
import app.plans as plans

# A daily cap that fits one qa turn and not two — derived, not hardcoded, so raising the generation
# budgets cannot turn these quota tests into false 429s. The 1.5x headroom keeps the FIRST turn from
# failing on a stray already-metered token. See the same constants in tests/unit/test_byok_quota.py.
_ONE_TURN = plans.token_estimate("qa")
_DAY_CAP = int(_ONE_TURN * 1.5)


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
                       length="", owner_id="local", llm=None):
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


def test_exclude_session_from_review_is_owner_scoped(client, monkeypatch):
    # Per-chat opt-out from the operator's post-10.8.2026 review/improvement use (privacy policy
    # section 12) — reuses the existing PATCH /sessions/{id} route, same as rename/pin.
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "alice-key,bob-key")
    a = {"Authorization": "Bearer alice-key"}
    b = {"Authorization": "Bearer bob-key"}

    r = client.post("/sessions/async", headers=a, json={"question": "שאלה", "intent": "qa"})
    sid = r.json()["session_id"]

    # New sessions default to included.
    session = next(s for s in client.get("/sessions", headers=a).json() if s["id"] == sid)
    assert session["excluded_from_review"] is False

    # Bob cannot exclude Alice's session.
    assert client.patch(f"/sessions/{sid}", headers=b, json={"excluded": True}).status_code == 404

    # Alice can, and it's reflected back.
    r = client.patch(f"/sessions/{sid}", headers=a, json={"excluded": True})
    assert r.status_code == 200, r.text
    assert r.json()["excluded_from_review"] is True

    # And she can flip it back.
    r = client.patch(f"/sessions/{sid}", headers=a, json={"excluded": False})
    assert r.json()["excluded_from_review"] is False


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
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]

    # One turn is admitted…
    admitted = client.post("/query/async", headers=h, json={"question": "a"})
    assert admitted.status_code == 202
    # …and its job must FINISH before we touch the counter it settles against. With the reservation
    # still outstanding the seeding bump below is itself refused (estimate + cap > cap), and the
    # worker's refund then drops the counter back to nearly zero — so the request that must be 429
    # sails through. Passes alone, fails under a full-suite run.
    _poll(client, admitted.json()["job_id"], headers=h)

    # …then spend the day's budget outright. Counting requests instead would race the worker: the
    # turn is admitted against an ESTIMATE and _settle_tokens corrects it to the real cost once the
    # job finishes, which under a stubbed LLM is nearly nothing — so the reservation is handed back
    # before the next request arrives and nothing appears to be metered at all.
    allowed, _d, _w = db.bump_usage(owner, _DAY_CAP, weekly_limit=0, units=_DAY_CAP, meter=db.TOKENS)
    assert allowed, "the seeding bump must actually land, or this test proves nothing"

    blocked = client.post("/query/async", headers=h, json={"question": "b"})
    assert blocked.status_code == 429, "a free account past its daily tokens must be refused"
    me = client.get("/me", headers=h).json()
    # Reported as a FRACTION remaining, never an absolute token count — see MeOut.
    assert me["authenticated"] and me["day_left"] == 0.0


def test_byok_header_grants_a_second_allowance_over_http(client, monkeypatch):
    """End-to-end: a caller-supplied X-User-LLM-Key admits a request over HTTP once the plan's own
    token quota is spent, and is refused once the SAME-SIZED BYOK allowance is also spent — the key
    is a second allowance, not an unlimited escape hatch. _byok_llm is stubbed (the fake pipeline
    here has no real .profile/wire_source_fetcher — see the `client` fixture) since the point of
    this test is the quota routing, not building a real provider client."""
    from types import SimpleNamespace as _NS

    monkeypatch.setattr(api, "_byok_supported", lambda: True)
    monkeypatch.setattr(api, "_byok_llm", lambda key, base_url="", model="": _NS())
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]

    db.bump_usage(owner, _DAY_CAP, weekly_limit=0, units=_DAY_CAP, meter=db.TOKENS)
    assert client.post("/query/async", headers=h, json={"question": "a"}).status_code == 429

    hk = {**h, "X-User-LLM-Key": "user-owns-this-key"}
    admitted = client.post("/query/async", headers=hk, json={"question": "a"})
    assert admitted.status_code == 202

    # Wait for that job to finish before touching the meter it settles against. The job refunds its
    # own reservation from a worker thread, so a test that bumps the counter first races it — the
    # refund lands afterwards, undoes the bump, and the third request is admitted. Rare enough to
    # pass alone and fail under a full-suite run, which is the worst kind of flake to leave behind.
    _poll(client, admitted.json()["job_id"], headers=hk)

    db.bump_usage(owner, _DAY_CAP, weekly_limit=0, units=_DAY_CAP, meter=db.BYOK_TOKENS)
    blocked = client.post("/query/async", headers=hk, json={"question": "b"})
    assert blocked.status_code == 429, "a key is a second allowance, not unlimited"


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


def test_immediate_deletion_erases_now_and_leaves_nothing_scheduled(client, monkeypatch):
    """The user who says "I asked to be deleted, why is it a month away" gets what they asked for in
    the app instead of having to email the operator. Nothing is left pending afterwards — a deletion
    that still shows as "scheduled" would suggest it had not happened."""
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    h = {"Authorization": "Bearer k"}
    # Seeded straight into the DB: POST /sessions runs a real generation, and this test is about
    # what deletion removes, not about the model.
    owner = client.get("/me", headers=h).json()["owner"]
    db.create_session("שאלה", mode="qa", owner_id=owner)
    assert len(client.get("/sessions", headers=h).json()) == 1

    got = client.post("/account/delete", json={"immediate": True}, headers=h).json()
    assert got["deleted"] is True and got["deletion_scheduled_for"] is None
    assert client.get("/me", headers=h).json()["deletion_scheduled_for"] is None
    assert client.get("/sessions", headers=h).json() == []          # the data really is gone


def test_deletion_defaults_to_the_grace_period_when_no_body_is_sent(client, monkeypatch):
    """An older client posts no body at all. It must still get the SAFE path, never the irreversible
    one — a missing field defaulting to "delete now" would be the worst possible default."""
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    h = {"Authorization": "Bearer k"}
    got = client.post("/account/delete", headers=h).json()
    assert got["deleted"] is False and got["deletion_scheduled_for"]


def test_me_states_the_grace_period_length(client, monkeypatch):
    """The UI names the number before the user commits, so it has to come from the server that will
    actually apply it — not a 30 hardcoded in the frontend next to a configurable backend."""
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    monkeypatch.setenv("CHAVRUTA_ACCOUNT_DELETION_GRACE_DAYS", "7")
    assert client.get("/me", headers={"Authorization": "Bearer k"}).json()["deletion_grace_days"] == 7


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
