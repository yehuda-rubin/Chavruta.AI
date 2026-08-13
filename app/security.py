"""Public-hosting protections: rate limiting, optional API-key auth, and a body-size cap.

All three are OFF or generous by default so local dev is unchanged, and tightened for a public
deployment purely by environment variables (Principle II — config, not code). The audit flagged the
API as having none of these: every route was public, one ~2KB request could drive ~135k tokens on
the LLM key, and `GET /sessions` enumerated everyone's sessions. This is the protective layer.

Single-instance, in-memory: the rate limiter's counters live in this process. Behind more than one
replica you'd move the window to Redis — noted, not built, because it isn't needed for one instance.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import socket
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import accounts as accts
from app import auth_supabase as sb

_log = logging.getLogger("chavruta.request")

# A blocked account is still allowed to reach these — so it can see WHY it's blocked (/me reports
# the block) and manage its own account (/account/*). Everything else is 403'd, and so is every
# route for an account that never accepted the Terms or confirmed 18+.
#
# `/me` is matched EXACTLY and only `/account/` by prefix. Written as ("/me", "/account") and tested
# with str.startswith, the tuple also exempted every path that merely BEGINS with those letters —
# `/messages/{id}/report` and `/metrics` both do. A permanently blocked account kept a live write
# path into the operator's own moderation queue, and both routes were reachable by an account that
# had accepted nothing. A prefix list is the wrong shape for a rule about routes; the bug is not the
# entries, it is that `startswith` was ever asked the question.
_BAN_EXEMPT_PATHS = frozenset({"/me"})
_BAN_EXEMPT_PREFIXES = ("/account/",)


def _ban_exempt(path: str) -> bool:
    return path in _BAN_EXEMPT_PATHS or path.startswith(_BAN_EXEMPT_PREFIXES)


# ── Outbound URL policy (BYOK) ────────────────────────────────────────────────
# A BYOK caller supplies the provider base URL their key belongs to, and the SERVER then makes
# requests to it — GET {base}/models to validate the model, POST {base}/chat/completions to generate.
# Unvalidated, that is a request generator aimed at our own network from inside it: Qdrant on :6333,
# the API itself on :8080, a cloud metadata endpoint on 169.254.169.254. And it is not even blind —
# the /models listing is echoed back to the caller in the response.
#
# What this does NOT solve, said plainly rather than left implied: the name is resolved HERE and
# connected to LATER by the OpenAI client, which resolves it again. A host that answers with a public
# address now and a private one a moment afterwards defeats the check. Closing that means pinning the
# connection to the address that was vetted; what follows rejects the direct cases and is not a
# substitute for that.
_BYOK_ALLOW_HTTP = os.environ.get("CHAVRUTA_BYOK_ALLOW_HTTP", "").strip().lower() in {"1", "true", "yes"}


class UnsafeProviderURL(ValueError):
    """A user-supplied provider URL that the server must not fetch."""


def validate_provider_base_url(url: str) -> str:
    """Return `url` unchanged if the server may call it, else raise UnsafeProviderURL."""
    raw = (url or "").strip()
    if not raw:
        raise UnsafeProviderURL("empty provider URL")
    parts = urlsplit(raw)
    if parts.scheme not in ("https", "http"):
        raise UnsafeProviderURL("the provider URL must start with https://")
    if parts.scheme == "http" and not _BYOK_ALLOW_HTTP:
        raise UnsafeProviderURL("the provider URL must use https")
    if parts.username or parts.password:
        # Credentials in the URL are never needed here — the key travels in a header — and they are
        # a well-worn way of making a hostile host read as a familiar one.
        raise UnsafeProviderURL("the provider URL must not embed credentials")
    host = parts.hostname
    if not host:
        raise UnsafeProviderURL("the provider URL has no host")
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UnsafeProviderURL("the provider host could not be resolved") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # `is_global` is False for every range that matters here at once — private, loopback,
        # link-local (169.254.169.254 included), multicast, reserved, unspecified — and it keeps
        # being right as ranges are assigned, which a hand-written CIDR list would not.
        if not ip.is_global:
            raise UnsafeProviderURL("the provider URL resolves to an internal address")
    return raw


# ── Auth ──────────────────────────────────────────────────────────────────────
# Two interchangeable modes, both env-gated (Principle II):
#   • Supabase (SUPABASE_URL set)  — a real signed-in user; owner = the verified JWT `sub`.
#   • API key  (CHAVRUTA_API_KEYS) — a shared/service key; owner = a stable hash of the key.
# Neither configured ⇒ open local dev, everyone is the single 'local' user (unchanged).
def _api_keys() -> set[str]:
    """Keys allowed to call the API. Empty ⇒ API-key auth DISABLED."""
    return {k.strip() for k in os.environ.get("CHAVRUTA_API_KEYS", "").split(",") if k.strip()}


# /billing/webhook is public — the payment provider posts to it with no bearer token; it is
# authenticated instead by its own HMAC signature (verified in the route).
_AUTH_EXEMPT = ("/health", "/ready", "/docs", "/openapi.json", "/redoc", "/billing/webhook")


def _bearer(authorization: str | None) -> str:
    """The token from an `Authorization: Bearer <token>` header, or ''."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """API-key gate. If CHAVRUTA_API_KEYS is set, require a matching key via `Authorization: Bearer
    <key>` or `X-API-Key: <key>`; otherwise a no-op. Liveness / readiness / docs are always exempt so
    probes and orchestrators aren't blocked."""
    if request.url.path in _AUTH_EXEMPT:
        return
    keys = _api_keys()
    if not keys:
        return
    presented = x_api_key or _bearer(authorization)
    if presented not in keys:
        raise HTTPException(status_code=401, detail="missing or invalid API key")


