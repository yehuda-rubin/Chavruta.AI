"""Email sending via Resend (app/email.py).

Pinned: send_email() follows the "no value = inert" convention — returns False when not configured
rather than raising. Recipients are sent via BCC for privacy, with batching at 50 recipients per API
call (Resend's limit). No real HTTP requests in tests — urlopen is mocked.
"""
from __future__ import annotations

import json
import urllib.request

import pytest

import app.email as email


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status
        self._body = b'{"id": "test-email-id"}'

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_send_email_returns_false_when_not_configured(monkeypatch):
    """When RESEND_API_KEY or RESEND_FROM is missing, returns False and logs warning (no exception)."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)
    # urlopen should NOT be called at all
    urlopen_called = False
    def fake_urlopen(*a, **kw):
        nonlocal urlopen_called
        urlopen_called = True
        raise AssertionError("urlopen should not be called when email is not configured")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert email.send_email("test@example.com", "Test", "<p>Test</p>") is False
    assert not urlopen_called


def test_send_email_returns_false_when_only_api_key_set(monkeypatch):
    """When RESEND_FROM is missing even though RESEND_API_KEY is set, returns False."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    urlopen_called = False
    def fake_urlopen(*a, **kw):
        nonlocal urlopen_called
        urlopen_called = True
        raise AssertionError("urlopen should not be called when RESEND_FROM is missing")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert email.send_email("test@example.com", "Test", "<p>Test</p>") is False
    assert not urlopen_called


def test_send_email_uses_bcc_for_recipients(monkeypatch):
    """When configured, the API request uses BCC for recipients and 'to' is the sender address."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    captured_requests = []
    def fake_urlopen(req, timeout=10):
        captured_requests.append(req)
        return _FakeResponse(status=200)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]
    result = email.send_email(recipients, "Test Subject", "<p>Test Body</p>")

    assert result is True
    assert len(captured_requests) == 1
    req = captured_requests[0]

    # Verify request method and URL
    assert req.method == "POST"
    assert req.full_url == "https://api.resend.com/emails"

    # Verify headers
    assert req.headers["Authorization"] == "Bearer test-key"
    # urllib.request.Request normalizes header names to Http-Header-Case — "Content-Type"
    # is actually stored as "Content-type" (only the first letter capitalized).
    assert req.headers["Content-type"] == "application/json"

    # Verify body structure
    body = json.loads(req.data.decode("utf-8"))
    assert body["from"] == "sender@example.com"
    assert body["to"] == "sender@example.com"  # Sender in 'to', not recipients
    assert body["bcc"] == recipients  # Recipients in BCC for privacy
    assert body["subject"] == "Test Subject"
    assert body["html"] == "<p>Test Body</p>"
    assert "text" not in body  # text not provided, so not in body


def test_send_email_includes_text_when_provided(monkeypatch):
    """When text parameter is provided, it's included in the request body."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    captured_requests = []
    def fake_urlopen(req, timeout=10):
        captured_requests.append(req)
        return _FakeResponse(status=200)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = email.send_email("test@example.com", "Test", "<p>HTML</p>", text="Plain text")

    assert result is True
    body = json.loads(captured_requests[0].data.decode("utf-8"))
    assert body["html"] == "<p>HTML</p>"
    assert body["text"] == "Plain text"


def test_send_email_batches_recipients(monkeypatch):
    """When recipient count exceeds 50, the function makes multiple API calls (batching)."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    captured_requests = []
    def fake_urlopen(req, timeout=10):
        captured_requests.append(req)
        return _FakeResponse(status=200)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # 125 recipients = 3 batches (50 + 50 + 25)
    recipients = [f"user{i}@example.com" for i in range(125)]
    result = email.send_email(recipients, "Test", "<p>Test</p>")

    assert result is True
    assert len(captured_requests) == 3

    # Verify each batch
    for i, req in enumerate(captured_requests):
        body = json.loads(req.data.decode("utf-8"))
        expected_batch_size = 50 if i < 2 else 25
        assert len(body["bcc"]) == expected_batch_size
        assert body["to"] == "sender@example.com"


def test_send_email_single_recipient(monkeypatch):
    """Single recipient as string (not list) works correctly."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    captured_requests = []
    def fake_urlopen(req, timeout=10):
        captured_requests.append(req)
        return _FakeResponse(status=200)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = email.send_email("single@example.com", "Test", "<p>Test</p>")

    assert result is True
    body = json.loads(captured_requests[0].data.decode("utf-8"))
    assert body["bcc"] == ["single@example.com"]


def test_send_email_empty_recipients_returns_false(monkeypatch):
    """Empty recipient list returns False without making HTTP requests."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    urlopen_called = False
    def fake_urlopen(*a, **kw):
        nonlocal urlopen_called
        urlopen_called = True
        raise AssertionError("urlopen should not be called with empty recipients")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert email.send_email([], "Test", "<p>Test</p>") is False
    assert not urlopen_called


def test_send_email_http_error_returns_false(monkeypatch):
    """HTTP error from Resend API returns False and logs error."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    def fake_urlopen_error(req, timeout=10):
        import urllib.error
        raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_error)

    result = email.send_email("test@example.com", "Test", "<p>Test</p>")
    assert result is False


def test_send_email_network_error_returns_false(monkeypatch):
    """Network error (e.g. timeout) returns False and logs error."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    def fake_urlopen_error(req, timeout=10):
        raise OSError("network down")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_error)

    result = email.send_email("test@example.com", "Test", "<p>Test</p>")
    assert result is False


def test_send_email_drops_blank_and_duplicate_recipients(monkeypatch):
    """Empty-string entries and duplicates in `to` are filtered before sending (order preserved)."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    captured_requests = []
    def fake_urlopen(req, timeout=10):
        captured_requests.append(req)
        return _FakeResponse(status=200)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = email.send_email(
        ["a@example.com", "", "b@example.com", "a@example.com", ""],
        "Test", "<p>Test</p>",
    )

    assert result is True
    body = json.loads(captured_requests[0].data.decode("utf-8"))
    assert body["bcc"] == ["a@example.com", "b@example.com"]


def test_send_email_all_blank_recipients_returns_false(monkeypatch):
    """A `to` list of only blanks behaves like an empty list — no HTTP call."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    def fake_urlopen(*a, **kw):
        raise AssertionError("urlopen should not be called with only blank recipients")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert email.send_email(["", ""], "Test", "<p>Test</p>") is False


def test_send_email_non_200_status_returns_false(monkeypatch):
    """Resend API returning non-200 status returns False."""
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM", "sender@example.com")

    def fake_urlopen(req, timeout=10):
        return _FakeResponse(status=500)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = email.send_email("test@example.com", "Test", "<p>Test</p>")
    assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
