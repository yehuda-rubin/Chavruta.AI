"""Supabase JWT verification (app/auth_supabase.py) and the auth-mode wiring in app/security.py.

Uses a real ES256 keypair to mint tokens and monkeypatches only the JWKS *lookup* (the network part)
to hand back the matching public key — so signature, expiry, audience and issuer are all verified for
real. The guarantees pinned: a good token yields its `sub`; tampered / expired / wrong-audience /
wrong-issuer tokens are rejected (None, never a 500); and require_auth/current_owner switch cleanly
between Supabase, API-key, and open-local modes.
"""
from __future__ import annotations

import time
import types

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

import app.auth_supabase as sb
from app import security

_ISS = "https://demo.supabase.co/auth/v1"


@pytest.fixture
def es256_keypair():
    priv = ec.generate_private_key(ec.SECP256R1())
    return priv, priv.public_key()


@pytest.fixture
def supabase_env(monkeypatch, es256_keypair):
    """Configure Supabase mode and route the JWKS lookup to the fixture's public key."""
    priv, pub = es256_keypair
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    sb.reset_cache()
    fake_key = types.SimpleNamespace(key=pub)
    monkeypatch.setattr(sb, "_client", lambda: types.SimpleNamespace(
        get_signing_key_from_jwt=lambda token: fake_key))
    return priv, pub


_CONSENTED = {"user_metadata": {"age_confirmed_18": True, "terms_version": "1.4"}}


def _token(priv, *, sub="user-123", aud="authenticated", iss=_ISS, exp_delta=3600, extra=None):
    now = int(time.time())
    claims = {"sub": sub, "aud": aud, "iss": iss, "iat": now, "exp": now + exp_delta}
    if extra:
        claims.update(extra)
    return jwt.encode(claims, priv, algorithm="ES256")


def test_enabled_follows_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    assert not sb.enabled()
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    assert sb.enabled()
    assert sb.jwks_url() == "https://demo.supabase.co/auth/v1/.well-known/jwks.json"
    assert sb.issuer() == _ISS


def test_valid_token_yields_sub(supabase_env):
    priv, _ = supabase_env
    assert sb.verify_sub(_token(priv, sub="abc-uuid")) == "abc-uuid"


def test_tampered_token_rejected(supabase_env):
    priv, _ = supabase_env
    tok = _token(priv)
    assert sb.verify_sub(tok[:-4] + "AAAA") is None      # corrupt the signature


def test_expired_token_rejected(supabase_env):
    priv, _ = supabase_env
    assert sb.verify_sub(_token(priv, exp_delta=-10)) is None


def test_wrong_audience_rejected(supabase_env):
    priv, _ = supabase_env
    assert sb.verify_sub(_token(priv, aud="anon")) is None


def test_wrong_issuer_rejected(supabase_env):
    priv, _ = supabase_env
    assert sb.verify_sub(_token(priv, iss="https://evil.example/auth/v1")) is None


def test_empty_token_is_none(supabase_env):
    assert sb.verify_sub("") is None
    assert sb.verify_sub(None) is None


# ── security.py mode switching ────────────────────────────────────────────────
def _req(path="/query"):
    r = types.SimpleNamespace()
    r.url = types.SimpleNamespace(path=path)
    r.state = types.SimpleNamespace()
    return r


def test_require_auth_supabase_rejects_missing_token(supabase_env):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        security.require_auth(_req(), None, None)
    assert e.value.status_code == 401


def test_require_auth_supabase_accepts_and_sets_owner(supabase_env):
    priv, _ = supabase_env
    req = _req()
    security.require_auth(req, f"Bearer {_token(priv, sub='u-9', extra=_CONSENTED)}", None)
    assert req.state.owner == "u-9"


def test_current_owner_supabase_is_verified_sub(supabase_env):
    priv, _ = supabase_env
    req = _req()
    security.require_auth(req, f"Bearer {_token(priv, sub='u-42', extra=_CONSENTED)}", None)
    assert security.current_owner(req, None, None) == "u-42"


# ── Consent gate (2026-07-30 — see docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding A) ───────────
def test_require_auth_rejects_missing_consent(supabase_env):
    """A token with no user_metadata at all — e.g. an account created by calling Supabase's own
    signup API directly, bypassing the app's terms/age checkboxes entirely — must not reach a
    generation route."""
    from fastapi import HTTPException

    priv, _ = supabase_env
    with pytest.raises(HTTPException) as e:
        security.require_auth(_req("/query"), f"Bearer {_token(priv)}", None)
    assert e.value.status_code == 403
    assert e.value.detail["error"] == "consent_required"


def test_require_auth_rejects_partial_consent(supabase_env):
    """Age confirmed but no recorded terms version (or vice versa) still doesn't count."""
    priv, _ = supabase_env
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        security.require_auth(
            _req("/query"),
            f"Bearer {_token(priv, extra={'user_metadata': {'age_confirmed_18': True}})}", None)
    assert e.value.status_code == 403


def test_require_auth_allows_me_and_account_without_consent(supabase_env):
    """/me and /account stay reachable without consent, same as for a banned account — so the
    frontend can detect the situation and the user can confirm through the app instead of being
    stuck with an opaque 403 on every route."""
    priv, _ = supabase_env
    security.require_auth(_req("/me"), f"Bearer {_token(priv)}", None)
    security.require_auth(_req("/account/delete"), f"Bearer {_token(priv)}", None)


def test_current_owner_local_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("CHAVRUTA_API_KEYS", raising=False)
    assert security.current_owner(_req(), None, None) == "local"


def test_api_key_mode_unaffected_by_supabase_helpers(monkeypatch):
    """With Supabase unset but API keys set, current_owner keeps its stable-hash behaviour."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k1")
    owner = security.current_owner(_req(), "Bearer k1", None)
    assert owner.startswith("u_") and owner != "local"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
