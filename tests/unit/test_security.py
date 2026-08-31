"""Public-hosting protections (app/security.py): API-key auth, per-IP rate limit, body cap.

Off/generous by default (local dev unchanged), enforced when env is set. These carry the cost and
access-control guarantees for a public deployment, so they're pinned.
"""
from __future__ import annotations

import types

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

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


def test_rate_limit_zero_means_unlimited_not_blocked():
    # CHAVRUTA_RATE_PER_MIN=0 is meant as "disable this limit" (the common convention for a limit
    # env var), not "every request is already over the limit" — `len(hits) >= 0` is always true, so
    # without the explicit guard this configuration blocked 100% of traffic instead of 0%.
    w = _SlidingWindow(0, 60.0)
    assert all(w.allow("a", i * 0.1) for i in range(10))


# ── Spoof-proof client IP for the rate-limit key (adversarial review P1) ──
def _req_ip(peer="1.2.3.4", xff=None):
    r = types.SimpleNamespace()
    r.client = types.SimpleNamespace(host=peer)
    r.headers = {"x-forwarded-for": xff} if xff is not None else {}
    return r


def test_client_ip_ignores_xff_by_default(monkeypatch):
    from app.security import _client_ip
    monkeypatch.delenv("CHAVRUTA_TRUSTED_PROXY_HOPS", raising=False)
    # Attacker rotates XFF hoping for a fresh rate-limit bucket — with no trusted proxy it's ignored
    # and the (unforgeable) TCP peer is used, so every request maps to the same bucket.
    assert _client_ip(_req_ip(peer="9.9.9.9", xff="evil-1")) == "9.9.9.9"
    assert _client_ip(_req_ip(peer="9.9.9.9", xff="evil-2")) == "9.9.9.9"


def test_client_ip_takes_last_hop_behind_one_proxy(monkeypatch):
    from app.security import _client_ip
    monkeypatch.setenv("CHAVRUTA_TRUSTED_PROXY_HOPS", "1")
    # nginx appends the real client as the LAST XFF entry; the leftmost is attacker-typed and ignored.
    assert _client_ip(_req_ip(peer="10.0.0.2", xff="spoofed, 203.0.113.7")) == "203.0.113.7"
    # Spoofing more entries can't help: still the last hop.
    assert _client_ip(_req_ip(peer="10.0.0.2", xff="a, b, 203.0.113.7")) == "203.0.113.7"


def test_client_ip_two_trusted_hops(monkeypatch):
    from app.security import _client_ip
    monkeypatch.setenv("CHAVRUTA_TRUSTED_PROXY_HOPS", "2")
    # client -> CF (adds real client) -> nginx (adds CF ip): real client is 2nd from the right.
    assert _client_ip(_req_ip(peer="10.0.0.2", xff="spoof, 203.0.113.7, 172.16.0.9")) == "203.0.113.7"


def test_client_ip_falls_back_to_peer_when_xff_too_short(monkeypatch):
    from app.security import _client_ip
    monkeypatch.setenv("CHAVRUTA_TRUSTED_PROXY_HOPS", "2")
    # Only one hop present but two claimed — don't trust it, use the peer.
    assert _client_ip(_req_ip(peer="10.0.0.2", xff="203.0.113.7")) == "10.0.0.2"


# ── The limit key: an account when provable, else the IP (spec 004 — a school behind one NAT) ──
def _req_auth(peer="1.2.3.4", token=None):
    r = types.SimpleNamespace()
    r.client = types.SimpleNamespace(host=peer)
    r.headers = {"authorization": f"Bearer {token}"} if token else {}
    return r


def test_limit_key_is_the_ip_when_there_is_no_auth(monkeypatch):
    from app import auth_supabase as sb
    from app.security import _limit_key
    monkeypatch.setattr(sb, "enabled", lambda: False)
    assert _limit_key(_req_auth(peer="9.9.9.9")) == "ip:9.9.9.9"


