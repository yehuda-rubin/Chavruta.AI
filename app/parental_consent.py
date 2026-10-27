"""Parental consent for a minor with no school (spec 009 T090, founder decision 2026-10-26, option 2).

A minor who is not linked to a school may send messages only once a parent has consented: an approved,
unrevoked row here, or an active `parent_links` row (`minors.parental_consent_ok` is the one test). The
parent needs no account; they answer on an emailed link.

What is stored, and why that much:
  * `token_hash` / `revoke_token_hash`: SHA-256 of random 32-byte url-safe tokens. The raw tokens exist
    only in the email. A database leak therefore cannot be replayed as a consent or a revocation.
  * `parent_email`: kept only as proof of consent (and for rate limiting). Deleted with the child.
  * `decided_at`, `decision_ip`, `decision_user_agent`: proof of WHEN and from WHERE the parent decided.
  * Nothing about the child is ever put in the email or returned by the public endpoints.

Statuses: pending | approved | declined | expired | revoked. `expired` also marks a request that was
superseded by a newer one (its token must die) or whose email could not be sent. Expiry by time is
applied lazily on read and on decision.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import app.db as db

EXPIRY_DAYS = 7
MAX_PER_HOUR = 3
MAX_PER_DAY = 10
MAX_PER_PARENT_PER_DAY = 3        # one stranger's inbox cannot be used as a mailbox to spam
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,}$")


class ConsentError(Exception):
    """Base. `code` is the API error code, `status` the HTTP status."""
    code = "consent_error"
    status = 400


class InvalidEmail(ConsentError):
    code, status = "invalid_email", 422


class SameAsChild(ConsentError):
    code, status = "same_as_child", 409


class NotApplicable(ConsentError):
    code, status = "not_applicable", 409          # not a minor, or already linked to a school


class AlreadyApproved(ConsentError):
    code, status = "already_approved", 409


class RateLimited(ConsentError):
    code, status = "rate_limited", 429


class SendFailed(ConsentError):
    code, status = "send_failed", 503


class UnknownToken(ConsentError):
    code, status = "not_found", 404


class Expired(ConsentError):
    code, status = "expired", 410


class AlreadyDecided(ConsentError):
    code, status = "already_decided", 409


def _hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def _now_dt() -> datetime:
    return datetime.now(UTC)


def normalize_email(raw: str) -> str:
    e = (raw or "").strip().lower()
    if not _EMAIL_RE.match(e) or len(e) > 320:
        raise InvalidEmail("invalid email address")
    return e


def mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    return (local[:1] + "***@" + domain) if local and domain else ""


def _site_url() -> str:
    return os.environ.get("CHAVRUTA_PUBLIC_URL", "https://chavrutaai.org").rstrip("/")


# ── the email (template: specs/009-school-minors/legal-drafts/parent-consent-he.md, Part B) ─────────
def compose(consent_url: str, revoke_url: str, expires_at: datetime) -> tuple[str, str, str]:
    """(subject, html, text). Transactional: no marketing, no unsubscribe, no child name or address."""
    exp = expires_at.strftime("%d.%m.%Y")
    subject = "אישור הורה לשימוש בחברותא AI"
    lines = [
        "שלום,",
        "מישהו/י שמסר/ה את כתובת המייל שלך ביקש/ה להשתמש בחברותא AI, שירות ללימוד תורה, ומצהיר/ה שאתה/את ההורה או האפוטרופוס שלו/ה.",
        "כדי שהילד/ה יוכל/תוכל להשתמש בשירות נדרש אישור שלך. בלי אישור - לא ישלח/תשלח הודעות.",
        "לקריאת מה מאשרים ולהחלטה:",
        consent_url,
        f"הקישור תקף 7 ימים (עד {exp}). אם לא ביקשת זאת, או שאינך הורה או אפוטרופוס - התעלם/י מהמייל, ושום דבר לא יקרה.",
        "בקצרה: חברותא AI היא תוכנת מחשב, לא רב. אין בה פסיקת הלכה לקטינים. הודעות של קטין נמחקות לאחר 60 יום ולא משמשות לאימון. אין רכישות ושיווק.",
        "לא תהיה לך גישה לשיחות הילד/ה. בהודעה שמעידה על מצוקה תישלח התראה למפעיל, בלי תוכן ההודעה.",
        "אפשר לבטל את האישור בכל עת:",
        revoke_url,
        "(הקישור פעיל לאחר אישור).",
        "שאלות: privacy@chavrutaai.org",
        "חברותא AI",
    ]
    text = "\n\n".join(lines)
    parts = []
    for ln in lines:
        if ln.startswith("http"):
            parts.append(f'<p><a href="{html.escape(ln)}">{html.escape(ln)}</a></p>')
        else:
            parts.append(f"<p>{html.escape(ln)}</p>")
    return subject, '<div dir="rtl" style="font-family:Arial,sans-serif">' + "".join(parts) + "</div>", text


def _send(to: str, subject: str, body_html: str, body_text: str) -> bool:
    """Patched in tests. Goes through the shared provider pool (Brevo / SES / Resend)."""
    from app.email_pool import pool

    ok, _provider = pool.send(to, subject, body_html, body_text)
    return bool(ok)


# ── the child's side ───────────────────────────────────────────────────────────────────────────────
def _expire_due(conn: Any) -> None:
    conn.execute("UPDATE parental_consents SET status='expired' WHERE status='pending' AND expires_at <= ?",
                 (_now_dt().isoformat(),))


def latest(child_id: str) -> dict[str, Any] | None:
    with db._tx(db.get_conn()) as conn:
        _expire_due(conn)
        row = conn.execute(
            "SELECT status, parent_email, sent_at, expires_at FROM parental_consents "
            "WHERE child_owner_id=? ORDER BY id DESC LIMIT 1", (child_id,)).fetchone()
    return dict(row) if row else None


def me_view(child_id: str) -> dict[str, str]:
    """The `/me` object for a minor: status none|pending|approved|declined|expired. A revoked consent is
    reported as `declined` (the UI has no separate state, and the child's next step is the same)."""
    row = latest(child_id)
    if row is None:
        return {"status": "none"}
    status = "declined" if row["status"] == "revoked" else row["status"]
    return {"status": status, "parent_email_masked": mask_email(row["parent_email"]),
            "sent_at": row["sent_at"]}


def request_consent(child_id: str, child_email: str, parent_email: str) -> dict[str, str]:
    """Create a request, superseding any pending one, and email the parent. Raises ConsentError."""
    import app.minors as minors
    import app.orgs as orgs

    email = normalize_email(parent_email)
    if (child_email or "").strip().lower() == email:
        raise SameAsChild("the parent's address must differ from the child's own")
    if not minors.is_minor(child_id) or orgs.membership(child_id):
        raise NotApplicable("parental consent applies to a minor with no school link")
    now = _now_dt()
    token, revoke_tok = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = now + timedelta(days=EXPIRY_DAYS)
    with db._tx(db.get_conn()) as conn:
        _expire_due(conn)
        if conn.execute("SELECT 1 FROM parental_consents WHERE child_owner_id=? AND status='approved'",
                        (child_id,)).fetchone():
            raise AlreadyApproved("already approved")
        hour, day = ((now - timedelta(hours=1)).isoformat(), (now - timedelta(days=1)).isoformat())
        n_hour = conn.execute("SELECT COUNT(*) FROM parental_consents WHERE child_owner_id=? AND sent_at>?",
                              (child_id, hour)).fetchone()[0]
        n_day = conn.execute("SELECT COUNT(*) FROM parental_consents WHERE child_owner_id=? AND sent_at>?",
                             (child_id, day)).fetchone()[0]
        n_parent = conn.execute("SELECT COUNT(*) FROM parental_consents WHERE parent_email=? AND sent_at>?",
                                (email, day)).fetchone()[0]
        if n_hour >= MAX_PER_HOUR or n_day >= MAX_PER_DAY or n_parent >= MAX_PER_PARENT_PER_DAY:
            raise RateLimited("too many consent requests; try again later")
        conn.execute("UPDATE parental_consents SET status='expired' WHERE child_owner_id=? AND status='pending'",
                     (child_id,))                       # the old link must stop working
        rid = conn.execute(
            "INSERT INTO parental_consents (child_owner_id, parent_email, token_hash, revoke_token_hash, "
            "status, sent_at, expires_at) VALUES (?,?,?,?,'pending',?,?)",
            (child_id, email, _hash(token), _hash(revoke_tok), now.isoformat(), expires.isoformat())).lastrowid
    subject, body_html, body_text = compose(f"{_site_url()}/parent-consent/{token}",
                                            f"{_site_url()}/parent-consent/revoke/{revoke_tok}", expires)
    try:
        ok = _send(email, subject, body_html, body_text)
    except Exception:                                   # noqa: BLE001 - a provider error is a 503, not a crash
        ok = False
    if not ok:
        with db._tx(db.get_conn()) as conn:
            conn.execute("UPDATE parental_consents SET status='expired' WHERE id=?", (rid,))
        raise SendFailed("the email could not be sent")
    return {"status": "pending", "sent_at": now.isoformat()}


# ── the parent's side (public; the token is the credential) ────────────────────────────────────────
def _by_token(conn: Any, column: str, token: str) -> Any:
    _expire_due(conn)
    row = conn.execute(f"SELECT * FROM parental_consents WHERE {column}=?", (_hash(token),)).fetchone()
    if row is None:
        raise UnknownToken("unknown link")
    return row


def info(token: str) -> dict[str, str]:
    """What the consent page needs. 404 unknown, 410 expired (or superseded). No child data."""
    with db._tx(db.get_conn()) as conn:
        row = _by_token(conn, "token_hash", token)
    if row["status"] == "expired":
        raise Expired("this link has expired")
    return {"status": row["status"], "expires_at": row["expires_at"]}


def decide(token: str, decision: str, ip: str, user_agent: str) -> dict[str, str]:
    if decision not in ("approve", "decline"):
        raise ValueError("decision must be 'approve' or 'decline'")
    with db._tx(db.get_conn()) as conn:
        row = _by_token(conn, "token_hash", token)
        if row["status"] == "expired":
            raise Expired("this link has expired")
        if row["status"] != "pending":
            raise AlreadyDecided("a decision was already recorded")
        status = "approved" if decision == "approve" else "declined"
        conn.execute("UPDATE parental_consents SET status=?, decided_at=?, decision_ip=?, "
                     "decision_user_agent=? WHERE id=?",
                     (status, _now_dt().isoformat(), (ip or "")[:64], (user_agent or "")[:300], row["id"]))
    return {"status": status}


def revoke(revoke_token: str, ip: str = "", user_agent: str = "") -> dict[str, str]:
    """The parent withdraws consent. Idempotent. The child has no way to call this."""
    with db._tx(db.get_conn()) as conn:
        row = _by_token(conn, "revoke_token_hash", revoke_token)
        if row["status"] == "revoked":
            return {"status": "revoked"}
        if row["status"] not in ("pending", "approved"):
            raise AlreadyDecided("nothing to revoke")
        conn.execute("UPDATE parental_consents SET status='revoked', decided_at=?, decision_ip=?, "
                     "decision_user_agent=? WHERE id=?",
                     (_now_dt().isoformat(), (ip or "")[:64], (user_agent or "")[:300], row["id"]))
    return {"status": "revoked"}
