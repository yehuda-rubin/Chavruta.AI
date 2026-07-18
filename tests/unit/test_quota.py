"""Free-tier daily quota persistence (app/db.py bump_usage / usage_today).

The guarantees pinned: the counter enforces the limit atomically (the Nth request over the cap is
refused WITHOUT being counted), limit<=0 is unlimited-but-counted, and counts are isolated per owner
and per UTC day (one user's usage never spills into another's, and a new day is a fresh allowance).
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
        allowed, count = fresh_db.bump_usage("u1", 3)
        assert allowed and count == i + 1
    allowed, count = fresh_db.bump_usage("u1", 3)      # 4th vs limit 3
    assert not allowed and count == 3
    assert fresh_db.usage_today("u1") == 3             # the rejected call did not increment


def test_zero_limit_is_unlimited_but_still_counts(fresh_db):
    for _ in range(10):
        allowed, _c = fresh_db.bump_usage("u2", 0)
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
        allowed, _ = fresh_db.bump_usage("c", limit)
        with rlock:
            results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == limit                 # exactly `limit` allowed, never more
    assert fresh_db.usage_today("c") == limit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
