"""Green Invoice / Morning adapter — issues the legally-required tax invoice/receipt off a charge.

API contract per developers.morning.co (verified 2026-07-19):
  auth     POST https://api.morning.co/idp/v1/oauth/token  (client_credentials) → {accessToken, expiresAt}
  issue    POST https://api.greeninvoice.co.il/api/v1/documents  (Bearer)  type 320 = חשבונית מס/קבלה
  credit   the same endpoint with type 330 = חשבונית זיכוי, issued when a charge is refunded
  the מספר-הקצאה (allocation number) is handled server-side once the Tax-Authority linkage is set up
  in the dashboard — no request field needed.

Best-effort: if invoicing isn't configured or a call fails, we log and move on — a failed invoice must
never fail the payment webhook (the money already moved). Issue the invoice, but don't gate on it.
"""

from __future__ import annotations

import logging
import os
import time

_log = logging.getLogger("chavruta.billing.greeninvoice")

_TIMEOUT = 30
_token_cache: dict = {"token": None, "exp": 0.0}


def _sandbox() -> bool:
    return os.environ.get("GREENINVOICE_MODE", "sandbox").lower() != "production"


def _token_url() -> str:
    return ("https://api.morning.co/idp/v1/oauth/token" if not _sandbox()
            else "https://api.sandbox.morning.dev/idp/v1/oauth/token")


def _api_base() -> str:
    return ("https://api.greeninvoice.co.il/api/v1" if not _sandbox()
            else "https://sandbox.d.greeninvoice.co.il/api/v1")


def _client_id() -> str:
    return os.environ.get("GREENINVOICE_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("GREENINVOICE_CLIENT_SECRET", "").strip()


def enabled() -> bool:
    return bool(_client_id() and _client_secret())


def _token(now: float) -> str:
    """A cached OAuth2 access token, refreshed ~60s before it expires."""
    import requests

    if _token_cache["token"] and now < _token_cache["exp"] - 60:
        return _token_cache["token"]
    r = requests.post(_token_url(), json={
        "grant_type": "client_credentials",
        "client_id": _client_id(),
        "client_secret": _client_secret(),
    }, timeout=_TIMEOUT)
    r.raise_for_status()
    body = r.json()
    _token_cache["token"] = body["accessToken"]
    _token_cache["exp"] = float(body.get("expiresAt", now + 3600))
    return _token_cache["token"]


def issue_receipt(*, email: str, name: str, amount: float, description: str,
                  now: float | None = None) -> dict | None:
    """Issue a חשבונית מס/קבלה (type 320) for a card charge. Returns the created document (with its
    PDF url) or None on failure — never raises, so a webhook can call it best-effort."""
    if not enabled():
        return None
    import requests

    now = now if now is not None else time.time()
    date = time.strftime("%Y-%m-%d", time.gmtime(now))
    try:
        token = _token(now)
        body = {
            "type": 320,
            "lang": "he",
            "currency": "ILS",
            "date": date,
            "client": {"name": name or email or "לקוח", "emails": [email] if email else [], "add": False},
            "income": [{"description": description, "quantity": 1, "price": amount,
                        "currency": "ILS", "vatType": 1}],   # 1 = price includes VAT
            "payment": [{"date": date, "type": 3, "price": amount, "currency": "ILS",
                         "dealType": 6}],                    # 3 = credit card, 6 = recurring
        }
        r = requests.post(f"{_api_base()}/documents", json=body,
                          headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        r.raise_for_status()
        doc = r.json()
        _log.info("issued invoice %s (doc %s) for %s", doc.get("number"), doc.get("id"), email)
        return doc
    except Exception as exc:                # noqa: BLE001 — invoicing must not break the payment flow
        _log.exception("green-invoice issue failed for %s: %s", email, exc.__class__.__name__)
        return None


# Green Invoice document types. 320 is the חשבונית מס/קבלה issued on a charge; 330 is the חשבונית
# זיכוי that reverses one. Overridable because it is the one number here that would silently produce
# the WRONG KIND of tax document if their catalogue ever differs from this.
CREDIT_NOTE_TYPE = 330


def issue_credit_note(*, email: str, name: str, amount: float, description: str,
                      now: float | None = None) -> dict | None:
    """Issue a חשבונית זיכוי for a refund. Returns the document, or None on failure.

    A refund is not the erasure of a charge; it is a second event that reverses it, and the books
    have to carry a document for each. Refunding money without issuing the credit note leaves the
    original tax invoice standing for income that was given back.

    Called AFTER the money has actually moved, and never raises, for the same reason issue_receipt()
    doesn't: the refund is already done by then, so a failure here is a document to chase, not a
    reason to report the refund as failed. The ledger row is written either way.

    ⚠️ Type 330 has not been issued against a live Green Invoice account here. Verify the first one
    in their dashboard; override with CHAVRUTA_INVOICE_CREDIT_TYPE.
    """
    if not enabled():
        return None
    import requests

    now = now if now is not None else time.time()
    date = time.strftime("%Y-%m-%d", time.gmtime(now))
    try:
        doc_type = int(os.environ.get("CHAVRUTA_INVOICE_CREDIT_TYPE", CREDIT_NOTE_TYPE))
    except ValueError:
        doc_type = CREDIT_NOTE_TYPE
    try:
        token = _token(now)
        body = {
            "type": doc_type,
            "lang": "he",
            "currency": "ILS",
            "date": date,
            "client": {"name": name or email or "לקוח", "emails": [email] if email else [], "add": False},
            "income": [{"description": description, "quantity": 1, "price": amount,
                        "currency": "ILS", "vatType": 1}],   # 1 = price includes VAT
            "payment": [{"date": date, "type": 3, "price": amount, "currency": "ILS",
                         "dealType": 6}],                    # 3 = credit card, 6 = recurring
        }
        r = requests.post(f"{_api_base()}/documents", json=body,
                          headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        r.raise_for_status()
        doc = r.json()
        _log.info("issued credit note %s (doc %s) for %s", doc.get("number"), doc.get("id"), email)
        return doc
    except Exception as exc:                # noqa: BLE001 — the money is already back; log and go on
        _log.exception("green-invoice credit note failed for %s: %s", email, exc.__class__.__name__)
        return None
