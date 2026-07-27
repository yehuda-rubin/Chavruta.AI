"""Quota persistence (app/db.py bump_usage / usage_today / usage_this_week).

The guarantees pinned: the counter enforces the DAILY and WEEKLY caps atomically (the request over
either cap is refused WITHOUT being counted), limit<=0 is uncapped-but-counted, and counts are
isolated per owner and per UTC day (one user's usage never spills into another's, and a new day is a
fresh allowance).

bump_usage returns (allowed, day_count, week_count).
"""
from __future__ import annotations

import pytest

import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "quota.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_bump_enforces_limit_and_does_not_count_rejects(fresh_db):
    for i in range(3):
        allowed, count, _w = fresh_db.bump_usage("u1", 3)
        assert allowed and count == i + 1
    allowed, count, _w = fresh_db.bump_usage("u1", 3)  # 4th vs limit 3
    assert not allowed and count == 3
    assert fresh_db.usage_today("u1") == 3             # the rejected call did not increment


def test_zero_limit_is_uncapped_but_still_counts(fresh_db):
    for _ in range(10):
        allowed, _c, _w = fresh_db.bump_usage("u2", 0)
        assert allowed
    assert fresh_db.usage_today("u2") == 10


def test_counts_isolated_per_owner(fresh_db):
    fresh_db.bump_usage("a", 5)
    fresh_db.bump_usage("a", 5)
    fresh_db.bump_usage("b", 5)
    assert fresh_db.usage_today("a") == 2
    assert fresh_db.usage_today("b") == 1


def test_counts_isolated_per_day(fresh_db):
    fresh_db.bump_usage("a", 5)
    fresh_db.bump_usage("a", 5)
    fresh_db.bump_usage("a", 5, day="2000-01-01")      # a different bucket entirely
    assert fresh_db.usage_today("a", day="2000-01-01") == 1
    assert fresh_db.usage_today("a") == 2


def test_usage_today_zero_when_none(fresh_db):
    assert fresh_db.usage_today("never-seen") == 0


def test_quota_resets_next_day(fresh_db):
    for _ in range(3):
        assert fresh_db.bump_usage("d", 3, day="2026-07-18")[0]
    assert not fresh_db.bump_usage("d", 3, day="2026-07-18")[0]   # day 1 capped
    assert fresh_db.bump_usage("d", 3, day="2026-07-19")[0]       # new day → fresh allowance
    assert fresh_db.usage_today("d", day="2026-07-19") == 1


def test_no_overshoot_under_concurrency(fresh_db):
    """N threads hammer the same owner at once — the atomic read-and-increment must let exactly
    `limit` through, never more (the property the single-lock transaction exists to guarantee)."""
    import threading

    limit = 50
    results: list[bool] = []
    rlock = threading.Lock()

    def worker():
        allowed, _d, _w = fresh_db.bump_usage("c", limit)
        with rlock:
            results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == limit                 # exactly `limit` allowed, never more
    assert fresh_db.usage_today("c") == limit


# ── The weekly cap ────────────────────────────────────────────────────────────
def test_weekly_cap_bites_before_the_daily_one_runs_out(fresh_db):
    """The reason the weekly cap exists: a daily cap alone permits seven maxed days in a row."""
    # Sun 2026-07-19 .. Sat 2026-07-25 is one week; 5/day but only 12/week.
    for day in ("2026-07-19", "2026-07-20"):
        for _ in range(5):
            assert fresh_db.bump_usage("w1", 5, day=day, weekly_limit=12)[0]
    # day 3: the day is fresh, but the week has 2 left
    assert fresh_db.bump_usage("w1", 5, day="2026-07-21", weekly_limit=12)[0]
    assert fresh_db.bump_usage("w1", 5, day="2026-07-21", weekly_limit=12)[0]
    allowed, day_count, week_count = fresh_db.bump_usage("w1", 5, day="2026-07-21", weekly_limit=12)
    assert not allowed and day_count == 2 and week_count == 12


def test_weekly_counter_resets_on_sunday(fresh_db):
    """Saturday and the following Sunday are different weeks."""
    for _ in range(5):
        fresh_db.bump_usage("w2", 0, day="2026-07-25", weekly_limit=0)      # Sat
    assert fresh_db.usage_this_week("w2", day="2026-07-25") == 5
    assert fresh_db.usage_this_week("w2", day="2026-07-26") == 0            # Sun — new week


def test_week_runs_sunday_to_saturday(fresh_db):
    days = fresh_db.week_days("2026-07-22")        # a Wednesday
    assert days[0] == "2026-07-19" and days[-1] == "2026-07-25"
    assert len(days) == 7


