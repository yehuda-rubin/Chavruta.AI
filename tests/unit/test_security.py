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
