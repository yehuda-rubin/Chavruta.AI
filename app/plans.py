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
    # How many accounts may share this subscription. 1 for a personal plan; the institution tiers
    # carry 20 / 50 / 100. The pool scales WITH the seat count so the per-member allowance stays
    # constant — split a fixed pool three ways and the biggest school gets the least per person,
    # which is how the first cut of this was wrong (see specs/004-school-accounts/plan.md).
    seats: int = 1


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
# A typical conversation turn is ~15k normalized tokens, so free ~35/week, pro ~350/week.
# annual_price_ils is twelve months for the price of ten. It is the YEAR'S TOTAL, charged as twelve
# monthly instalments — nothing is taken up front. See ANNUAL_INSTALMENTS for why.
#
# Free raised 2026-08-03 (+50% on both token pools, +1 lesson/week — real usage was routinely
# maxing the old 350k/week pool inside a single heavy day) — every paid tier recomputed at its SAME
# multiple against the new free baseline, preserving the honest-ratio invariant above.
#
# Free's DAILY pool raised again 2026-08-12 (user decision): 180k → 200k, alongside the per-intent
# generation budgets roughly doubling in pipeline.py. A bigger answer costs more per turn, so
# leaving the daily pool where it was would have quietly cut how many turns a free day buys. Every
# paid tier is recomputed at its SAME multiple (x3 / x10 / x40) so "3x the usage" stays literally
# true — that invariant is the whole reason the UI can state a ratio and never a number.
# Repriced 2026-08-12. The old ladder (₪29 / ₪49.90 / ₪199) was set before anyone measured what a
# turn costs, and two of its three tiers lost money at their own cap — see the profitability test in
# tests/unit. Nothing was grandfathered because nothing had to be: the only paid accounts in
# production were a coupon grant and a test.
#
# Every paid tier must cover THREE things, and the price is derived from them rather than guessed:
#
#   1. its own worst case — the daily pool maxed every day, PLUS the separate weekly lesson pool,
#      which draws no tokens at all and is the line easiest to forget when pricing;
#   2. the free users it carries — a paid tier subsidises `multiple` free accounts (basic 3, pro 10,
#      institution 40), so a larger customer funds proportionally more of the free tier rather than a
#      flat amount that would crush the small tier;
#   3. a PROFIT_TARGET margin on top of both.
#
# Every figure is the FULL-utilisation worst case, deliberately: a price that only works when
# customers under-use their allowance is not a price, it is a hope. Real usage sits far below, so
# these are floors.
#
#     tier      own cost   free users   subsidy   total   net needed   gross (incl. VAT)
#     basic         ₪14        3           ₪14      ₪29       ₪41            ₪49
#     pro           ₪48       10           ₪48      ₪96      ₪137           ₪169
#     institution  ₪192       40          ₪192     ₪385      ₪549           ₪649
#
# The "gross" column above is the FLOOR at the ORIGINAL 2026-08-12 numbers, kept as-is because the
# cost inputs (token price, weekly-lesson budget, PROFIT_TARGET) have not changed. It no longer equals
# the sale price for any tier after the 2026-08-21 reprice below (₪75 / ₪200 / ₪1,000 / ₪2,000 /
# ₪4,000) — every paid tier now sits deliberately above its floor rather than at it.
#
# Derived at $0.20 per million normalized tokens (= COMPLETION_WEIGHT matches the provider's own
# input:output ratio, so a normalized token IS the cost unit), ~3.7 ILS/USD, 18% VAT, and a measured
# 23,512 normalized tokens per turn / ~58,000 per lesson.
#
# NOT included, because no per-seat price can carry it alone: the server costs ~₪740/month whether
# anyone subscribes or not. At realistic usage that is roughly two institutions or eight pro
# subscribers — the number to actually aim at.
PROFIT_TARGET = 0.30