def test_units_consume_more_than_one_slot(fresh_db):
    """Weighted quota (a lesson eats 5) must not be able to step over the cap."""
    allowed, day_count, _w = fresh_db.bump_usage("w3", 10, units=5)
    assert allowed and day_count == 5
    assert fresh_db.bump_usage("w3", 10, units=5)[0]            # exactly at the cap
    assert not fresh_db.bump_usage("w3", 10, units=5)[0]        # would overshoot → refused
    assert fresh_db.usage_today("w3") == 10


def test_a_refused_weekly_bump_counts_nothing(fresh_db):
    for _ in range(3):
        fresh_db.bump_usage("w4", 0, day="2026-07-19", weekly_limit=3)
    assert not fresh_db.bump_usage("w4", 0, day="2026-07-20", weekly_limit=3)[0]
    assert fresh_db.usage_today("w4", day="2026-07-20") == 0
    assert fresh_db.usage_this_week("w4", day="2026-07-20") == 3


# ── Two independent pools ─────────────────────────────────────────────────────
def test_token_and_lesson_meters_do_not_touch_each_other(fresh_db):
    """The whole point of the split: exhausting conversation tokens must not cost a lesson, and a
    lesson must not eat conversation tokens."""
    d = "2026-07-20"
    fresh_db.bump_usage("m1", 100, day=d, units=100, meter=fresh_db.TOKENS)   # tokens fully spent
    assert not fresh_db.bump_usage("m1", 100, day=d, units=1, meter=fresh_db.TOKENS)[0]

    # Lessons are untouched and still available.
    allowed, _d, week = fresh_db.bump_usage("m1", 0, day=d, weekly_limit=3, units=1,
                                            meter=fresh_db.LESSON)
    assert allowed and week == 1
    # And the lesson did not consume token allowance.
    assert fresh_db.usage_today("m1", day=d, meter=fresh_db.TOKENS) == 100


def test_lesson_pool_is_weekly_only(fresh_db):
    """Three lessons a week means three, whether taken in one day or spread out."""
    for _ in range(3):
        assert fresh_db.bump_usage("m2", 0, day="2026-07-20", weekly_limit=3, units=1,
                                   meter=fresh_db.LESSON)[0]
    assert not fresh_db.bump_usage("m2", 0, day="2026-07-21", weekly_limit=3, units=1,
                                   meter=fresh_db.LESSON)[0]
    # Next week is a fresh allowance.
    assert fresh_db.bump_usage("m2", 0, day="2026-07-27", weekly_limit=3, units=1,
                               meter=fresh_db.LESSON)[0]


# ── Reserve then settle ───────────────────────────────────────────────────────
def test_settling_below_the_reservation_refunds_the_difference(fresh_db):
    """The normal case: the estimate is generous, so most of it comes back."""
    fresh_db.bump_usage("s1", 0, units=20_000, meter=fresh_db.TOKENS)     # reserved
    fresh_db.settle_usage("s1", reserved=20_000, actual=6_000)
    assert fresh_db.usage_today("s1", meter=fresh_db.TOKENS) == 6_000


def test_settling_above_the_reservation_charges_the_overrun(fresh_db):
    """An under-estimate must still be paid for, or a big request is partly free."""
    fresh_db.bump_usage("s2", 0, units=20_000, meter=fresh_db.TOKENS)
    fresh_db.settle_usage("s2", reserved=20_000, actual=90_000)
    assert fresh_db.usage_today("s2", meter=fresh_db.TOKENS) == 90_000


def test_settlement_cannot_mint_allowance_from_earlier_usage(fresh_db):
    """A wrong reservation must never drive the counter below what other requests already spent."""
    fresh_db.bump_usage("s3", 0, units=5_000, meter=fresh_db.TOKENS)      # an earlier request
    fresh_db.settle_usage("s3", reserved=50_000, actual=0)                # never reserved that much
    assert fresh_db.usage_today("s3", meter=fresh_db.TOKENS) == 0         # floored, not negative


def test_settlement_is_isolated_per_meter(fresh_db):
    fresh_db.bump_usage("s4", 0, units=2, meter=fresh_db.LESSON)
    fresh_db.settle_usage("s4", reserved=0, actual=7_000, meter=fresh_db.TOKENS)
    assert fresh_db.usage_today("s4", meter=fresh_db.LESSON) == 2
    assert fresh_db.usage_today("s4", meter=fresh_db.TOKENS) == 7_000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
