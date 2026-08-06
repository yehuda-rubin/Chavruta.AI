"""Email sending via Resend.

A general-purpose email module for operator-initiated broadcasts (not auth/transactional
emails — those go through Supabase). Follows the project's "no value = inert" convention:
if RESEND_API_KEY is not configured, send_email() returns False and logs a warning rather
than raising an exception, so callers don't need try/except guards.

Resend API: POST https://api.resend.com/emails with Authorization: Bearer <RESEND_API_KEY>.
Body: {"from": ..., "to": ..., "bcc": [...], "subject": ..., "html": ..., "text": ...}.

Privacy: all recipients are sent via BCC, not to/cc. This ensures no recipient sees another
recipient's address — critical for broadcasts to multiple users. The 'to' field in the request
is set to the sender address itself (RESEND_FROM), while the actual recipient list goes in 'bcc'.

Batching: Resend limits the 'to' field to 50 addresses per request. Since we use BCC for the
real recipients, we split the recipient list into batches of 50 and make multiple API calls
sequentially when needed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Lazy import of urllib.request for runtime, but type checkers need to see it
    import urllib.request

_log = logging.getLogger("chavruta.email")

# Resend API limit: max 50 recipients in the 'to' field per request.
# Since we use BCC for actual recipients, we batch at this limit.
_RESEND_BATCH_SIZE = 50


def send_email(to: str | list[str], subject: str, html: str, text: str | None = None) -> bool:
    """Send an email via Resend.

    Args:
        to: Single recipient email address or list of addresses. All recipients are sent via BCC
            for privacy — the 'to' field in the API request is set to the sender address itself.
        subject: Email subject line.
        html: HTML body of the email.
        text: Optional plain text body. If not provided, Resend auto-generates from HTML.

    Returns:
        True if the email was sent successfully (all batches succeeded), False if email is not
        configured (RESEND_API_KEY/RESEND_FROM missing) or if any API call failed.

    The function follows the project's "no value = inert" convention: if Resend is not configured,
    it returns False and logs a warning rather than raising. This allows callers to invoke it
    without try/except guards — a failed send is a non-fatal degradation.
    """
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_addr = os.environ.get("RESEND_FROM", "").strip()
    if not (api_key and from_addr):
        _log.warning("email not configured: RESEND_API_KEY or RESEND_FROM not set")
        return False

    # Normalize recipients to a list, dropping blanks and duplicates (order-preserving) — cheap
    # insurance against a caller passing a raw, unvalidated address list (e.g. straight from
    # list_supabase_user_emails()).
    if isinstance(to, str):
        raw_recipients = [to]
    else:
        raw_recipients = list(to)
    recipients = list(dict.fromkeys(r for r in raw_recipients if r))

    if not recipients:
        _log.warning("no recipients provided")
        return False

    # Lazy import urllib.request to match app.accounts.py pattern
    import urllib.error
    import urllib.request

    # Split recipients into batches of _RESEND_BATCH_SIZE
    batches = [recipients[i:i + _RESEND_BATCH_SIZE]
               for i in range(0, len(recipients), _RESEND_BATCH_SIZE)]

    all_success = True
    for i, batch in enumerate(batches, 1):
        body = {
            "from": from_addr,
            "to": from_addr,  # Sender address in 'to', real recipients in 'bcc' for privacy
            "bcc": batch,
            "subject": subject,
            "html": html,
        }
        if text is not None:
            body["text"] = text

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(body).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    _log.error("Resend API returned non-200 status: %d (batch %d/%d)",
                              resp.status, i, len(batches))
                    all_success = False
        except urllib.error.HTTPError as exc:
            _log.error("Resend API HTTP error: %d %s (batch %d/%d)",
                      exc.code, exc.reason or "", i, len(batches))
            # Try to read response body for more context
            try:
                body_bytes = exc.read()
                if body_bytes:
                    _log.error("Response body: %s", body_bytes.decode("utf-8", errors="replace")[:500])
            except Exception:
                pass
            all_success = False
        except Exception as exc:
            _log.error("Resend API request failed (batch %d/%d): %s",
                      i, len(batches), exc.__class__.__name__)
            all_success = False

    if all_success:
        _log.info("email sent successfully to %d recipient(s) in %d batch(es)",
                  len(recipients), len(batches))
    else:
        _log.warning("email send completed with failures (%d recipient(s), %d batch(es))",
                     len(recipients), len(batches))

    return all_success
