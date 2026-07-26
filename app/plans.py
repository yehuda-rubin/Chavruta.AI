"""Subscription tiers and credit costs — the one place that decides what an account may do.

Everything here is a DEFAULT overridable by environment, because pricing is a business decision that
should not need a code change (Principle II). The shape is deliberate:

  • Billing is MONTHLY. Usage is capped DAILY **and** WEEKLY, and both are enforced.
    The daily cap bounds the worst day. On its own it is not enough: seven maxed-out days in a row
    is 7x the intended load, which is exactly the shape of a runaway month. The weekly cap is what
    bounds the bill, at roughly 3.5x the daily figure — enough for a few heavy prep days, not
    enough for a permanently maxed week.
  • NO TIER IS UNLIMITED. On a product whose marginal cost is tokens, "unlimited" is an open-ended
    liability, and companies far larger than this one have been badly burned selling it. Every tier
    carries a real number. (An operator can still set 0 = uncapped via env for their own account or
    a test; no shipped tier does.)
  • Credits are prepaid generations spent ONLY after a cap is hit. That makes them a real overflow
    valve rather than a second, competing currency.
  • A credit costs more for the expensive intents. A lesson runs the agentic loop over a large
    source pool — roughly an order of magnitude more tokens than a question — so charging it as one
    unit would let 1,000 credits buy ~10,000 questions' worth of compute. Set
    CHAVRUTA_CREDIT_COSTS="" to flatten every intent back to 1.
  • The same weighting can be applied to the QUOTA itself (CHAVRUTA_QUOTA_WEIGHTED=true), so a
    lesson consumes 5 of the day's allowance rather than 1. It is OFF by default because a plain
    count is what a user can predict ("40 questions a day"); turn it on if lesson-heavy accounts
    turn out to dominate the bill, which is the one way a count-based cap still leaks cost.

Legacy note: the first billing implementation knew only 'free' and 'paid'. 'paid' is kept as an
alias of the 'pro' tier so existing subscribers and the PayPlus webhook keep working untouched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MONTHLY, ANNUAL = "monthly", "annual"
CYCLES = (MONTHLY, ANNUAL)


@dataclass(frozen=True)
class Tier:
    id: str
    daily_quota: int          # generations per UTC day
    weekly_quota: int         # generations per week (Sunday-start) — the cap that bounds the month
    price_ils: float          # monthly, for display and checkout
    annual_price_ils: float   # paid once up front — 10 months' price for 12 (~17% off)
    name_he: str
    name_en: str


# Order matters: rank() uses it to decide whether a coupon is an upgrade or a downgrade.
#
# Weekly sits near 3.5x daily, deliberately below 7x: a user may have three or four heavy days in a
# week, but a permanently maxed week is not what any of these prices buy. The monthly ceiling is
# roughly weekly x 4.3 — that is the number to check a price against, not the daily one.
# Annual is twelve months for the price of ten — the familiar SaaS trade: the customer commits, you
# get the cash up front and stop paying a processor fee eleven extra times.
TIERS: tuple[Tier, ...] = (
    Tier("free",          8,   25,   0.0,    0.0, "חינם",   "Free"),          # ~110/month
    Tier("basic",        40,  140,  29.0,  290.0, "בסיסי",  "Basic"),         # ~600/month
    Tier("pro",         100,  350,  49.9,  499.0, "מלא",    "Pro"),           # ~1,500/month
    Tier("institution", 350, 1200, 199.0, 1990.0, "מוסדי",  "Institution"),   # ~5,200/month
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


def _env_int(*names: str | None) -> int | None:
    for name in names:
        if name and (raw := os.environ.get(name, "").strip()):
            try:
                return max(0, int(raw))
            except ValueError:
                pass
    return None


def daily_quota(plan: str | None) -> int:
    """Generations per UTC day for this plan. 0 ⇒ uncapped (no shipped tier uses it).

    Env override per tier: CHAVRUTA_QUOTA_FREE / _BASIC / _PRO / _INSTITUTION. The older
    CHAVRUTA_FREE_DAILY_QUOTA and CHAVRUTA_PAID_DAILY_QUOTA still work — a deployment that already
    set them keeps its behaviour without editing anything.
    """
    t = tier(plan)
    legacy = {"free": "CHAVRUTA_FREE_DAILY_QUOTA", "pro": "CHAVRUTA_PAID_DAILY_QUOTA"}.get(t.id)
    got = _env_int(f"CHAVRUTA_QUOTA_{t.id.upper()}", legacy)
    return t.daily_quota if got is None else got


def weekly_quota(plan: str | None) -> int:
    """Generations per week (Sunday-start) for this plan. 0 ⇒ uncapped.

    This is the cap that actually bounds the monthly bill; the daily one bounds a single spike.
    Override with CHAVRUTA_WEEKLY_QUOTA_FREE / _BASIC / _PRO / _INSTITUTION.
    """
    t = tier(plan)
    got = _env_int(f"CHAVRUTA_WEEKLY_QUOTA_{t.id.upper()}")
    return t.weekly_quota if got is None else got


def quota_units(intent: str | None) -> int:
    """How much of the allowance one generation consumes.

    1 by default: a plain count is what a user can predict and what the UI can show honestly. With
    CHAVRUTA_QUOTA_WEIGHTED=true it follows credit_cost() instead, so a lesson eats 5 — the lever to
    pull if lesson-heavy accounts dominate the bill, since a flat count under-charges them ~10x.
    """
    raw = os.environ.get("CHAVRUTA_QUOTA_WEIGHTED", "").strip().lower()
    return credit_cost(intent) if raw in {"1", "true", "yes", "on"} else 1


def canonical_cycle(cycle: str | None) -> str:
    """'annual' only when explicitly asked for; anything unrecognised bills monthly — the cheaper,
    lower-commitment option, which is the safe way to resolve an ambiguous request for money."""
    return ANNUAL if (cycle or "").strip().lower() in {"annual", "year", "yearly"} else MONTHLY


def period_days(cycle: str | None = MONTHLY) -> int:
    """Days of access one payment buys. Override with CHAVRUTA_SUB_PERIOD_DAYS / _ANNUAL_PERIOD_DAYS."""
    if canonical_cycle(cycle) == ANNUAL:
        return _env_int("CHAVRUTA_ANNUAL_PERIOD_DAYS") or 365
    return _env_int("CHAVRUTA_SUB_PERIOD_DAYS") or 30


def price_ils(plan: str | None, cycle: str | None = MONTHLY) -> float:
    """What one billing period costs: the monthly price, or the whole year up front."""
    t = tier(plan)
    if canonical_cycle(cycle) == ANNUAL:
        raw = os.environ.get(f"CHAVRUTA_ANNUAL_PRICE_{t.id.upper()}", "").strip()
        try:
            return float(raw) if raw else t.annual_price_ils
        except ValueError:
            return t.annual_price_ils
    raw = os.environ.get(f"CHAVRUTA_PRICE_{t.id.upper()}", "").strip()
    if not raw and t.id == "pro":
        raw = os.environ.get("CHAVRUTA_SUB_PRICE_ILS", "").strip()   # the original single-price knob
    try:
        return float(raw) if raw else t.price_ils
    except ValueError:
        return t.price_ils


def annual_saving_pct(plan: str | None) -> int:
    """How much paying yearly saves, for the UI to state instead of hardcoding "17%"."""
    monthly, annual = price_ils(plan, MONTHLY), price_ils(plan, ANNUAL)
    if monthly <= 0 or annual <= 0:
        return 0
    return max(0, round((1 - annual / (monthly * 12)) * 100))


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
    """The tier list for the UI — id, display name, monthly price and both caps."""
    he = (lang or "he").startswith("he")
    return [{
        "id": t.id,
        "name": t.name_he if he else t.name_en,
        "price_ils": price_ils(t.id, MONTHLY),
        "annual_price_ils": price_ils(t.id, ANNUAL),
        "annual_saving_pct": annual_saving_pct(t.id),
        "daily_quota": daily_quota(t.id),
        "weekly_quota": weekly_quota(t.id),
    } for t in TIERS]
