"""Chavruta.AI — Multi-Provider Email Pool (Brevo + Amazon SES Hybrid).

Dispatches authentication and transactional emails (such as Supabase Auth sign-up
confirmations and password resets) with automatic waterfall routing and failover:
1. Primary (0 ₪): Brevo API (up to 300 free emails per day).
2. Overflow / Backup: Amazon SES (10 cents per 1,000 emails, capped via AWS Budget at $1/month).
3. Optional Fallback: Resend API (if configured).

Follows project conventions:
- "no value = inert": only configured providers are active.
- Pure Python standard library (urllib.request, smtplib, hmac, hashlib) without extra dependencies.
- Localized Hebrew email templates with RTL layout matching Chavruta.AI branding.
"""

from __future__ import annotations

import base64
import email.message
import hashlib
import hmac
import json
import logging
import os
import smtplib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

_log = logging.getLogger("chavruta.email_pool")

DEFAULT_FROM = os.environ.get("EMAIL_FROM", "Chavruta.AI <auth@chavrutaai.org>")


class EmailProvider(ABC):
    """Abstract base class for email providers in the pool."""

    def __init__(self, name: str, daily_limit: int, from_addr: str = ""):
        self.name = name
        self.daily_limit = daily_limit
        self.from_addr = from_addr or DEFAULT_FROM

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials and sender are present in environment."""
        pass

    @abstractmethod
    def send(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        """Send an email to a single recipient. Returns True on success, False on error."""
        pass


class BrevoProvider(EmailProvider):
    """Brevo (Sendinblue) API v3 Provider (Free tier: 300 emails/day)."""

    def __init__(self, daily_limit: int = 295):  # Safety buffer before hard 300 limit
        from_addr = os.environ.get("BREVO_FROM", "").strip() or DEFAULT_FROM
        super().__init__(name="brevo", daily_limit=daily_limit, from_addr=from_addr)

    def is_configured(self) -> bool:
        return bool(os.environ.get("BREVO_API_KEY", "").strip() and self.from_addr)

    def _parse_sender(self) -> dict[str, str]:
        addr = self.from_addr
        if "<" in addr and addr.endswith(">"):
            name, email_part = addr.split("<", 1)
            return {"name": name.strip(), "email": email_part[:-1].strip()}
        return {"name": "Chavruta.AI", "email": addr.strip()}

    def send(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        api_key = os.environ.get("BREVO_API_KEY", "").strip()
        if not api_key:
            return False

        body: dict[str, Any] = {
            "sender": self._parse_sender(),
            "to": [{"email": to.strip()}],
            "subject": subject,
            "htmlContent": html,
        }
        if text:
            body["textContent"] = text

        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            method="POST",
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Chavruta-Email/1.0",
            },
            data=json.dumps(body).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if 200 <= resp.status < 300:
                    return True
                _log.warning("Brevo returned status %d", resp.status)
                return False
        except urllib.error.HTTPError as exc:
            _log.warning("Brevo HTTP error %d: %s", exc.code, exc.reason)
            return False
        except Exception as exc:
            _log.warning("Brevo send failed: %s", exc)
            return False


class AmazonSESProvider(EmailProvider):
    """Amazon SES Provider (Overflow/Backup). Supports SMTP or HTTPS REST API.

    Cost: $0.10 per 1,000 emails. Capped via AWS Budget at $1.00/month.
    """

    def __init__(self, daily_limit: int = 1000):
        from_addr = os.environ.get("AWS_SES_FROM", "").strip() or DEFAULT_FROM
        super().__init__(name="amazon_ses", daily_limit=daily_limit, from_addr=from_addr)

    def is_configured(self) -> bool:
        # Check either SMTP credentials or AWS API credentials
        smtp_configured = bool(
            os.environ.get("AWS_SES_SMTP_HOST", "").strip()
            and os.environ.get("AWS_SES_SMTP_USER", "").strip()
            and os.environ.get("AWS_SES_SMTP_PASSWORD", "").strip()
            and self.from_addr
        )
        return smtp_configured

    def _parse_sender_email(self) -> tuple[str, str]:
        addr = self.from_addr
        if "<" in addr and addr.endswith(">"):
            name, email_part = addr.split("<", 1)
            return name.strip(), email_part[:-1].strip()
        return "Chavruta.AI", addr.strip()

    def send(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        host = os.environ.get("AWS_SES_SMTP_HOST", "").strip()
        port = int(os.environ.get("AWS_SES_SMTP_PORT", "587"))
        user = os.environ.get("AWS_SES_SMTP_USER", "").strip()
        password = os.environ.get("AWS_SES_SMTP_PASSWORD", "").strip()

        if not (host and user and password):
            return False

        from_name, from_email = self._parse_sender_email()

        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to.strip()

        if text:
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(html, subtype="html")

        try:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            return True
        except Exception as exc:
            _log.warning("Amazon SES SMTP send failed: %s", exc)
            return False


class ResendProvider(EmailProvider):
    """Resend API Provider (Optional additional fallback: 100 emails/day)."""

    def __init__(self, daily_limit: int = 95):
        from_addr = os.environ.get("RESEND_FROM", "").strip() or DEFAULT_FROM
        super().__init__(name="resend", daily_limit=daily_limit, from_addr=from_addr)

    def is_configured(self) -> bool:
        return bool(os.environ.get("RESEND_API_KEY", "").strip() and self.from_addr)

    def send(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        api_key = os.environ.get("RESEND_API_KEY", "").strip()
        if not api_key:
            return False

        body: dict[str, Any] = {
            "from": self.from_addr,
            "to": [to.strip()],
            "subject": subject,
            "html": html,
        }
        if text:
            body["text"] = text

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "curl/8.5.0",  # Cloudflare compatibility
            },
            data=json.dumps(body).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if 200 <= resp.status < 300:
                    return True
                _log.warning("Resend returned status %d", resp.status)
                return False
        except Exception as exc:
            _log.warning("Resend send failed: %s", exc)
            return False


class EmailPool:
    """Manages the hybrid email pool (Amazon SES / Brevo / Resend) with quota tracking."""

    def __init__(self, providers: list[EmailProvider] | None = None):
        self._lock = threading.Lock()
        if providers is not None:
            self._providers = providers
        else:
            primary = os.environ.get("EMAIL_PRIMARY_PROVIDER", "amazon_ses").strip().lower()
            if primary == "brevo":
                self._providers = [
                    BrevoProvider(),      # Primary (Free 300/day)
                    AmazonSESProvider(),  # Overflow / Backup
                    ResendProvider(),     # 3rd fallback
                ]
            else:
                self._providers = [
                    AmazonSESProvider(),  # Primary (Verified & Active)
                    BrevoProvider(),      # Secondary / Overflow
                    ResendProvider(),     # 3rd fallback
                ]
        # In-memory tracking: { "YYYY-MM-DD": { "provider_name": count } }
        self._usage: dict[str, dict[str, int]] = {}

    def _get_today_key(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _get_usage(self, provider_name: str, today: str) -> int:
        return self._usage.get(today, {}).get(provider_name, 0)

    def _increment_usage(self, provider_name: str, today: str) -> None:
        if today not in self._usage:
            self._usage = {today: {}}
        day_dict = self._usage[today]
        day_dict[provider_name] = day_dict.get(provider_name, 0) + 1

    def get_status(self) -> list[dict[str, Any]]:
        """Return real-time configuration and usage metrics for all providers."""
        today = self._get_today_key()
        with self._lock:
            status = []
            for p in self._providers:
                configured = p.is_configured()
                used = self._get_usage(p.name, today)
                status.append({
                    "name": p.name,
                    "configured": configured,
                    "daily_limit": p.daily_limit,
                    "used_today": used,
                    "remaining_today": max(0, p.daily_limit - used) if configured else 0,
                })
            return status

    def send(
        self,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> tuple[bool, str]:
        """Send an email using Waterfall strategy: Brevo first, SES on overflow or failure.

        Returns:
            (True, provider_name) on success.
            (False, "email_daily_quota_exhausted") if all active providers failed or exceeded quotas.
        """
        to = to.strip()
        if not to:
            return False, "recipient_empty"

        today = self._get_today_key()

        with self._lock:
            active_providers = [p for p in self._providers if p.is_configured()]

        if not active_providers:
            _log.warning("No email providers configured in EmailPool")
            return False, "no_providers_configured"

        # Separate candidates with quota remaining from exhausted ones
        candidates: list[EmailProvider] = []
        with self._lock:
            for p in active_providers:
                used = self._get_usage(p.name, today)
                if used < p.daily_limit:
                    candidates.append(p)

        if not candidates:
            _log.warning("All email providers reached their daily limit for today (%s)", today)
            # Try active providers anyway in case provider limit is higher than local buffer
            candidates = list(active_providers)

        for provider in candidates:
            _log.info("Sending email to %s via %s", to, provider.name)
            success = provider.send(to=to, subject=subject, html=html, text=text)
            if success:
                with self._lock:
                    self._increment_usage(provider.name, today)
                _log.info("Email delivered successfully via %s to %s", provider.name, to)
                return True, provider.name

            _log.warning("Provider %s failed to send email to %s; falling back to next provider...", provider.name, to)

        return False, "email_daily_quota_exhausted"


# Singleton instance
pool = EmailPool()


# --- URL Link Construction & Webhook Security ---

def build_verify_link(
    site_url: str,
    token_hash: str,
    action_type: str,
    redirect_to: str = "",
) -> str:
    """Build the Supabase email action verification URL.

    The URL format is:
    <SITE_URL>/auth/v1/verify?token=<token_hash>&type=<action_type>&redirect_to=<redirect_to>
    Crucial: parameter 'token' takes the SHA256 'token_hash', NOT the 6-digit OTP token!
    """
    base = site_url.rstrip("/")
    if not base.endswith("/auth/v1"):
        endpoint = f"{base}/auth/v1/verify"
    else:
        endpoint = f"{base}/verify"

    params = {
        "token": token_hash,
        "type": action_type,
    }
    if redirect_to:
        params["redirect_to"] = redirect_to

    return f"{endpoint}?{urllib.parse.urlencode(params)}"


def verify_supabase_hook(
    raw_body: bytes,
    headers: dict[str, str],
    secret: str,
) -> bool:
    """Verify incoming Supabase Send Email Auth Hook signature (Standard Webhooks HMAC-SHA256).

    Headers required:
    - webhook-id
    - webhook-timestamp
    - webhook-signature (formatted as 'v1,<base64_sig>')
    """
    if not secret:
        return False

    # Lowercase header lookup
    hdr = {k.lower(): v for k, v in headers.items()}
    msg_id = hdr.get("webhook-id", "")
    msg_time = hdr.get("webhook-timestamp", "")
    signatures = hdr.get("webhook-signature", "").split(" ")

    if not (msg_id and msg_time and signatures):
        return False

    # Replay attack prevention: verify timestamp within 5 minutes (300 seconds)
    try:
        ts = int(msg_time)
        if abs(time.time() - ts) > 300:
            _log.warning("Webhook timestamp out of allowed 5-minute window: %d vs %d", ts, int(time.time()))
            return False
    except ValueError:
        return False

    # Normalize secret
    clean_secret = secret.strip()
    for prefix in ("v1,whsec_", "whsec_", "v1,"):
        if clean_secret.startswith(prefix):
            clean_secret = clean_secret[len(prefix):]

    try:
        secret_bytes = base64.b64decode(clean_secret)
    except Exception:
        _log.warning("Invalid base64 in SUPABASE_AUTH_HOOK_SECRET")
        return False

    to_sign = f"{msg_id}.{msg_time}.".encode("utf-8") + raw_body
    computed_digest = hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    computed_sig = base64.b64encode(computed_digest).decode("ascii")
    expected_v1 = f"v1,{computed_sig}"

    return any(hmac.compare_digest(expected_v1, s.strip()) for s in signatures if s.strip())


# --- Localized Templates (Hebrew & English) ---

def render_auth_email(
    action_type: str,
    action_url: str,
    token: str | None = None,
    lang: str = "he",
) -> tuple[str, str, str]:
    """Render localized HTML and text templates for Supabase Auth emails."""
    if token in ("he", "en") and lang == "he":
        lang = token
        token = None

    is_en = (lang or "").startswith("en")

    if is_en:
        if action_type == "recovery":
            subject = "Reset your password — Chavruta AI"
            title = "Reset Your Password"
            lead = "We received a request to reset your password for your Chavruta AI account."
            action_label = "Reset Password"
            note = "If you did not request a password reset, you can safely ignore this email."
        elif action_type == "signup":
            subject = "Welcome to Chavruta AI — Confirm your email"
            title = "Welcome to Chavruta AI!"
            lead = "Thank you for signing up for Chavruta AI. Please confirm your email address to activate your account and start learning."
            action_label = "Confirm Email"
            note = "If you did not create an account, you can safely ignore this email."
        elif action_type == "magiclink":
            subject = "Your sign-in link — Chavruta AI"
            title = "Sign In to Chavruta AI"
            lead = "Click the button below to sign in directly to your Chavruta AI account."
            action_label = "Sign In"
            note = "This link is valid for a limited time."
        else:
            subject = "Message from Chavruta AI"
            title = "Verify Action"
            lead = "Verification is required to complete the requested action on your account."
            action_label = "Continue"
            note = "If you did not perform this action, please contact support."

        otp_block = ""
        otp_text = ""
        if token:
            otp_block = f"""
        <div style="background-color: #f1f5f9; border-radius: 8px; padding: 12px; margin: 20px 0; text-align: center;">
            <p style="margin: 0 0 6px 0; font-size: 13px; color: #475569;">One-time verification code (OTP):</p>
            <span style="font-family: monospace; font-size: 22px; font-weight: bold; letter-spacing: 4px; color: #1e293b;">{token}</span>
        </div>
            """
            otp_text = f"\nOne-time verification code (OTP): {token}\n"

        html = f"""<!DOCTYPE html>
