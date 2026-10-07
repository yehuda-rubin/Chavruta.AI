"""Unit tests for the Multi-Provider Email Pool (app/email_pool.py).

Verifies Brevo, Amazon SES, Waterfall routing, failover, quota tracking,
Standard Webhooks HMAC verification, and URL link construction.
All network calls are strictly mocked (no real HTTP or SMTP connections).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.request
from unittest.mock import MagicMock, patch

try:
    import pytest
except ImportError:
    pytest = None

import app.email_pool as ep


class _FakeHTTPResponse:
    def __init__(self, status: int = 200, body: bytes = b'{"messageId": "msg-123"}'):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- Brevo Provider Tests ---

def test_brevo_unconfigured_returns_false(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    provider = ep.BrevoProvider()
    assert not provider.is_configured()
    assert provider.send("test@example.com", "Test", "<p>Hi</p>") is False


def test_brevo_successful_send(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-key")
    monkeypatch.setenv("BREVO_FROM", "Chavruta <auth@chavrutaai.org>")

    recorded_request = None

    def fake_urlopen(req, timeout=12):
        nonlocal recorded_request
        recorded_request = req
        return _FakeHTTPResponse(status=201)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = ep.BrevoProvider()
    assert provider.is_configured()
    ok = provider.send("user@example.com", "Welcome", "<p>Welcome to Chavruta</p>")

    assert ok is True
    assert recorded_request is not None
    assert recorded_request.full_url == "https://api.brevo.com/v3/smtp/email"
    assert recorded_request.headers["Api-key"] == "test-brevo-key"
    payload = json.loads(recorded_request.data.decode("utf-8"))
    assert payload["to"] == [{"email": "user@example.com"}]
    assert payload["subject"] == "Welcome"


def test_brevo_failure_returns_false(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-brevo-key")

    def fake_urlopen(req, timeout=12):
        return _FakeHTTPResponse(status=400)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = ep.BrevoProvider()
    assert provider.send("user@example.com", "Test", "<p>Error</p>") is False


# --- Amazon SES Provider Tests ---

def test_amazon_ses_unconfigured_returns_false(monkeypatch):
    monkeypatch.delenv("AWS_SES_SMTP_HOST", raising=False)
    monkeypatch.delenv("AWS_SES_SMTP_USER", raising=False)
    monkeypatch.delenv("AWS_SES_SMTP_PASSWORD", raising=False)

    provider = ep.AmazonSESProvider()
    assert not provider.is_configured()
    assert provider.send("user@example.com", "Test", "<p>Hi</p>") is False


def test_amazon_ses_successful_send(monkeypatch):
    monkeypatch.setenv("AWS_SES_SMTP_HOST", "email-smtp.eu-central-1.amazonaws.com")
    monkeypatch.setenv("AWS_SES_SMTP_PORT", "587")
    monkeypatch.setenv("AWS_SES_SMTP_USER", "smtp_user")
    monkeypatch.setenv("AWS_SES_SMTP_PASSWORD", "smtp_pass")
    monkeypatch.setenv("AWS_SES_FROM", "Chavruta <auth@chavrutaai.org>")

    provider = ep.AmazonSESProvider()
    assert provider.is_configured()

    mock_smtp_instance = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_instance):
        mock_smtp_instance.__enter__.return_value = mock_smtp_instance
        ok = provider.send("user@example.com", "Subject", "<p>Body</p>")

        assert ok is True
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("smtp_user", "smtp_pass")
        mock_smtp_instance.send_message.assert_called_once()


# --- EmailPool Waterfall & Failover Tests ---

def test_pool_empty_unconfigured():
    pool = ep.EmailPool(providers=[])
    ok, reason = pool.send("user@example.com", "Test", "<p>Test</p>")
    assert ok is False
    assert reason == "no_providers_configured"


def test_pool_primary_provider_selection(monkeypatch):
    monkeypatch.setenv("EMAIL_PRIMARY_PROVIDER", "amazon_ses")
    pool_ses = ep.EmailPool()
    assert pool_ses._providers[0].name == "amazon_ses"

    monkeypatch.setenv("EMAIL_PRIMARY_PROVIDER", "brevo")
    pool_brevo = ep.EmailPool()
    assert pool_brevo._providers[0].name == "brevo"


def test_pool_waterfall_uses_brevo_first():
    mock_brevo = MagicMock(spec=ep.EmailProvider)
    mock_brevo.name = "brevo"
    mock_brevo.daily_limit = 295
    mock_brevo.is_configured.return_value = True
    mock_brevo.send.return_value = True

    mock_ses = MagicMock(spec=ep.EmailProvider)
    mock_ses.name = "amazon_ses"
    mock_ses.daily_limit = 1000
    mock_ses.is_configured.return_value = True

    pool = ep.EmailPool(providers=[mock_brevo, mock_ses])
    ok, provider = pool.send("user@example.com", "Subject", "<p>HTML</p>")

    assert ok is True
    assert provider == "brevo"
    mock_brevo.send.assert_called_once()
    mock_ses.send.assert_not_called()


def test_pool_failover_to_ses_when_brevo_fails():
    mock_brevo = MagicMock(spec=ep.EmailProvider)
    mock_brevo.name = "brevo"
    mock_brevo.daily_limit = 295
    mock_brevo.is_configured.return_value = True
    mock_brevo.send.return_value = False  # Brevo fails (e.g. 550 Quota)

    mock_ses = MagicMock(spec=ep.EmailProvider)
    mock_ses.name = "amazon_ses"
    mock_ses.daily_limit = 1000
    mock_ses.is_configured.return_value = True
    mock_ses.send.return_value = True  # SES succeeds

    pool = ep.EmailPool(providers=[mock_brevo, mock_ses])
    ok, provider = pool.send("user@example.com", "Subject", "<p>HTML</p>")

    assert ok is True
    assert provider == "amazon_ses"
    mock_brevo.send.assert_called_once()
    mock_ses.send.assert_called_once()


def test_pool_switches_to_ses_when_brevo_limit_reached():
    mock_brevo = MagicMock(spec=ep.EmailProvider)
    mock_brevo.name = "brevo"
    mock_brevo.daily_limit = 2  # Low limit for testing
    mock_brevo.is_configured.return_value = True
    mock_brevo.send.return_value = True

    mock_ses = MagicMock(spec=ep.EmailProvider)
    mock_ses.name = "amazon_ses"
    mock_ses.daily_limit = 1000
    mock_ses.is_configured.return_value = True
    mock_ses.send.return_value = True

    pool = ep.EmailPool(providers=[mock_brevo, mock_ses])

    # 1st email -> Brevo
    ok, p = pool.send("u1@example.com", "S", "H")
    assert ok and p == "brevo"

    # 2nd email -> Brevo
    ok, p = pool.send("u2@example.com", "S", "H")
    assert ok and p == "brevo"

    # 3rd email -> Brevo quota (2) reached, automatically routed to Amazon SES!
    ok, p = pool.send("u3@example.com", "S", "H")
    assert ok is True
    assert p == "amazon_ses"


def test_pool_exhausted_returns_error_string():
    mock_brevo = MagicMock(spec=ep.EmailProvider)
    mock_brevo.name = "brevo"
    mock_brevo.daily_limit = 1
    mock_brevo.is_configured.return_value = True
    mock_brevo.send.return_value = False

    pool = ep.EmailPool(providers=[mock_brevo])
    ok, reason = pool.send("u@example.com", "S", "H")

    assert ok is False
    assert reason == "email_daily_quota_exhausted"


# --- Webhook Signature Verification Tests ---

def test_verify_supabase_hook_valid_signature():
    secret = "whsec_" + base64.b64encode(b"my-secret-key-32-bytes-long-here!!").decode("ascii")
    raw_body = b'{"user":{"email":"test@example.com"},"email_data":{"token_hash":"abc"}}'
    msg_id = "msg_test_123"
    msg_time = str(int(time.time()))

    # Compute expected signature
    secret_bytes = base64.b64decode(secret.replace("whsec_", ""))
    to_sign = f"{msg_id}.{msg_time}.".encode("utf-8") + raw_body
    sig = base64.b64encode(hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()).decode("ascii")

    headers = {
        "webhook-id": msg_id,
        "webhook-timestamp": msg_time,
        "webhook-signature": f"v1,{sig}",
    }

    assert ep.verify_supabase_hook(raw_body, headers, secret) is True


def test_verify_supabase_hook_invalid_signature():
    secret = "whsec_" + base64.b64encode(b"real-secret-key").decode("ascii")
    raw_body = b'{"hello":"world"}'
    headers = {
        "webhook-id": "msg_123",
        "webhook-timestamp": str(int(time.time())),
        "webhook-signature": "v1,invalidBase64Signature==",
    }
    assert ep.verify_supabase_hook(raw_body, headers, secret) is False


def test_verify_supabase_hook_expired_timestamp():
    secret = "whsec_" + base64.b64encode(b"real-secret-key").decode("ascii")
    raw_body = b'{"hello":"world"}'
    # Timestamp from 10 minutes ago (> 300 seconds)
    expired_time = str(int(time.time()) - 600)
    headers = {
        "webhook-id": "msg_123",
        "webhook-timestamp": expired_time,
        "webhook-signature": "v1,someSignature",
    }
    assert ep.verify_supabase_hook(raw_body, headers, secret) is False


# --- Link Construction & Template Tests ---

def test_build_verify_link_uses_token_hash():
    link = ep.build_verify_link(
        site_url="https://chavrutaai.org",
        token_hash="hash123456",
        action_type="signup",
        redirect_to="https://chavrutaai.org/welcome",
    )
    assert link.startswith("https://chavrutaai.org/auth/v1/verify?")
    assert "token=hash123456" in link
    assert "type=signup" in link
    assert "redirect_to=https%3A%2F%2Fchavrutaai.org%2Fwelcome" in link


def test_render_auth_email_contains_hebrew_and_link():
    subject, html, text = ep.render_auth_email(
        action_type="recovery",
        action_url="https://chavrutaai.org/auth/v1/verify?token=abc",
        token="654321",
    )
    assert "איפוס סיסמה" in subject
    assert "איפוס סיסמה" in html
    assert "654321" in html
    assert "https://chavrutaai.org/auth/v1/verify?token=abc" in html
    assert "direction: rtl" in html
