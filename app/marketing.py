"""Marketing email: who may be mailed, and the one-click withdrawal of that consent.

Consent lives in Supabase `user_metadata` (`marketing_consent`, `marketing_consent_at`), written by the
opt-in checkbox at sign-up and the switch in Settings. Israeli law (Communications Law s.30A) allows an
advertising email only to someone who agreed, and requires a working way to withdraw that agreement in
the same medium. This module is that way: a signed link in every message that clears the flag.

Standard library only, like `accounts.py`. Nothing here sends mail; `scripts/send_product_update.py` does.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

_log = logging.getLogger("chavruta.marketing")

SITE_URL = os.environ.get("CHAVRUTA_PUBLIC_URL", "https://chavrutaai.org").rstrip("/")


# ── Signed withdrawal links ───────────────────────────────────────────────────
def _secret() -> bytes:
    """Empty means "not configured": no link can be made or accepted (fail closed, like the hooks)."""
    return os.environ.get("UNSUBSCRIBE_SECRET", "").strip().encode()


def make_token(user_id: str) -> str:
    """`<b64(user_id)>.<mac>`. The mac covers the id under a fixed label, so a token minted here can
    never be replayed against another HMAC-protected route that uses the same secret."""
    key = _secret()
    if not key or not user_id:
        raise RuntimeError("UNSUBSCRIBE_SECRET is not configured")
    body = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip("=")
    mac = hmac.new(key, b"unsub:" + user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{mac}"


def verify_token(token: str) -> str | None:
    """The user id the token was minted for, or None for anything malformed, altered or unsigned."""
    key = _secret()
    if not key or not token or token.count(".") != 1:
        return None
    body, mac = token.split(".", 1)
    try:
        user_id = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
    except Exception:                       # noqa: BLE001 — any decode failure is simply "invalid"
        return None
    expected = hmac.new(key, b"unsub:" + user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return user_id if user_id and hmac.compare_digest(expected, mac) else None


def unsubscribe_url(user_id: str) -> str:
    return f"{SITE_URL}/account/unsubscribe?t={make_token(user_id)}"


# ── Recipients ────────────────────────────────────────────────────────────────
def has_consent(user: dict) -> bool:
    """True only for an explicit boolean True. A missing key, a string, or null is "did not agree"."""
    return (user.get("user_metadata") or {}).get("marketing_consent") is True


def _admin_headers() -> tuple[str, dict[str, str]] | None:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not (key and url):
        return None
    return url, {"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"}


def list_marketing_recipients() -> list[tuple[str, str]]:
    """(user_id, email) of everyone who opted in, de-duplicated by address. Empty when Supabase is not
    configured: unknown must never turn into "mail everybody"."""
    admin = _admin_headers()
    if admin is None:
        return []
    import urllib.request

    url, headers = admin
    # Minors are never mailed (specs/009-school-minors R11). Read from the age records, not from the
    # JWT: user_metadata is writable by the account holder. Raises if the database cannot be read —
    # an unreadable age table must stop a send, not become "nobody is a minor".
    from app import minors

    minor_ids = minors.minor_owner_ids()
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    page = 1
    while True:
        req = urllib.request.Request(f"{url}/auth/v1/admin/users?page={page}&per_page=1000", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            users = json.loads(resp.read()).get("users", [])
        for u in users:
            email = (u.get("email") or "").strip().lower()
            if u.get("id") and "@" in email and email not in seen and has_consent(u) and not u.get("banned_until") \
                    and u["id"] not in minor_ids:
                seen.add(email)
                out.append((u["id"], email))
        if len(users) < 1000:
            return out
        page += 1


# ── Withdrawing consent ───────────────────────────────────────────────────────
def withdraw_consent(user_id: str) -> bool:
    """Clear the opt-in flag. True when Supabase accepted the change (or the flag was already clear)."""
    admin = _admin_headers()
    if admin is None:
        return False
    import urllib.error
    import urllib.request

    url, headers = admin
    body = json.dumps({"user_metadata": {
        "marketing_consent": False,
        "marketing_consent_at": datetime.now(timezone.utc).isoformat(),
    }}).encode()
    req = urllib.request.Request(f"{url}/auth/v1/admin/users/{user_id}", data=body, method="PUT", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=15)
        _log.info("marketing consent withdrawn for %s", user_id)
        return True
    except urllib.error.HTTPError as exc:
        _log.warning("withdraw_consent failed for %s: HTTP %s", user_id, exc.code)
    except Exception as exc:                # noqa: BLE001
        _log.warning("withdraw_consent errored for %s: %s", user_id, exc.__class__.__name__)
    return False


# ── The two pages the link shows ──────────────────────────────────────────────
_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>הסרה מרשימת הדיוור | חברותא</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f4ff;color:#1a1633;
font:18px/1.7 Heebo,Rubik,system-ui,sans-serif;padding:24px}}main{{max-width:460px;background:#fff;
border:1px solid #e6e2fa;border-radius:28px;padding:36px 32px;text-align:center}}h1{{font-size:26px;margin:0 0 10px}}
p{{margin:0 0 22px;color:#6b6788}}button,a.b{{display:inline-block;font:inherit;font-weight:600;color:#fff;
background:#5b3df5;border:0;border-radius:999px;padding:12px 28px;cursor:pointer;text-decoration:none}}</style>
</head><body><main>{body}</main></body></html>"""


def page_confirm(token: str) -> str:
    return _PAGE.format(body=(
        "<h1>להסיר אותך מרשימת הדיוור?</h1>"
        "<p>לא נשלח לך יותר עדכונים והצעות במייל. מיילים הנוגעים לחשבון, כמו אימות והתחברות, ימשיכו להישלח.</p>"
        f'<form method="post" action="/account/unsubscribe?t={token}"><button type="submit">כן, להסיר</button></form>'
    ))


def page_done() -> str:
    return _PAGE.format(body=(
        "<h1>הוסרת מהרשימה</h1><p>לא נשלח לך עוד עדכונים והצעות במייל. אפשר להצטרף שוב בכל עת מההגדרות באתר.</p>"
        f'<a class="b" href="{SITE_URL}">לחברותא</a>'
    ))


def page_error() -> str:
    return _PAGE.format(body=(
        "<h1>הקישור אינו תקף</h1><p>אפשר להסיר את ההסכמה בעצמך מההגדרות באתר, תחת &quot;עדכונים והצעות במייל&quot;.</p>"
        f'<a class="b" href="{SITE_URL}">לחברותא</a>'
    ))
