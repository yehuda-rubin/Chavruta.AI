"""Institutional pricing is a negotiation anchor, not a published number (decided 2026-08-21).

app/plans.py::TIERS carries a real figure for institution/-50/-100 (₪1,000/₪2,000/₪4,000) so the
rest of the pricing math (floor, margin, credit pricing) still has something to compute against, but
neither PUBLIC catalogue endpoint may ever hand that number to a caller — public_catalogue() backs
the marketing UI's "contact us" card, and limits_catalogue() backs /billing/limits, which is
unauthenticated. A caller who queries either directly, not just the rendered page, must see the same
None the UI treats as "no price to show".
"""
from __future__ import annotations

from app import plans


def _institutional_rows(catalogue: list[dict]) -> list[dict]:
    return [row for row in catalogue if row["seats"] > 1]


def _personal_rows(catalogue: list[dict]) -> list[dict]:
    return [row for row in catalogue if row["seats"] == 1]


def test_public_catalogue_hides_institutional_prices():
    rows = _institutional_rows(plans.public_catalogue("he"))
    assert rows and all(r["price_ils"] is None for r in rows)
    assert all(r["annual_price_ils"] is None for r in rows)
    assert all(r["annual_monthly_ils"] is None for r in rows)


def test_public_catalogue_still_prices_personal_tiers():
    rows = _personal_rows(plans.public_catalogue("he"))
    assert rows and all(r["price_ils"] is not None for r in rows)
    free = next(r for r in rows if r["id"] == "free")
    assert free["price_ils"] == 0


def test_limits_catalogue_also_hides_institutional_prices():
    """The real bug this guards: limits_catalogue is a SEPARATE function from public_catalogue and
    backs a public, unauthenticated route (/billing/limits) — fixing one without the other would
    leave the internal negotiation anchor readable by anyone who called the endpoint directly, even
    while the marketing UI correctly showed "contact us"."""
    rows = _institutional_rows(plans.limits_catalogue("he"))
    assert rows and all(r["price_ils"] is None for r in rows)
    assert all(r["annual_price_ils"] is None for r in rows)
    assert all(r["annual_monthly_ils"] is None for r in rows)


def test_limits_catalogue_still_shows_institutional_usage_limits():
    """Usage caps are not the competitive-sensitive part — only the price is."""
    rows = _institutional_rows(plans.limits_catalogue("he"))
    assert all(r["daily_tokens"] > 0 and r["weekly_tokens"] > 0 and r["weekly_lessons"] > 0
               for r in rows)


def test_limits_catalogue_still_prices_personal_tiers():
    rows = _personal_rows(plans.limits_catalogue("he"))
    assert rows and all(r["price_ils"] is not None for r in rows)