# The rule above yields a FLOOR, not a price. Do not "correct" a paid tier down to its floor — the
# floor answers "would this lose money", not "what is this worth".
#
# INSTITUTIONAL PRICING IS NO LONGER A PUBLIC SELF-SERVICE LADDER (changed 2026-08-21). The three
# figures below (₪1,000 / ₪2,000 / ₪4,000) are an INTERNAL negotiation anchor, not a published price:
# public_catalogue() and the frontend (PlansModal.tsx) show "contact us" for any tier with seats > 1
# instead of a number — see is_institutional(). Why: (1) a public institutional price invites a direct
# comparison against Otzar HaHochma's real published rate (~₪561/month equivalent for 20 seats, see
# docs/מחירון-מנויים-Chavruta-AI.pdf §9), and ₪1,000 for institution-20 would read as ~78% more
# expensive with no room to explain the self-service admin panel (seats/invites/usage — orgs.py +
# web/app/school) that a personal tier never gets and that is not priced into the cost model above at
# all; (2) there is still no real institutional pricing signal (3 accounts, billing off) — a
# conversation produces one, a published number does not; (3) it sidesteps needing to fix
# create_org's broken self-service creation path for now — every institutional grant goes through the
# ALREADY-WORKING coupon flow (coupons.issue_plan_coupon → redeem, see
# test_a_coupon_granted_plan_reaches_the_school) after a manual, negotiated conversation, not through
# checkout. IMPORTANT: because of this, a negotiated price below the anchor must be granted by coupon,
# never inferred from the amount paid — a discounted invoice run through the ordinary PayPlus
# amount-resolver (_tier_affordable_at) would silently resolve to a SMALLER tier than what was sold,
# since that resolver only matches an amount against these list prices.
#
# At the ₪1,000 / ₪2,000 / ₪4,000 anchor, all three institution tiers clear PROFIT_TARGET even at full
# utilisation (54.6% / 43.3% / 43.2% margin) — unlike the previous public ladder, where institution-50
# and institution-100 sat below the 30% target at their own worst case. Per-seat price is ₪50.00 /
# ₪40.00 / ₪40.00 — no further discount from 50 to 100 seats, which is fine for a negotiated anchor
# (each conversation can move off it) but would look like a broken volume curve if ever published
# as-is. See docs/מחירון-מנויים-Chavruta-AI.pdf §9 for the full worked analysis, including the basic/
# pro reprice below.
#
# Repriced 2026-08-21 (basic/pro raised; institution/-50/-100 moved to the internal anchor above):
# basic and pro were re-anchored well above their floor (54.6% / 43.3% margin at full utilisation)
# rather than sitting a few agorot over it as before — that also fixes a real inversion where basic
# was cheaper per normalized token than pro (backwards volume logic). Nothing is grandfathered: billing
# is still off (no PAYPLUS_* keys), so none of this is charged to anyone yet.
TIERS: tuple[Tier, ...] = (
    Tier("free",             200_000,     525_000,   2,   1,    0.0,      0.0, "חינם",         "Free"),
    Tier("basic",            600_000,   1_575_000,   6,   3,   75.0,    750.0, "בסיסי",        "Basic"),
    Tier("pro",            2_000_000,   5_250_000,  20,  10,  200.0,   2000.0, "מלא",          "Pro"),
    Tier("institution",    8_000_000,  21_000_000,  80,  40, 1000.0,  10000.0, "מוסדי 20",     "Institution 20", 20),
    Tier("institution_50", 20_000_000,  52_500_000, 200, 100, 2000.0, 20000.0, "מוסדי 50",    "Institution 50", 50),
    Tier("institution_100", 40_000_000, 105_000_000, 400, 200, 4000.0, 40000.0, "מוסדי 100",  "Institution 100", 100),
)

# Output costs several times input everywhere; 3x is the round figure that holds across the models
# this runs on. Only the RATIO matters — it decides whether a long paste or a long answer dominates.
#
# It also happens to be EXACTLY the provider's own structure: Nebius charges $0.20 per million input
# tokens and 3x that for output. So a normalized token is not merely proportional to cost, it IS the
# cost unit — `billed_tokens * $0.20 / 1e6` is the real dollar figure for any account, tier or turn,
# with no conversion factor to get wrong. Measured 2026-08-12 over 166 production turns: 19,566
# prompt + 1,315 completion per turn = 23,512 normalized ≈ $0.0047. If the provider or its pricing
# ratio ever changes, this constant is where that shows up.
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