def test_two_signed_in_users_behind_one_ip_get_separate_buckets(monkeypatch):
    """The school case. Sharing one bucket meant three active students could 429 the other
    twenty-seven, and no amount of quota the school had paid for would have helped."""
    from app import auth_supabase as sb
    from app.security import _limit_key
    monkeypatch.setattr(sb, "enabled", lambda: True)
    monkeypatch.setattr(sb, "verify_sub", lambda tok: {"t-a": "user-a", "t-b": "user-b"}.get(tok))
    a = _limit_key(_req_auth(peer="203.0.113.9", token="t-a"))
    b = _limit_key(_req_auth(peer="203.0.113.9", token="t-b"))
    assert a != b
    assert a == "u:user-a"


def test_an_unverified_token_cannot_mint_a_fresh_bucket(monkeypatch):
    """The id comes from the VERIFIED token only. Otherwise rotating a made-up bearer would skip the
    limiter entirely — a worse hole than the one this fixes."""
    from app import auth_supabase as sb
    from app.security import _limit_key
    monkeypatch.setattr(sb, "enabled", lambda: True)
    monkeypatch.setattr(sb, "verify_sub", lambda tok: None)
    assert _limit_key(_req_auth(peer="9.9.9.9", token="forged-1")) == "ip:9.9.9.9"
    assert _limit_key(_req_auth(peer="9.9.9.9", token="forged-2")) == "ip:9.9.9.9"


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


# ── The middleware itself, not just the key function ─────────────────────────
def test_the_limiter_still_limits_through_the_middleware(monkeypatch, tmp_path):
    """_limit_key now runs via run_in_threadpool. The three tests above call it directly and would
    pass identically if the middleware forgot to await it — which would use a coroutine as the dict
    key, giving every request a unique bucket and switching the limiter off entirely."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    import app.api as api
    import app.db as db
    from app import security

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "rl.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(api, "_assert_config_usable", lambda: None)
    monkeypatch.setattr(api, "_get_pipeline", lambda: SimpleNamespace(
        embedding=SimpleNamespace(embed_query=lambda q: SimpleNamespace(dense=[0.0], sparse={}))))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.setattr(security, "_minute", security._SlidingWindow(3, 60.0))
    monkeypatch.setattr(security, "_hour", security._SlidingWindow(100, 3600.0))

    with TestClient(api.app) as c:
        codes = [c.post("/query/async", json={"question": "x"}).status_code for _ in range(5)]
    assert 429 in codes, "the middleware must actually reach the window"
    assert codes.count(202) == 3


# ── Body cap must also catch bodies with no Content-Length (chunked transfer) ─────────────────
def test_body_size_middleware_allows_small_chunked_body(monkeypatch):
    from app import security

    monkeypatch.setattr(security, "_MAX_BODY", 10)

    app = FastAPI()
    app.middleware("http")(security.body_size_middleware)

    @app.post("/echo")
    async def echo(request: Request):
        return {"len": len(await request.body())}

    def chunks(data: bytes):
        for i in range(0, len(data), 3):
            yield data[i:i + 3]

    with TestClient(app) as c:
        r = c.post("/echo", content=chunks(b"hello"))   # 5 bytes, under the 10-byte cap
    assert r.status_code == 200
    assert r.json()["len"] == 5


def test_body_size_middleware_rejects_oversized_chunked_body(monkeypatch):
    """Content-Length is absent for `Transfer-Encoding: chunked` — the header check alone can't see
    an oversized body sent this way, so it used to sail straight through uncounted."""
    from app import security

    monkeypatch.setattr(security, "_MAX_BODY", 10)

    app = FastAPI()
    app.middleware("http")(security.body_size_middleware)

    @app.post("/echo")
    async def echo(request: Request):
        return {"len": len(await request.body())}   # must never run for the oversized request

    def chunks(data: bytes):
        for i in range(0, len(data), 3):
            yield data[i:i + 3]

    with TestClient(app) as c:
        r = c.post("/echo", content=chunks(b"x" * 50))   # 50 bytes, over the 10-byte cap
    assert r.status_code == 413
