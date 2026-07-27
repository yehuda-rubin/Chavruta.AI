"""Subscription tiers and credit costs — the one place that decides what an account may do.

Everything here is a DEFAULT overridable by environment, because pricing is a business decision that
should not need a code change (Principle II). The shape is deliberate:

  • Billing is MONTHLY on both cycles — the annual plan is a discounted RATE billed monthly, not a
    year taken up front (see ANNUAL_INSTALMENTS). Usage is metered in TWO INDEPENDENT POOLS:

      conversation  qa / explain / compare / chavruta / halacha   → TOKENS, daily + weekly
      lessons       lesson                                        → a COUNT, weekly

    They do not touch each other. Running out of conversation tokens does not stop a lesson, and a
    lesson never spends conversation tokens. A lesson is a big discrete thing a teacher plans around
    ("three shiurim this week"), so counting it is both truer to how it's used and easier to reason
    about; conversation is a stream of wildly different sizes, so only tokens measure it honestly.

  • Metering conversation in TOKENS, not messages, because a message is not a unit of cost. Pasting a
    daf and asking one question costs many times a short follow-up, and a message count charges them
    the same. Tokens are what the provider bills, so tokens are what we count.

  • The token unit is NORMALIZED: prompt + 3x completion. Output costs several times input on every
    provider, so a raw sum would price a long paste like a long answer.

  • Lesson cost is bounded by count x the per-lesson token budget already enforced in the pipeline —
    that product, not a token cap, is what makes a lesson quota safe to sell.

  • NO TIER IS UNLIMITED. On a product whose marginal cost is tokens, "unlimited" is an open-ended
    liability, and companies far larger than this one have been badly burned selling it. Every tier
    carries a real number. (An operator can still set 0 = uncapped via env for their own account or
    a test; no shipped tier does.)

  • Each paid tier is a single clean MULTIPLE of free — x3, x10, x40 — across every dimension at
    once. That is what lets the UI say "3x the usage" honestly without ever printing an absolute
    number: one ratio is true for tokens and lessons alike. Absolute figures are deliberately NOT
    shown to users (see public_catalogue): a published number becomes a promise, and then any budget
    change or a costlier model is a downgrade to a paying customer, while a ratio stays true as the
    numbers underneath it move.

  • Credits are prepaid generations spent ONLY after a cap is hit. That makes them a real overflow
    valve rather than a second, competing currency.
  • A credit costs more for the expensive intents. A lesson runs the agentic loop over a large
    source pool — roughly an order of magnitude more tokens than a question — so charging it as one
    unit would let 1,000 credits buy ~10,000 questions' worth of compute. Set
    CHAVRUTA_CREDIT_COSTS="" to flatten every intent back to 1.

Legacy note: the first billing implementation knew only 'free' and 'paid'. 'paid' is kept as an
alias of the 'pro' tier so existing subscribers and the PayPlus webhook keep working untouched.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

MONTHLY, ANNUAL = "monthly", "annual"
CYCLES = (MONTHLY, ANNUAL)


@dataclass(frozen=True)
class Tier:
    id: str
    daily_tokens: int         # conversation pool, normalized tokens per UTC day
    weekly_tokens: int        # conversation pool per week (Sunday-start) — bounds the month
    weekly_lessons: int       # lesson pool per week — a COUNT, independent of tokens
    multiple: int             # how many times the free tier this is; what the UI states
    price_ils: float          # monthly, for display and checkout
    annual_price_ils: float   # the YEAR's total — 10 months' price for 12 (~17% off).
                              # Billed as 12 instalments of a twelfth, NOT taken up front; see
                              # ANNUAL_INSTALMENTS and price_ils().
    name_he: str
    name_en: str


# Order matters: rank() uses it to decide whether a coupon is an upgrade or a downgrade.
#
# The weekly token figure sits near 3x the daily one, deliberately below 7x: a user may have two or
# three heavy days in a week, but a permanently maxed week is not what any of these prices buy. The
# monthly ceiling is roughly weekly x 4.3 — that is the number to check a price against.
#
# Every dimension scales by the SAME multiple, which is what makes "3x the usage" a true statement
# rather than a marketing average. Keep it that way when tuning: if tokens and lessons drift apart,
# the ratio the UI prints stops being honest.
#
# A typical conversation turn is ~15k normalized tokens, so free ~23/week, pro ~230/week.
# annual_price_ils is twelve months for the price of ten. It is the YEAR'S TOTAL, charged as twelve
# monthly instalments — nothing is taken up front. See ANNUAL_INSTALMENTS for why.
TIERS: tuple[Tier, ...] = (
    Tier("free",          120_000,    350_000,  1,  1,   0.0,    0.0, "חינם",   "Free"),
    Tier("basic",         360_000,  1_050_000,  3,  3,  29.0,  290.0, "בסיסי",  "Basic"),
    Tier("pro",         1_200_000,  3_500_000, 10, 10,  49.9,  499.0, "מלא",    "Pro"),
    Tier("institution", 4_800_000, 14_000_000, 40, 40, 199.0, 1990.0, "מוסדי",  "Institution"),
)

# Output costs several times input everywhere; 3x is the round figure that holds across the models
# this runs on. Only the RATIO matters — it decides whether a long paste or a long answer dominates.
COMPLETION_WEIGHT = 3


def normalized_tokens(prompt_tokens: int, completion_tokens: int) -> int:
    """What one LLM call costs in the unit the quota is denominated in."""
    return max(0, int(prompt_tokens or 0)) + COMPLETION_WEIGHT * max(0, int(completion_tokens or 0))

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


LESSON_INTENTS = frozenset({"lesson"})


def is_lesson(intent: str | None) -> bool:
    """Which pool a request draws on. Everything that isn't a lesson is conversation."""
    return (intent or "").strip().lower() in LESSON_INTENTS


