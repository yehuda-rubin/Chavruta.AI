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
import logging
import os
import threading
import time
import uuid

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app import auth_supabase as sb

_log = logging.getLogger("chavruta.request")


# ── Auth ──────────────────────────────────────────────────────────────────────
# Two interchangeable modes, both env-gated (Principle II):
#   • Supabase (SUPABASE_URL set)  — a real signed-in user; owner = the verified JWT `sub`.
#   • API key  (CHAVRUTA_API_KEYS) — a shared/service key; owner = a stable hash of the key.
# Neither configured ⇒ open local dev, everyone is the single 'local' user (unchanged).
def _api_keys() -> set[str]:
    """Keys allowed to call the API. Empty ⇒ API-key auth DISABLED."""
    return {k.strip() for k in os.environ.get("CHAVRUTA_API_KEYS", "").split(",") if k.strip()}


_AUTH_EXEMPT = ("/health", "/ready", "/docs", "/openapi.json", "/redoc")


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


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """App-wide gate. In Supabase mode, require a valid access-token JWT and stash the verified user
    id on request.state for current_owner; otherwise fall back to the API-key gate (or open-local)."""
    if request.url.path in _AUTH_EXEMPT:
        return
    if sb.enabled():
        sub = sb.verify_sub(_bearer(authorization))
        if not sub:
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")
        request.state.owner = sub
        return
    require_api_key(request, authorization, x_api_key)


def current_owner(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
    """The identity data is scoped to. Supabase mode ⇒ the verified JWT `sub` (already validated and
    stashed by require_auth). API-key mode ⇒ a stable hash of the presented key (the key itself is
    never stored as an id). Neither configured ⇒ the single 'local' user (unchanged offline behaviour)."""
    if sb.enabled():
        # require_auth verified + stashed the sub on non-exempt paths; exempt paths carry no identity.
        return getattr(request.state, "owner", None) or "local"
    if not _api_keys():
        return "local"
    presented = x_api_key or _bearer(authorization)
    if not presented:
        return "local"
    return "u_" + hashlib.sha256(presented.encode()).hexdigest()[:16]


# ── Rate limiting (per-IP, in-memory sliding window) ──────────────────────────
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
_METERED_PREFIXES = ("/query", "/sessions")   # POST to these drives the LLM
_EXEMPT = ("/health", "/ready")
_last_sweep = [0.0]


def _client_ip(request: Request) -> str:
    # Behind nginx with --proxy-headers, request.client.host is the real client; X-Forwarded-For is
    # the fallback when proxy headers aren't parsed.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    metered = request.method == "POST" and path.startswith(_METERED_PREFIXES) and path not in _EXEMPT
    if metered:
        ip = _client_ip(request)
        now = time.monotonic()
        if now - _last_sweep[0] > 300:
            _last_sweep[0] = now
            _minute.sweep(now)
            _hour.sweep(now)
        if not _minute.allow(ip, now) or not _hour.allow(ip, now):
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