def is_institutional(plan: str | None) -> bool:
    """Whether this tier is sold to an organisation rather than to a person. Read off `seats` rather
    than an id prefix so adding a tier can't quietly land on the wrong side of the rule."""
    return tier(plan).seats > 1


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
    # parsha/dafyomi default to a chavruta-style turn (see _wants_full_lesson) — reserved like
    # explain/chavruta, not like a full lesson; the rare turn that escalates into one still
    # settles against its real usage (see _metered), so under-reserving here just means a
    # slightly late top-up, not an unpaid lesson.
    #
    # Raised 2026-08-12 with the per-intent generation budgets in pipeline.py. These have to move
    # together: a completion is weighted x3 (COMPLETION_WEIGHT), so a 6k-token answer alone is 18k
    # normalized — an estimate of 20k for a whole qa turn stopped covering even the output, let
    # alone the prompt, the moment the budget doubled.
    return {"compare": 80_000, "halacha": 80_000, "shut": 80_000, "explain": 40_000,
            "parsha": 40_000, "dafyomi": 40_000}.get((intent or "").strip().lower(), 30_000)


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


# ── Cancellation and refunds ─────────────────────────────────────────────────
#
# Terms §10 grants the statutory 14-day cancellation on a distance sale. The supplier may keep a
# cancellation fee of 5% of the transaction or ₪100, WHICHEVER IS LOWER — and on the amounts here
# (a ₪24–₪199 instalment) the percentage is always the lower of the two, so the ₪100 cap never
# binds. It is written out anyway because the cap is the part of the rule people misremember, and
# because the institution tier is one price rise away from the boundary.
#
# Nothing here is deducted automatically. These functions produce a QUOTE that scripts/refund.py
# shows an operator before anything moves; the amount actually refunded is a human decision, and the
# default that script offers is the most generous lawful one.
CANCELLATION_FEE_PCT = 5.0
CANCELLATION_FEE_CAP_ILS = 100.0


def cancellation_fee_ils(amount: float) -> float:
    """The most a supplier may keep as a cancellation fee on a ₪`amount` distance sale."""
    return round(min(max(0.0, float(amount)) * CANCELLATION_FEE_PCT / 100.0,
                     CANCELLATION_FEE_CAP_ILS), 2)


def refund_quote(amount: float, *, days_used: int = 0, cycle: str | None = MONTHLY) -> dict:
    """What may lawfully be withheld from a ₪`amount` charge, and what we would actually give back.

    Three figures, because they answer different questions:

      fee        the cancellation fee the law permits (5% or ₪100, the lower).
      consumed   the pro-rata value of the days already used in the period paid for. A continuing
                 transaction is cancelled going forward, so the days the customer actually had the
                 service are theirs to pay for.
      max_deduct fee + consumed — the floor the law puts under a refund, not a target.
      refund     what we offer: the whole charge minus the fee, and NOT minus `consumed`.

    `refund` is deliberately more generous than `amount - max_deduct`. On a single monthly instalment
    the pro-rata share is a few shekels, and arguing over them with someone who has already decided
    to leave costs more than it collects — in goodwill and in the operator time it takes to defend
    the arithmetic. `consumed` is still computed and shown, so an operator can choose otherwise on a
    large or abusive case and know the number is defensible.
    """
    amount = max(0.0, float(amount))
    fee = cancellation_fee_ils(amount)
    days = max(0, int(days_used))
    total_days = max(1, period_days(cycle))
    consumed = round(amount * min(days, total_days) / total_days, 2)
    return {
        "amount": round(amount, 2),
        "fee": fee,
        "consumed": consumed,
        "max_deduct": round(min(amount, fee + consumed), 2),
        "refund": round(max(0.0, amount - fee), 2),
    }


# ── Credits ──────────────────────────────────────────────────────────────────
#
# A credit is one generation, spent ONLY after a plan's cap is hit. Pricing it has almost nothing to
# do with what it costs us and everything to do with not undercutting the subscriptions:
#
#     marginal cost of one turn                  ₪0.017
#     implied per-turn price, basic / inst-20     ₪0.260
#     implied per-turn price, pro / inst-50 / inst-100   ₪0.208   (the cheapest rate we sell at all)
#
# (Recomputed for the 2026-08-21 reprice — price ÷ (weekly_tokens x 4.3 / 23,512). Institution figures
# use the internal negotiation anchor, not a published price; see the note above TIERS.)
#
# So a credit priced below ~₪0.20 is not an overflow valve, it is a cheaper subscription with extra
# steps — anyone doing arithmetic buys credits instead of a plan, and the recurring revenue that
# actually funds the server evaporates. ₪0.50 sits ~2.4x above the cheapest subscription rate and ~29x
# marginal cost, which is what makes it worth topping up in a pinch and never worth living on.
#
# Not yet sold: credits are granted by coupon today (db.add_credits), and a pack purchase would
# write the same column. This constant is here so the first person to build that flow inherits the
# reasoning rather than picking a round number.
CREDIT_PRICE_ILS = 0.50