def daily_tokens(plan: str | None) -> int:
    """Conversation tokens per UTC day. 0 ⇒ uncapped (no shipped tier uses it).

    Override with CHAVRUTA_TOKENS_DAY_FREE / _BASIC / _PRO / _INSTITUTION.
    """
    t = tier(plan)
    got = _env_int(f"CHAVRUTA_TOKENS_DAY_{t.id.upper()}")
    return t.daily_tokens if got is None else got


def weekly_tokens(plan: str | None) -> int:
    """Conversation tokens per week (Sunday-start). 0 ⇒ uncapped.

    This is the cap that actually bounds the monthly bill; the daily one bounds a single spike.
    Override with CHAVRUTA_TOKENS_WEEK_FREE / _BASIC / _PRO / _INSTITUTION.
    """
    t = tier(plan)
    got = _env_int(f"CHAVRUTA_TOKENS_WEEK_{t.id.upper()}")
    return t.weekly_tokens if got is None else got


def weekly_lessons(plan: str | None) -> int:
    """Lessons per week. Its own pool: unaffected by, and with no effect on, conversation tokens.
    0 ⇒ uncapped. Override with CHAVRUTA_LESSONS_WEEK_FREE / _BASIC / _PRO / _INSTITUTION.
    """
    t = tier(plan)
    got = _env_int(f"CHAVRUTA_LESSONS_WEEK_{t.id.upper()}")
    return t.weekly_lessons if got is None else got


def token_estimate(intent: str | None) -> int:
    """Normalized tokens to RESERVE before a conversation turn runs.

    A quota has to be checked before generation, but the true cost is only known after, so a turn is
    admitted against an estimate and settled to the real figure once the tokens come back. The
    estimate exists to stop an account with almost nothing left from launching a large request; it
    is intentionally generous, since over-reserving only delays a user while under-reserving spends
    money that was not there.
    """
    raw = _env_int(f"CHAVRUTA_TOKEN_ESTIMATE_{(intent or 'qa').strip().upper()}")
    if raw is not None:
        return raw
    return {"compare": 40_000, "halacha": 40_000, "shut": 40_000, "explain": 25_000}.get(
        (intent or "").strip().lower(), 20_000)


def canonical_cycle(cycle: str | None) -> str:
    """'annual' only when explicitly asked for; anything unrecognised bills monthly — the cheaper,
    lower-commitment option, which is the safe way to resolve an ambiguous request for money."""
    return ANNUAL if (cycle or "").strip().lower() in {"annual", "year", "yearly"} else MONTHLY


