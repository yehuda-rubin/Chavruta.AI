"""Subscription tiers and credit costs — the one place that decides what an account may do.

Everything here is a DEFAULT overridable by environment, because pricing is a business decision that
should not need a code change (Principle II). The shape is deliberate:

  • A tier is a DAILY generation cap, not a monthly one. The cost driver is tokens per generation,
    and a daily cap bounds the worst day instead of letting one afternoon drain a month's budget.
  • Credits are prepaid generations spent ONLY after the day's cap is used up. That makes them a
    real overflow valve rather than a second, competing currency.
  • A credit costs more for the expensive intents. A lesson runs the agentic loop over a large
    source pool — roughly an order of magnitude more tokens than a question — so charging it as one
    unit would let 1,000 credits buy ~10,000 questions' worth of compute. Set
    CHAVRUTA_CREDIT_COSTS="" to flatten every intent back to 1.

Legacy note: the first billing implementation knew only 'free' and 'paid'. 'paid' is kept as an
alias of the 'pro' tier so existing subscribers and the PayPlus webhook keep working untouched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    id: str
    daily_quota: int          # generations per UTC day; 0 = unlimited
    price_ils: float          # monthly, for display and checkout
    name_he: str
    name_en: str


# Order matters: _rank() uses it to decide whether a coupon is an upgrade or a downgrade.
TIERS: tuple[Tier, ...] = (
    Tier("free",        10,  0.0,   "חינם",   "Free"),
    Tier("basic",       60,  29.0,  "בסיסי",  "Basic"),
    Tier("pro",        250,  49.9,  "מלא",    "Pro"),
    Tier("institution",  0,  199.0, "מוסדי",  "Institution"),
)

_BY_ID = {t.id: t for t in TIERS}
_ALIASES = {"paid": "pro"}          # pre-tier billing wrote 'paid'; it means the standard paid tier


def canonical(plan: str | None) -> str:
    """The tier id for a stored plan value. Unknown values fall back to 'free' — an account can never
    end up with more access than a name we recognise."""
    p = (plan or "free").strip().lower()
    p = _ALIASES.get(p, p)
    return p if p in _BY_ID else "free"


def tier(plan: str | None) -> Tier:
    return _BY_ID[canonical(plan)]


def rank(plan: str | None) -> int:
    """Position in TIERS — higher is more access. Used to avoid downgrading someone with a coupon."""
    return next(i for i, t in enumerate(TIERS) if t.id == canonical(plan))


def is_valid_plan(plan: str) -> bool:
    """Whether a string names a real tier — for validating operator input before issuing a coupon."""
    p = (plan or "").strip().lower()
    return _ALIASES.get(p, p) in _BY_ID


def daily_quota(plan: str | None) -> int:
    """Generations per UTC day for this plan. 0 ⇒ unlimited.

    Env override per tier: CHAVRUTA_QUOTA_FREE / _BASIC / _PRO / _INSTITUTION. The older
    CHAVRUTA_FREE_DAILY_QUOTA and CHAVRUTA_PAID_DAILY_QUOTA still work — a deployment that already
    set them keeps its behaviour without editing anything.
    """
    t = tier(plan)
    legacy = {"free": "CHAVRUTA_FREE_DAILY_QUOTA", "pro": "CHAVRUTA_PAID_DAILY_QUOTA"}.get(t.id)
    for env in (f"CHAVRUTA_QUOTA_{t.id.upper()}", legacy):
        if env and (raw := os.environ.get(env, "").strip()):
            try:
                return max(0, int(raw))
            except ValueError:
                pass
    return t.daily_quota


def price_ils(plan: str | None) -> float:
    t = tier(plan)
    raw = os.environ.get(f"CHAVRUTA_PRICE_{t.id.upper()}", "").strip()
    if not raw and t.id == "pro":
        raw = os.environ.get("CHAVRUTA_SUB_PRICE_ILS", "").strip()   # the original single-price knob
    try:
        return float(raw) if raw else t.price_ils
    except ValueError:
        return t.price_ils


# ── Credits ──────────────────────────────────────────────────────────────────
_DEFAULT_COSTS = {"lesson": 5, "halacha": 2, "shut": 2}
_FALLBACK_COST = 1


def credit_cost(intent: str | None) -> int:
    """Credits one generation of this intent costs. CHAVRUTA_CREDIT_COSTS overrides as
    "lesson=5,halacha=2"; setting it to an empty string charges 1 for everything."""
    raw = os.environ.get("CHAVRUTA_CREDIT_COSTS")
    if raw is None:
        costs = _DEFAULT_COSTS
    else:
        costs = {}
        for part in raw.split(","):
            k, _, v = part.partition("=")
            if k.strip() and v.strip().isdigit():
                costs[k.strip().lower()] = int(v)
    return max(1, costs.get((intent or "").strip().lower(), _FALLBACK_COST))


def public_catalogue(lang: str = "he") -> list[dict]:
    """The tier list for the UI — id, display name, price and daily cap."""
    he = (lang or "he").startswith("he")
    return [{
        "id": t.id,
        "name": t.name_he if he else t.name_en,
        "price_ils": price_ils(t.id),
        "daily_quota": daily_quota(t.id),      # 0 ⇒ unlimited
    } for t in TIERS]