<html dir="ltr" lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 40px 16px; direction: ltr; text-align: left;">
    <div style="max-width: 540px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 36px 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <div style="text-align: center; margin-bottom: 24px;">
            <h1 style="color: #1e3a8a; font-size: 24px; font-weight: 700; margin: 0;">Chavruta AI</h1>
            <p style="color: #64748b; font-size: 13px; margin: 4px 0 0 0;">Source-grounded AI for the Jewish bookshelf</p>
        </div>
        <div style="border-top: 1px solid #f1f5f9; margin-bottom: 24px;"></div>
        
        <h2 style="color: #0f172a; font-size: 20px; font-weight: 600; margin: 0 0 12px 0;">{title}</h2>
        <p style="color: #334155; font-size: 15px; line-height: 1.6; margin: 0 0 20px 0;">{lead}</p>
        
        {otp_block}
        
        <div style="text-align: center; margin: 28px 0;">
            <a href="{action_url}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 10px; font-weight: 600; font-size: 15px; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);">
                {action_label}
            </a>
        </div>
        
        <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin: 24px 0 0 0; border-top: 1px solid #f1f5f9; padding-top: 16px;">
            {note}
            <br>
            If the button does not work, copy and paste this link into your browser:
            <br>
            <a href="{action_url}" style="color: #2563eb; word-break: break-all; font-size: 12px;">{action_url}</a>
        </p>
    </div>
