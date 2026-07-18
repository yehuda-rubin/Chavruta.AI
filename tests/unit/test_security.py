"""Public-hosting protections (app/security.py): API-key auth, per-IP rate limit, body cap.

Off/generous by default (local dev unchanged), enforced when env is set. These carry the cost and
access-control guarantees for a public deployment, so they're pinned.
"""
from __future__ import annotations

import types

import pytest
from app.security import _SlidingWindow, require_api_key


def _req(path="/query"):
    r = types.SimpleNamespace()
    r.url = types.SimpleNamespace(path=path)
    return r


def test_auth_disabled_when_no_keys(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_API_KEYS", raising=False)
    # no keys configured → any request passes (current public behaviour / local dev)
    require_api_key(_req(), None, None)


def test_auth_blocks_without_key(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k1,k2")
    with pytest.raises(HTTPException) as e:
        require_api_key(_req(), None, None)
    assert e.value.status_code == 401


@pytest.mark.parametrize("authz,xkey", [("Bearer k1", None), ("bearer k2", None), (None, "k1")])
def test_auth_accepts_valid_key(monkeypatch, authz, xkey):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k1,k2")
    require_api_key(_req(), authz, xkey)  # no raise


def test_auth_rejects_wrong_key(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k1")
    with pytest.raises(HTTPException):
        require_api_key(_req(), "Bearer nope", None)


@pytest.mark.parametrize("path", ["/health", "/ready", "/openapi.json"])
def test_health_and_docs_exempt_even_with_keys(monkeypatch, path):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k1")
    require_api_key(_req(path), None, None)  # exempt → no raise


def test_rate_limit_blocks_after_max():
    w = _SlidingWindow(3, 60.0)
    hits = [w.allow("ip", i * 0.1) for i in range(5)]
    assert hits == [True, True, True, False, False]


def test_rate_limit_is_per_key():
    w = _SlidingWindow(1, 60.0)
    assert w.allow("a", 0.0) is True
    assert w.allow("a", 0.1) is False   # a is over
    assert w.allow("b", 0.2) is True    # b is independent


def test_rate_limit_window_slides():
    w = _SlidingWindow(1, 10.0)
    assert w.allow("a", 0.0) is True
    assert w.allow("a", 5.0) is False   # within window
    assert w.allow("a", 11.0) is True   # old hit expired


# ── Per-owner data isolation (app/db.py) — the IDOR the audit flagged (GET /sessions leaked all) ──
def _fresh_db(tmp_path, monkeypatch):
    import app.db as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()   # init schema (v6, with owner_id) on the temp file
    return db


def test_sessions_are_isolated_by_owner(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    a = db.create_session("alice q", mode="qa", owner_id="alice")
    b = db.create_session("bob q", mode="qa", owner_id="bob")
    db.save_message(a, "user", "hi")
    db.save_message(b, "user", "hi")

    assert [s["id"] for s in db.list_sessions("alice")] == [a]     # alice sees only hers
    assert [s["id"] for s in db.list_sessions("bob")] == [b]
    assert db.get_messages(b, "alice") == []                       # can't read bob's chat
    assert len(db.get_messages(b, "bob")) == 1
    assert db.delete_session(b, "alice") is False                  # can't delete bob's
    assert db.list_sessions("bob"), "bob's session survived alice's delete attempt"
    assert db.get_session_mode(b, "alice") is None                 # can't read bob's locked mode


def test_lessons_are_isolated_by_owner(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    db.save_lesson("L1", "alice topic", "", "", "", "he", [{"name": "a"}], owner_id="alice")
    db.save_lesson("L2", "bob topic", "", "", "", "he", [{"name": "b"}], owner_id="bob")

    assert [x["id"] for x in db.list_lessons("alice")] == ["L1"]
    assert db.get_lesson("L2", "alice") is None                    # can't read bob's lesson
    assert db.get_lesson("L2", "bob") is not None
    assert db.delete_lesson("L2", "alice") is False                # can't delete bob's
    assert db.get_lesson("L2", "bob") is not None
