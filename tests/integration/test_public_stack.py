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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