# A credit costs more for the expensive intents. Measured: a lesson averages ~58,000 normalized
# tokens against ~23,512 for a question — 2.5x. It is charged 5x, deliberately above the measured
# ratio, because a lesson also runs the agentic loop over a much larger source pool and its variance
# is far wider than a question's.
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

    Prices are absolute for PERSONAL tiers — they have to be. Allowances are NOT: this returns the
    multiple of the free tier and nothing else. A published token or lesson figure becomes a promise,
    so trimming a budget or moving to a costlier model would be a downgrade to a paying customer; a
    ratio survives both. It is also the only honest way to describe a token allowance, which means
    nothing to a reader on its own.

    The single `multiple` is truthful because every dimension scales together — see TIERS.

    INSTITUTIONAL tiers (seats > 1) get price fields of None instead of a number, deliberately, as of
    2026-08-21 — see the "INSTITUTIONAL PRICING IS NO LONGER A PUBLIC SELF-SERVICE LADDER" note above
    TIERS. The number in TIERS for those rows is an internal negotiation anchor, not something this
    endpoint should ever expose — a client inspecting the raw response must see the same "contact us"
    signal the rendered UI shows, not a number the UI merely chooses not to print.
    """
    he = (lang or "he").startswith("he")
    out = []
    for t in TIERS:
        institutional = t.seats > 1
        out.append({
            "id": t.id,
            "name": t.name_he if he else t.name_en,
            "price_ils": None if institutional else price_ils(t.id, MONTHLY),
            "annual_price_ils": None if institutional else annual_total_ils(t.id),
            "annual_monthly_ils": None if institutional else price_ils(t.id, ANNUAL),
            "annual_saving_pct": 0 if institutional else annual_saving_pct(t.id),
            "multiple": t.multiple,          # "3x the free tier" — the only allowance figure shown
            "seats": t.seats,                # > 1 is what the frontend uses to render "contact us"
        })
    return out


def limits_catalogue(lang: str = "he") -> list[dict]:
    """The absolute usage limits for each tier — for the /limits page.

    This exists separately from public_catalogue() because the marketing UI deliberately shows only
    a ratio ("3x the usage") and never an absolute token or lesson count. A published number becomes
    a promise, so trimming a budget or moving to a costlier model would be a downgrade to a paying
    customer, while a ratio stays true as the numbers underneath it move.

    However, a usage cap is a material feature of what someone is buying, and "3x of something we
    won't tell you" leaves a customer unable to know what they bought or whether it later shrank.
    Both can be had: the marketing UI keeps the ratio, and the absolute numbers live in exactly
    one place (this function, exposed at /billing/limits) that is linked from pricing and checkout.

    This function reads the current values through the accessor functions (daily_tokens, weekly_tokens,
    weekly_lessons, price_ils, annual_total_ils) so environment overrides are reflected.

    INSTITUTIONAL tiers (seats > 1) get price fields of None here too, for the same reason as
    public_catalogue (see the note above TIERS in this module): this is a public, UNAUTHENTICATED
    endpoint, so if this function printed the real number a call to it directly would hand out the
    ₪1,000/₪2,000/₪4,000 internal negotiation anchor even while the marketing UI shows "contact us" —
    defeating the whole point of not publishing it. The absolute token/lesson figures are still real
    and shown, since usage limits are not the competitive-sensitive part.
    """
    he = (lang or "he").startswith("he")
    out = []
    for t in TIERS:
        institutional = t.seats > 1
        out.append({
            "id": t.id,
            "name": t.name_he if he else t.name_en,
            "price_ils": None if institutional else price_ils(t.id, MONTHLY),
            "annual_price_ils": None if institutional else annual_total_ils(t.id),
            "annual_monthly_ils": None if institutional else price_ils(t.id, ANNUAL),
            "daily_tokens": daily_tokens(t.id),
            "weekly_tokens": weekly_tokens(t.id),
            "weekly_lessons": weekly_lessons(t.id),
            "seats": t.seats,
        })
    return out
