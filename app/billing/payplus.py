"""PayPlus gateway adapter.

API contract per docs.payplus.co.il (verified 2026-07-19):
  base     https://restapi.payplus.co.il/api/v1.0/  (prod) · https://restapidev.payplus.co.il/... (sandbox)
  auth     headers `api-key`, `secret-key`
  checkout POST /PaymentPages/generateLink  → { data: { payment_page_link, page_request_uid } }
  cancel   POST /RecurringPayments/{uid}/Valid  { valid: false }
  refund   POST /Transactions/RefundByTransactionUID  { transaction_uid, amount }
  webhook  header `hash` = base64(HMAC-SHA256(raw body, secret-key)); user-agent == "PayPlus";
           payload transaction.status_code == "000" ⇒ success; more_info round-trips our owner id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
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


def refund(transaction_uid: str, amount: float, *, description: str = "") -> dict:
    """Refund a charge, in full or in part, and return the provider's parsed response.

    Terms §10 promises cancellation within 14 days of a distance sale with a refund, and until now
    nothing in this module could give money back — the promise was kept by hand or not at all. This
    is the call behind it. It is deliberately NOT wired to a user-facing route: a refund is an
    irreversible movement of real money and is issued by an operator through scripts/refund.py,
    which shows the charge and asks before it runs.

    `amount` may be less than the original charge — the statutory cancellation fee (the lower of 5%
    or ₪100) is withheld by refunding the remainder, so the arithmetic lives in app/plans.py and
    only the final number arrives here.

    ⚠️ NOT exercised against a live PayPlus terminal — no refund has run here. Their reference
    documents the endpoint and the two required fields (verified 2026-07-27), but the response shape
    is not published, so success is taken from the HTTP status and the whole body is returned for
    the operator to read and for the ledger note. Check the first real refund against the PayPlus
    dashboard before trusting the reported result, and override the path with PAYPLUS_REFUND_PATH if
    their API names it differently.
    """
    import requests

    if not transaction_uid:
        raise ValueError("refund needs the provider's transaction uid")
    if amount <= 0:
        raise ValueError(f"refund amount must be positive, got {amount}")
    path = os.environ.get("PAYPLUS_REFUND_PATH", "Transactions/RefundByTransactionUID").strip("/")
    body = {"transaction_uid": transaction_uid, "amount": round(float(amount), 2)}
    if description:
        # Their `more_info` becomes the product line on a partial-refund document.
        body["more_info"] = description
    r = requests.post(f"{_base()}/{path}", json=body, headers=_headers(), timeout=_TIMEOUT)
    if not r.ok:
        # Do not swallow this. A refund that silently failed while we wrote a refund row to the
        # ledger is worse than no refund at all: the books would say the customer was paid back.
        raise RuntimeError(f"payplus refund failed ({r.status_code}): {r.text[:300]}")
    try:
        return r.json() or {}
    except ValueError:
        return {"raw": r.text[:500]}


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


def _customer_info(txn: dict) -> tuple[str, str]:
    """(email, name) for the receipt, from the webhook's own `transaction.data.hash_data` — despite
    the name, that field is base64-encoded JSON PayPlus round-trips containing what the hosted
    payment page collected (email, name, vat_number, phone; verified against
    docs.payplus.co.il's transaction-callback reference 2026-08-26). There is no plain
    `customer_email`/`customer_name` field on this callback shape — those exist only on the
    DIFFERENT `refURL_success` redirect response, which this webhook is not.
    Never raises: a malformed or absent hash_data means an empty receipt name field, not a 500 on
    a payment that already succeeded."""
    raw = ((txn.get("data") or {}).get("hash_data") or "").strip()
    if not raw:
        return "", ""
    try:
        info = json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        return "", ""
    return str(info.get("email") or "").strip(), str(info.get("name") or "").strip()


def parse_event(payload: dict) -> dict:
    """Normalise a callback into {owner_id, success, transaction_uid, recurring_uid, is_renewal,
    amount, email, name}.

    `transaction_uid` identifies THIS charge, where `recurring_uid` identifies the subscription that
    produced it. Refunds are issued against the former, so it has to be captured here and stored —
    without it a customer asking for their money back leaves us with a subscription handle and no
    way to name the payment.
    """
    txn = payload.get("transaction") or {}
    rec = txn.get("recurring_charge_information") or {}
    email, name = _customer_info(txn)
    return {
        "owner_id": txn.get("more_info") or payload.get("more_info"),
        "success": str(txn.get("status_code")) == "000",
        "transaction_uid": txn.get("uid") or txn.get("transaction_uid"),
        "recurring_uid": rec.get("recurring_uid"),
        "is_renewal": bool(rec),                 # renewal callbacks carry recurring_charge_information
        "amount": txn.get("amount"),
        "email": email,
        "name": name,
    }
