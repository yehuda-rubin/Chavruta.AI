"""HTTP-level coverage of /admin/* — the same TestClient(api.app) fixture as test_public_stack.py,
proving the real gate: a non-admin owner never sees anything different from a 404 "not found",
and an admin owner reaches real aggregated data."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.db as db


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(api, "_assert_config_usable", lambda: None)
    fake_pipeline = SimpleNamespace(
        embedding=SimpleNamespace(embed_query=lambda q: SimpleNamespace(dense=[0.0], sparse={})))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake_pipeline)
    monkeypatch.delenv("CHAVRUTA_ADMIN_OWNERS", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    with TestClient(api.app) as c:
        yield c


def test_non_admin_gets_404_on_every_admin_route(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    assert client.get("/admin/overview", headers=h).status_code == 404
    assert client.get("/admin/usage-by-owner", headers=h).status_code == 404
    assert client.get("/admin/usage-by-intent", headers=h).status_code == 404
    assert client.get("/admin/usage-by-week", headers=h).status_code == 404
    assert client.get("/admin/flagged-messages", headers=h).status_code == 404
    assert client.post("/admin/flagged-messages/1/review", headers=h).status_code == 404


def test_local_unauthenticated_caller_also_gets_404(client):
    assert client.get("/admin/overview").status_code == 404


def test_admin_owner_reaches_overview_with_expected_shape(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]

    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)
    r = client.get("/admin/overview", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"accounts", "usage", "concurrency", "revenue"}
    assert set(body["accounts"].keys()) == {"total", "by_plan"}
    assert set(body["revenue"].keys()) == {"by_plan", "totals"}


def test_me_reflects_is_admin(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]
    assert client.get("/me", headers=h).json()["is_admin"] is False

    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)
    assert client.get("/me", headers=h).json()["is_admin"] is True


def test_admin_can_review_a_flagged_message(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)

    # Build the underlying state directly (a session + message + report) rather than driving the
    # real generation pipeline through HTTP — this test is about the /admin routes, not generation.
    sid = db.create_session("x", owner_id=owner)
    msg_id = db.save_message(sid, "assistant", "an answer")
    db.report_message(msg_id, owner, "test")

    unreviewed = client.get("/admin/flagged-messages?reviewed=false", headers=h).json()
    assert len(unreviewed) == 1

    review = client.post(f"/admin/flagged-messages/{unreviewed[0]['id']}/review", headers=h)
    assert review.status_code == 200 and review.json()["ok"] is True

    assert client.get("/admin/flagged-messages?reviewed=false", headers=h).json() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