def _owner_from_key(authorization: str | None, x_api_key: str | None) -> str:
    """The owner id for API-key / open-local mode: 'local' when no keys are set or none presented,
    otherwise a stable hash of the presented key (the key is never stored as an id)."""
    if not _api_keys():
        return "local"
    presented = x_api_key or _bearer(authorization)
    if not presented:
        return "local"
    return "u_" + hashlib.sha256(presented.encode()).hexdigest()[:16]


def _has_consented(payload: dict) -> bool:
    """Whether the account carries a real terms-acceptance + 18+ confirmation.

    These are written into Supabase user_metadata at signup (SignIn.tsx) but were never checked
    anywhere server-side — since the Supabase anon key is public by definition, anyone could create
    a working account via Supabase's own signup API and skip both checkboxes entirely. This is that
    check (found in the 2026-07-30 lawsuit-exposure audit, docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md
    Finding A)."""
    meta = payload.get("user_metadata") or {}
    return bool(meta.get("age_confirmed_18")) and bool(str(meta.get("terms_version") or "").strip())


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """App-wide gate. Resolves the caller's identity (Supabase JWT `sub`, or a hashed API key, or
    'local'), stashes it on request.state for current_owner, and enforces the blocklist: a blocked
    account is 403'd on every route except viewing/managing its own account. In Supabase mode, also
    enforces that the account actually carries terms/age consent (see _has_consented) — again
    exempting /me and /account so the frontend can detect the situation and let the user confirm."""
    path = request.url.path
    if path in _AUTH_EXEMPT:
        return
    if sb.enabled():
        payload = sb.verify(_bearer(authorization))
        if not payload:
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")
        owner = payload.get("sub")
        if not owner:
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")
        if not _has_consented(payload) and not _ban_exempt(path):
            raise HTTPException(status_code=403, detail={
                "error": "consent_required",
                "message": "Terms of Use and age (18+) confirmation are required to use the service.",
            })
    else:
        require_api_key(request, authorization, x_api_key)     # 401 on a bad/absent key
        owner = _owner_from_key(authorization, x_api_key)
    request.state.owner = owner

    if owner != "local" and not _ban_exempt(path):
        ban = accts.active_ban(owner)
        if ban:
            raise HTTPException(status_code=403, detail={
                "error": "account_blocked",
                "permanent": ban["permanent"],
                "until": ban["until"],
                "reason": ban["reason"],
            })


def current_owner(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
    """The identity data is scoped to. Prefers the value require_auth already resolved and stashed;
    falls back to recomputing for direct calls (and exempt paths that skip require_auth)."""
    stashed = getattr(getattr(request, "state", None), "owner", None)
    if stashed:
        return stashed
    if sb.enabled():
        return "local"
    return _owner_from_key(authorization, x_api_key)


# ── Rate limiting (per-account where provable, else per-IP; in-memory sliding window) ─────────
class _SlidingWindow:
    def __init__(self, max_events: int, window_s: float):
        self.max = max_events
        self.window = window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float) -> bool:
        with self._lock:
            cutoff = now - self.window
            hits = [t for t in self._hits.get(key, ()) if t > cutoff]
            if len(hits) >= self.max:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def sweep(self, now: float) -> None:
        """Drop idle keys so the dict doesn't grow without bound under many distinct IPs."""
        with self._lock:
            cutoff = now - self.window
            for k in [k for k, v in self._hits.items() if not any(t > cutoff for t in v)]:
                del self._hits[k]


# Two windows: a burst-per-minute and a heavier per-hour cap on the expensive generation routes.
# Defaults are generous (a real user won't hit them); a public deployment tightens via env.
_RPM = int(os.environ.get("CHAVRUTA_RATE_PER_MIN", "20"))
_RPH = int(os.environ.get("CHAVRUTA_RATE_PER_HOUR", "200"))
_minute = _SlidingWindow(_RPM, 60.0)
_hour = _SlidingWindow(_RPH, 3600.0)

# Only the generation routes are metered — they're the ones that cost tokens. Health, session
# listing, and reads are exempt so a dashboard/poller isn't throttled.
# /byok is here for a different reason from the other two: it drives no generation, but every call
# blocks a sync-threadpool worker for the length of an outbound HTTP request to a host the CALLER
# chose. Unmetered, a handful of concurrent requests to a blackholed address pin every worker in the
# pool and stall every other sync route in the app — which is nearly all of them.
_METERED_PREFIXES = ("/query", "/sessions", "/byok")   # POST: drives the LLM, or an outbound call
_EXEMPT = ("/health", "/ready")
_last_sweep = [0.0]


