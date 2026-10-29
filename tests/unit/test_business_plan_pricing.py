"""Unit tests for the business plan pricing and credit model:
- Free users receive 20 credits per month.
- Questions, solving mock exams/exams, and building content cost 1 question credit.
- File creation (.doc / PDF export / lesson / bagrut files) costs 5 credits standard, 3 credits under launch discount.
- Credit cards / passes: entry (50/19 ₪), learner (120/39 ₪), researcher (280/79 ₪), expansion (1000/295 ₪).
- Subscriptions: personal (100 credits/month, 29 ₪ / 240 ₪).
"""

from __future__ import annotations

import os
import pytest
from app import plans
import app.db as db


def test_credit_packs_configuration():
    packs = {p.id: p for p in plans.CREDIT_PACKS}
    assert "entry" in packs
    assert packs["entry"].credits == 50
    assert packs["entry"].price_ils == 19.0

    assert "learner" in packs
    assert packs["learner"].credits == 120
    assert packs["learner"].price_ils == 39.0

    assert "researcher" in packs
    assert packs["researcher"].credits == 280
    assert packs["researcher"].price_ils == 79.0

    assert "institution_expansion" in packs
    assert packs["institution_expansion"].credits == 1000
    assert packs["institution_expansion"].price_ils == 295.0


def test_free_tier_credits():
    free = plans.tier("free")
    assert free.monthly_credits == 20
    assert plans.public_catalogue()[0]["monthly_credits"] == 20


def test_action_and_question_credit_costs():
    # Standard questions, Chavruta, QA, Explain: 1 credit
    assert plans.credit_cost("qa") == 1
    assert plans.credit_cost("explain") == 1
    assert plans.credit_cost("chavruta") == 1

    # Solving exams / mock exams / building: 1 question credit
    assert plans.credit_cost("bagrut", action="practice") == 1
    assert plans.credit_cost("bagrut", action="check") == 1
    assert plans.credit_cost("bagrut", action="solve") == 1
    assert plans.credit_cost("bagrut", action="build") == 1
    assert plans.credit_cost("exam_solve") == 1
    assert plans.credit_cost("mock_exam_solve") == 1
    assert plans.credit_cost("build") == 1


def test_file_creation_credit_costs(monkeypatch):
    # Under launch discount (default on): 3 credits
    assert plans.file_creation_credit_cost() == 3
    assert plans.credit_cost("lesson") == 3
    assert plans.credit_cost("bagrut", action="exam") == 3
    assert plans.credit_cost("bagrut", action="summary") == 3
    assert plans.credit_cost("bagrut", action="solution") == 3
    assert plans.credit_cost("qa", has_files=True) == 3

    # When launch discount is deactivated: standard 5 credits
    monkeypatch.setenv("CHAVRUTA_LAUNCH_DISCOUNT", "0")
    assert plans.file_creation_credit_cost() == 5
    assert plans.credit_cost("lesson") == 5
    assert plans.credit_cost("bagrut", action="exam") == 5
    assert plans.credit_cost("bagrut", action="summary") == 5
    assert plans.credit_cost("qa", has_files=True) == 5


def test_free_monthly_credits_granted(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "credits_test.db")
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()

    user = "user-free-test"
    # User begins with ensure_free_monthly_credits
    credits = db.ensure_free_monthly_credits(user)
    assert credits == 20
    assert db.get_credits(user) == 20

    # Spending 1 credit (e.g. for a question or exam solve) leaves 19
    spent, balance = db.spend_credits(user, 1)
    assert spent is True
    assert balance == 19

    # Spending 3 credits (file creation under launch discount) leaves 16
    spent, balance = db.spend_credits(user, 3)
    assert spent is True
    assert balance == 16


def test_rolling_month_reset_from_account_creation(monkeypatch, tmp_path):
    from datetime import datetime, UTC
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "rolling_credits_test.db")
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()

    user = "user-rolling-month"
    tz = ZoneInfo("Asia/Jerusalem")
    # Account opened on October 15, 2026 at 14:00
    opening_time = datetime(2026, 10, 15, 14, 0, tzinfo=tz)

    credits = db.ensure_free_monthly_credits(user, now_override=opening_time)
    assert credits == 20

    # User spends 15 credits, 5 remain
    spent, balance = db.spend_credits(user, 15)
    assert spent is True
    assert balance == 5

    # Check on November 1st (calendar month boundary has passed, but NOT a month from account opening)
    nov_1 = datetime(2026, 11, 1, 10, 0, tzinfo=tz)
    c_nov1 = db.ensure_free_monthly_credits(user, now_override=nov_1)
    # Must NOT reset on the 1st of the calendar month!
    assert c_nov1 == 5
    assert db.get_credits(user) == 5

    # Check on November 10 (still before 1 month from opening)
    nov_10 = datetime(2026, 11, 10, 10, 0, tzinfo=tz)
    c_nov10 = db.ensure_free_monthly_credits(user, now_override=nov_10)
    assert c_nov10 == 5

    # Check on November 15 at 14:05 (exactly 1 month from account opening has arrived)
    nov_15 = datetime(2026, 11, 15, 14, 5, tzinfo=tz)
    c_nov15 = db.ensure_free_monthly_credits(user, now_override=nov_15)
    # Must reset back to 20!
    assert c_nov15 == 20
    assert db.get_credits(user) == 20

    # Next reset should now be December 15
    next_reset = db.get_free_credits_next_reset(user, now_override=nov_15)
    assert next_reset is not None
    assert "2026-12-15" in next_reset


def test_subscription_tiers_pricing_and_credits():
    basic = plans.tier("basic")
    assert basic.price_ils == 29.0
    assert basic.annual_price_ils == 240.0
    assert basic.monthly_credits == 100
    assert basic.weekly_lessons == 0

    plus = plans.tier("plus")
    assert plus.price_ils == 69.0
    assert plus.annual_price_ils == 590.0
    assert plus.monthly_credits == 280
    assert plus.weekly_lessons == 0

    pro = plans.tier("pro")
    assert pro.price_ils == 129.0
    assert pro.annual_price_ils == 1090.0
    assert pro.monthly_credits == 600
    assert pro.weekly_lessons == 0


def test_no_standalone_lesson_quota():
    # All tiers have weekly_lessons == 0 (no separate weekly lesson counter)
    for t in plans.TIERS:
        assert t.weekly_lessons == 0
        assert plans.weekly_lessons(t.id) == 0


def test_institutional_tiers_pricing_and_credits():
    inst = plans.tier("institution")
    assert inst.price_ils == 460.0
    assert inst.monthly_credits == 1500
    assert inst.name_he == "כולל / בית מדרש"

    inst_50 = plans.tier("institution_50")
    assert inst_50.price_ils == 932.0
    assert inst_50.monthly_credits == 3500
    assert inst_50.name_he == "ישיבה רגילה"

    inst_100 = plans.tier("institution_100")
    assert inst_100.price_ils == 1994.0
    assert inst_100.monthly_credits == 7000
    assert inst_100.name_he == "ישיבה גדולה"



