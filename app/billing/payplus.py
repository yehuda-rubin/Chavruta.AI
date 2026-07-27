"""PayPlus gateway adapter.

API contract per docs.payplus.co.il (verified 2026-07-19):
  base     https://restapi.payplus.co.il/api/v1.0/  (prod) · https://restapidev.payplus.co.il/... (sandbox)
  auth     headers `api-key`, `secret-key`
  checkout POST /PaymentPages/generateLink  → { data: { payment_page_link, page_request_uid } }
  cancel   POST /RecurringPayments/{uid}/Valid  { valid: false }
  webhook  header `hash` = base64(HMAC-SHA256(raw body, secret-key)); user-agent == "PayPlus";
           payload transaction.status_code == "000" ⇒ success; more_info round-trips our owner id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

_log = logging.getLogger("chavruta.billing.payplus")

_TIMEOUT = 30


def _sandbox() -> bool:
    return os.environ.get("PAYPLUS_MODE", "sandbox").lower() != "production"


def _base() -> str:
    return ("https://restapidev.payplus.co.il/api/v1.0"
            if _sandbox() else "https://restapi.payplus.co.il/api/v1.0")


def _api_key() -> str:
    return os.environ.get("PAYPLUS_API_KEY", "").strip()


def _secret_key() -> str:
    return os.environ.get("PAYPLUS_SECRET_KEY", "").strip()


def _page_uid() -> str:
    return os.environ.get("PAYPLUS_PAYMENT_PAGE_UID", "").strip()


def enabled() -> bool:
    return bool(_api_key() and _secret_key() and _page_uid())


def _headers() -> dict:
    return {"api-key": _api_key(), "secret-key": _secret_key(), "Content-Type": "application/json"}


def _public_url() -> str:
    return os.environ.get("CHAVRUTA_PUBLIC_URL", "http://localhost:5173").rstrip("/")


def _price() -> float:
    try:
        return float(os.environ.get("CHAVRUTA_SUB_PRICE_ILS", "49.9"))
    except ValueError:
        return 49.9


def create_payment_page(owner_id: str, email: str, name: str, *,
                        amount: float | None = None, cycle: str = "monthly") -> dict:
    """Create a hosted recurring-payment page and return {link, page_request_uid}. `owner_id` is
    threaded through `more_info` so the webhook can tie the charge back to the account.

    `cycle` picks the recurrence: monthly, or yearly for a prepaid year. Either way the subscription
    renews until cancelled — cancelling stops the NEXT charge and leaves the period already paid for
    intact, which for an annual plan means access runs to the end of that year.

    ⚠️ `recurring_type: "yearly"` is the documented value but has NOT been exercised against a live
    PayPlus terminal here (no annual charge has run yet). Verify it on the first real annual
    checkout before advertising the plan; override with PAYPLUS_ANNUAL_RECURRING_TYPE if their API
    names it differently.
    """
    import requests

    annual = cycle == "annual"
    recurring_type = (os.environ.get("PAYPLUS_ANNUAL_RECURRING_TYPE", "yearly").strip()
                      if annual else "monthly")
    body = {
        "payment_page_uid": _page_uid(),
        "amount": _price() if amount is None else float(amount),
        "currency_code": "ILS",
        "charge_method": 3,          # 3 = recurring
        "create_token": True,
        "refURL_callback": f"{_public_url()}/api/billing/webhook",
        "refURL_success": f"{_public_url()}/billing/success",
        "refURL_failure": f"{_public_url()}/billing/failure",
        "customer": {"customer_name": name or email or "user", "email": email or ""},
        "recurring_settings": {
            "instant_first_payment": True,
            "recurring_type": recurring_type,
            "number_of_charges": 0,   # 0 = until cancelled
        },
        "more_info": owner_id,
    }
    r = requests.post(f"{_base()}/PaymentPages/generateLink", json=body,
                      headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()
    data = (r.json() or {}).get("data") or {}
    link = data.get("payment_page_link")
    if not link:
        raise RuntimeError(f"payplus: no payment_page_link in response: {r.text[:300]}")
    return {"link": link, "page_request_uid": data.get("page_request_uid")}


def cancel_recurring(recurring_uid: str, terminal_uid: str | None = None) -> None:
    """Stop future charges on a subscription (no dedicated delete endpoint — set valid=false)."""
    import requests

    body = {"valid": False}
    if terminal_uid:
        body["terminal_uid"] = terminal_uid
    r = requests.post(f"{_base()}/RecurringPayments/{recurring_uid}/Valid", json=body,
                      headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()


def verify_webhook(raw_body: bytes, user_agent: str | None, hash_header: str | None) -> bool:
    """True iff the callback is authentically from PayPlus: user-agent 'PayPlus' and the `hash` header
    equals base64(HMAC-SHA256(raw body bytes, secret-key)). Hash the EXACT raw bytes, never re-serialized
    JSON. Constant-time compare.

    Fails closed when no secret is configured. Without that check the HMAC key is the empty string —
    which the attacker knows too, so anyone could compute a valid `hash` for a body of their choosing
    and post a forged "payment succeeded" for any account. The webhook route is unauthenticated by
    necessity (the provider cannot send a bearer token), so this signature IS the authentication."""
    secret = _secret_key()
    if not secret:
        _log.warning("webhook rejected: PAYPLUS_SECRET_KEY is not configured")
        return False
    if user_agent != "PayPlus" or not hash_header:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, hash_header)


def parse_event(payload: dict) -> dict:
    """Normalise a callback into {owner_id, success, recurring_uid, is_renewal, amount}."""
    txn = payload.get("transaction") or {}
    rec = txn.get("recurring_charge_information") or {}
    return {
        "owner_id": txn.get("more_info") or payload.get("more_info"),
        "success": str(txn.get("status_code")) == "000",
        "recurring_uid": rec.get("recurring_uid"),
        "is_renewal": bool(rec),                 # renewal callbacks carry recurring_charge_information
        "amount": txn.get("amount"),
    }