# The annual plan is a discounted RATE billed monthly, not a year taken up front.
#
# Israeli consumer law gives the buyer of a continuing transaction two rights that a prepaid year
# collides with: cancellation within 14 days of a distance sale (the supplier keeping at most 5% or
# ₪100, whichever is lower — on a ₪1,990 year that is a ~₪1,890 refund), and cancellation at any time
# thereafter, at which point holding eleven months of someone's money is the exposure. Charging a
# twelfth each month removes the collision at its source: there is never a prepayment to refund, and
# `cancel()` — which already stops future charges and leaves the paid period intact — is the whole
# mechanism. The customer pays the same total for the same year at the same discount.
#
# The trade-off is real and was taken deliberately: this gives up the cash up front. It also means a
# customer can take the annual rate and leave after a month, keeping the discount without the year.
# That is accepted rather than clawed back — billing someone a penalty for exercising a statutory
# cancellation right is exactly the problem this change exists to avoid.
ANNUAL_INSTALMENTS = 12


def period_days(cycle: str | None = MONTHLY) -> int:
    """Days of access one payment buys — a month on either cycle, since the annual plan is billed
    monthly too. Override with CHAVRUTA_SUB_PERIOD_DAYS / _ANNUAL_PERIOD_DAYS."""
    if canonical_cycle(cycle) == ANNUAL:
        return _env_int("CHAVRUTA_ANNUAL_PERIOD_DAYS") or 30
    return _env_int("CHAVRUTA_SUB_PERIOD_DAYS") or 30


def _annual_headline_ils(plan: str | None) -> float:
    """The configured yearly figure — the input to the instalment, not something anyone is charged."""
    t = tier(plan)
    raw = os.environ.get(f"CHAVRUTA_ANNUAL_PRICE_{t.id.upper()}", "").strip()
    try:
        return float(raw) if raw else t.annual_price_ils
    except ValueError:
        return t.annual_price_ils


def annual_total_ils(plan: str | None) -> float:
    """What the year actually costs: twelve instalments, to the agora.

    Derived from the instalment rather than configured directly, so the advertised year and the sum of
    the charges cannot drift apart. They do drift if you divide naively — ₪290 / 12 rounds to ₪24.17,
    and twelve of those is ₪290.04, four agorot MORE than the price on the page. The instalment is
    therefore rounded DOWN, which makes the year cost at most its headline and never more.
    """
    return round(price_ils(plan, ANNUAL) * ANNUAL_INSTALMENTS, 2)


def price_ils(plan: str | None, cycle: str | None = MONTHLY) -> float:
    """What ONE CHARGE costs: the monthly price, or a twelfth of the annual total.

    This is the amount handed to the payment provider. It is deliberately not the yearly figure —
    see ANNUAL_INSTALMENTS. For the year's total use annual_total_ils().
    """
    t = tier(plan)
    if canonical_cycle(cycle) == ANNUAL:
        # Floor, not round: twelve rounded-up instalments would exceed the advertised year.
        return math.floor(_annual_headline_ils(t.id) / ANNUAL_INSTALMENTS * 100) / 100
    raw = os.environ.get(f"CHAVRUTA_PRICE_{t.id.upper()}", "").strip()
    if not raw and t.id == "pro":
        raw = os.environ.get("CHAVRUTA_SUB_PRICE_ILS", "").strip()   # the original single-price knob
    try:
        return float(raw) if raw else t.price_ils
    except ValueError:
        return t.price_ils


def annual_saving_pct(plan: str | None) -> int:
    """How much the annual rate saves, for the UI to state instead of hardcoding "17%".

    Both figures are now per-month, so this compares like with like — the annual instalment against
    the monthly price."""
    monthly, instalment = price_ils(plan, MONTHLY), price_ils(plan, ANNUAL)
    if monthly <= 0 or instalment <= 0:
        return 0
    return max(0, round((1 - instalment / monthly) * 100))


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
    """The tier list for the UI.

    Prices are absolute — they have to be. Allowances are NOT: this returns the multiple of the free
    tier and nothing else. A published token or lesson figure becomes a promise, so trimming a
    budget or moving to a costlier model would be a downgrade to a paying customer; a ratio survives
    both. It is also the only honest way to describe a token allowance, which means nothing to a
    reader on its own.

    The single `multiple` is truthful because every dimension scales together — see TIERS.
    """
    he = (lang or "he").startswith("he")
    return [{
        "id": t.id,
        "name": t.name_he if he else t.name_en,
        "price_ils": price_ils(t.id, MONTHLY),
        "annual_price_ils": annual_total_ils(t.id),        # the year's total, for "₪1,990 a year"
        "annual_monthly_ils": price_ils(t.id, ANNUAL),     # what is actually charged each month
        "annual_saving_pct": annual_saving_pct(t.id),
        "multiple": t.multiple,          # "3x the free tier" — the only allowance figure shown
    } for t in TIERS]