def _trusted_proxy_hops() -> int:
    """How many trusted reverse proxies sit in front of the app. 0 (default) ⇒ trust ONLY the real
    TCP peer and ignore X-Forwarded-For entirely. The shipped docker topology (one nginx) sets 1."""
    try:
        return max(0, int(os.environ.get("CHAVRUTA_TRUSTED_PROXY_HOPS", "0")))
    except ValueError:
        return 0


def _client_ip(request: Request) -> str:
    """The rate-limit key: the real client IP, chosen so it can't be spoofed.

    X-Forwarded-For is a client-writable header. The LEFTMOST entries are whatever the client typed;
    only the RIGHTMOST entries are appended by trusted proxies (nginx's `$proxy_add_x_forwarded_for`
    appends the real peer as the last element). So with N trusted proxies, the real client is the
    Nth-from-the-right — never the leftmost. With no trusted proxy (default), XFF is ignored and we
    use the TCP peer, which the client cannot forge. Reading the leftmost value (the old behaviour)
    let an attacker rotate the header to land every request in a fresh bucket and skip the limiter."""
    peer = request.client.host if request.client else "unknown"
    hops = _trusted_proxy_hops()
    if hops <= 0:
        return peer
    fwd = request.headers.get("x-forwarded-for")
    if not fwd:
        return peer
    parts = [p.strip() for p in fwd.split(",") if p.strip()]
    if len(parts) >= hops:
        return parts[-hops]        # the address the outermost trusted proxy saw as its client
    return peer


def _limit_key(request: Request) -> str:
    """Who this request counts against: the signed-in account if we can prove one, else the IP.

    The IP alone was wrong for the first deployment shape where many paying users share an egress
    address — a school. Thirty students behind one NAT shared one 20/min bucket, so three active
    students could 429 the other twenty-seven, and no amount of quota they had paid for would help.

    The account id is taken from the VERIFIED token, never from a client-supplied header: an
    unverified id would be a way to mint a fresh bucket per request and skip the limiter entirely.
    Anything that doesn't verify falls back to the IP (and require_auth 401s it a moment later).
    This does verify the JWT a second time — a local signature check against the cached JWKS, on
    POSTs to two routes that are about to run an LLM, so it is not a cost worth engineering around.
    """
    if sb.enabled():
        sub = sb.verify_sub(_bearer(request.headers.get("authorization")))
        if sub:
            return f"u:{sub}"
    return f"ip:{_client_ip(request)}"


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    metered = request.method == "POST" and path.startswith(_METERED_PREFIXES) and path not in _EXEMPT
    if metered:
        # _limit_key verifies a JWT, and on a cache miss PyJWKClient fetches the JWKS over the network
        # with a blocking urllib call. This middleware is async, so doing that inline would park the
        # event loop and stall every other in-flight request in the worker — not just this one — at
        # exactly the two moments it happens: the first metered request after a restart, and a
        # Supabase key rotation. Steady state is a local signature check and the threadpool hop is
        # noise next to the LLM call this request is about to make.
        key = await run_in_threadpool(_limit_key, request)
        now = time.monotonic()
        if now - _last_sweep[0] > 300:
            _last_sweep[0] = now
            _minute.sweep(now)
            _hour.sweep(now)
        if not _minute.allow(key, now) or not _hour.allow(key, now):
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded — please slow down"},
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


# ── Body-size cap ─────────────────────────────────────────────────────────────
_MAX_BODY = int(os.environ.get("CHAVRUTA_MAX_BODY_BYTES", str(2 * 1024 * 1024)))  # 2 MB default


async def body_size_middleware(request: Request, call_next):
    """Reject oversized bodies before they're read into memory. nginx also caps this, but a
    directly-exposed instance (or a missing nginx limit) needs its own guard."""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_BODY:
        return JSONResponse(status_code=413, content={"detail": "request body too large"})
    return await call_next(request)


# ── Request logging + correlation IDs ─────────────────────────────────────────
async def request_context_middleware(request: Request, call_next):
    """One structured log line per request (method, path, status, ms) with a correlation id that's
    echoed back as X-Request-ID. Until this, the only per-request record was uvicorn's access log —
    no way to tie a user's error report to a server-side line. Health/readiness are skipped so probes
    don't spam the log."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    path = request.url.path
    if path in ("/health", "/ready"):
        return await call_next(request)
    t0 = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        _log.exception("request FAILED rid=%s %s %s (%.0fms)",
                       rid, request.method, path, (time.monotonic() - t0) * 1000)
        raise
    dt = (time.monotonic() - t0) * 1000
    _log.info("rid=%s %s %s -> %s (%.0fms)", rid, request.method, path, response.status_code, dt)
    response.headers["X-Request-ID"] = rid
    return response