</body>
</html>"""

        text = f"""{title}

{lead}
{otp_text}
Action link:
{action_url}

{note}
Chavruta AI Team
"""
        return subject, html, text

    # Hebrew (default)
    if action_type == "recovery":
        subject = "איפוס סיסמה — חברותא.AI"
        title = "איפוס סיסמה"
        lead = "קיבלנו בקשה לאיפוס הסיסמה עבור חשבונך ב-Chavruta.AI."
        action_label = "לחץ כאן לאיפוס הסיסמה"
        note = "אם לא ביקשת לאפס את הסיסמה, תוכל להתעלם ממייל זה בבטחה."
    elif action_type == "signup":
        subject = "ברוכים הבאים לחברותא.AI — אימות כתובת מייל"
        title = "ברוכים הבאים לחברותא!"
        lead = "תודה שנרשמת ל-Chavruta.AI. אנא אמת את כתובת המייל שלך כדי להפעיל את החשבון ולהתחיל ללמוד."
        action_label = "הפעלת החשבון ואימות המייל"
        note = "אם לא נרשמת לשירות, תוכל להתעלם ממייל זה."
    elif action_type == "magiclink":
        subject = "קישור כניסה — חברותא.AI"
        title = "כניסה לחשבון"
        lead = "לחץ על הכפתור למטה כדי להיכנס ישירות לחשבונך."
        action_label = "כניסה לחברותא"
        note = "הקישור תקף לזמן מוגבל."
    else:
        subject = "הודעה מ-Chavruta.AI"
        title = "אימות פעולה"
        lead = "נדרש אימות כדי להשלים את הפעולה המבוקשת בחשבונך."
        action_label = "לחץ להמשך"
        note = "אם לא ביצעת פעולה זו, פנה לתמיכה."

    otp_block = ""
    otp_text = ""
    if token:
        otp_block = f"""
        <div style="background-color: #f1f5f9; border-radius: 8px; padding: 12px; margin: 20px 0; text-align: center;">
            <p style="margin: 0 0 6px 0; font-size: 13px; color: #475569;">קוד אימות חד-פעמי (OTP):</p>
            <span style="font-family: monospace; font-size: 22px; font-weight: bold; letter-spacing: 4px; color: #1e293b;">{token}</span>
        </div>
        """
        otp_text = f"\nקוד אימות חד-פעמי (OTP): {token}\n"

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 40px 16px; direction: rtl; text-align: right;">
    <div style="max-width: 540px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 36px 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <div style="text-align: center; margin-bottom: 24px;">
            <h1 style="color: #1e3a8a; font-size: 24px; font-weight: 700; margin: 0;">חברותא.AI</h1>
            <p style="color: #64748b; font-size: 13px; margin: 4px 0 0 0;">בינה מלאכותית מבוססת מקורות לארון הספרים היהודי</p>
        </div>
        <div style="border-top: 1px solid #f1f5f9; margin-bottom: 24px;"></div>
        
        <h2 style="color: #0f172a; font-size: 20px; font-weight: 600; margin: 0 0 12px 0;">{title}</h2>
        <p style="color: #334155; font-size: 15px; line-height: 1.6; margin: 0 0 20px 0;">{lead}</p>
        
        {otp_block}
        
        <div style="text-align: center; margin: 28px 0;">
            <a href="{action_url}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 10px; font-weight: 600; font-size: 15px; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);">
                {action_label}
            </a>
        </div>
        
        <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin: 24px 0 0 0; border-top: 1px solid #f1f5f9; padding-top: 16px;">
            {note}
            <br>
            אם הכפתור לא עובד, ניתן להעתיק ולהדביק את הקישור הבא בדפדפן:
            <br>
            <a href="{action_url}" style="color: #2563eb; word-break: break-all; font-size: 12px;">{action_url}</a>
        </p>
    </div>
</body>
</html>"""

    text = f"""{title}

{lead}
{otp_text}
קישור לפעולה:
{action_url}

{note}
צוות Chavruta.AI
"""
    return subject, html, text
