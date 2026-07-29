"""Supabase Auth — verify the access-token JWT a signed-in user's browser sends.

Flow: the Next.js frontend signs the user in with Supabase (email / OAuth) and puts the returned
access token in `Authorization: Bearer <jwt>` on every API call. We verify that token HERE, offline,
against the project's public JSON Web Key Set — fetched once and cached, never a per-request round
trip to Supabase — and take the `sub` claim (a stable user UUID) as the owner_id that scopes the
caller's sessions and lessons. This slots in exactly where the API-key-derived owner used to sit
(`app.security.current_owner`), so no data-scoping code downstream changes.

Enabled purely by environment (Principle II): set SUPABASE_URL (or SUPABASE_JWKS_URL) and this is the
auth mode; leave it unset and the API keeps its existing API-key / open-local behaviour untouched.

Reference (Supabase docs, verified 2026-07-18):
  JWKS     GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json
  issuer   {SUPABASE_URL}/auth/v1
  audience "authenticated"
  alg      ES256 (asymmetric signing keys) / RS256; legacy projects use an HS256 shared secret.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger("chavruta.auth")


def project_url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def jwks_url() -> str:
    explicit = os.environ.get("SUPABASE_JWKS_URL", "").strip()
    if explicit:
        return explicit
    url = project_url()
    return f"{url}/auth/v1/.well-known/jwks.json" if url else ""


def issuer() -> str:
    explicit = os.environ.get("SUPABASE_JWT_ISSUER", "").strip()
    if explicit:
        return explicit
    url = project_url()
    return f"{url}/auth/v1" if url else ""


def _audience() -> str:
    # Supabase issues user tokens with aud="authenticated"; overridable for a custom setup.
    return os.environ.get("SUPABASE_JWT_AUD", "authenticated")


def _jwt_secret() -> str:
    # Legacy HS256 shared secret (older Supabase projects). Modern projects use asymmetric keys and
    # leave this unset — then verification goes through the JWKS below.
    return os.environ.get("SUPABASE_JWT_SECRET", "").strip()


def enabled() -> bool:
    """True when Supabase auth is configured — either a JWKS endpoint or a legacy shared secret."""
    return bool(jwks_url() or _jwt_secret())


# PyJWKClient fetches the JWKS once and caches the signing keys in-process (like jose's
# createRemoteJWKSet), so steady-state verification is a local signature check — no network per call.
_jwk_client = None


def _client():
    global _jwk_client
    if _jwk_client is None:
        from jwt import PyJWKClient
        _jwk_client = PyJWKClient(jwks_url())
    return _jwk_client


def reset_cache() -> None:
    """Drop the cached JWKS client — for tests that reconfigure the endpoint between cases."""
    global _jwk_client
    _jwk_client = None


def verify(token: str | None) -> dict | None:
    """Return the verified JWT payload for a valid token, else None (missing / malformed /
    bad-signature / expired / wrong issuer or audience). Never raises — the caller maps None to 401.

    Supabase embeds `user_metadata` directly in this same token — the consent-recording fields
    written at signup (age_confirmed_18, terms_version) are already here, so checking them costs no
    extra network round trip. See require_auth() in app/security.py."""
    if not token:
        return None
    try:
        import jwt

        iss = issuer()
        common = dict(
            audience=_audience(),
            options={"require": ["exp", "sub"], "verify_iss": bool(iss)},
        )
        if iss:
            common["issuer"] = iss

        secret = _jwt_secret()
        if secret:
            payload = jwt.decode(token, secret, algorithms=["HS256"], **common)
        else:
            signing_key = _client().get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"], **common)
        return payload
    except Exception as exc:                # noqa: BLE001 — any failure is an auth rejection, not a 500
        _log.info("supabase token rejected: %s", exc.__class__.__name__)
        return None


def verify_sub(token: str | None) -> str | None:
    """Return the verified user id (`sub`) for a valid token, else None."""
    payload = verify(token)
    return payload.get("sub") if payload else None
