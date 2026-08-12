"""BYOK (bring-your-own-key) quota fallback (app/api.py::_reserve_tokens / _charge_lesson_unit /
_byok_supported).

The guarantee: once the plan's OWN allowance (db.TOKENS / db.LESSON) is exhausted, a caller-supplied
provider key buys a SECOND allowance of the exact same size, tracked in its own meter
(db.BYOK_TOKENS / db.BYOK_LESSON) — so the two pools never mix, and no key means the old refuse-or-
spend-credits behaviour is completely unchanged.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.api as api
import app.db as db
import app.plans as plans

# A daily cap that fits ONE qa turn and not two. DERIVED, not hardcoded: these tests pin the
# BEHAVIOUR (one turn fits, the next is refused unless a key is supplied), and the hardcoded 25,000
# they used to carry silently became a cap SMALLER than one turn the moment the generation budgets
# and their reservations were raised (2026-08-12), turning every one of them into a false 429.
#
# The 1.5x headroom is not cosmetic. A cap of exactly one reservation leaves zero slack, so any
# stray token already metered against the owner makes even the FIRST turn fail — which showed up as
# an intermittent failure that passed when the file was run alone. The old pair (25,000 against a
# 20,000 estimate) had the same 1.25x slack; keeping it is what makes these tests deterministic.
_ONE_TURN = plans.token_estimate("qa")
_DAY_CAP = int(_ONE_TURN * 1.5)


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "byok.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


@pytest.fixture
def api_backend(monkeypatch):
    """A fake pipeline whose profile names an OpenAI-compatible backend — the shape _byok_supported
    checks. 'bridge' is exercised separately."""
    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="api"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    return fake


def test_byok_supported_false_for_bridge_backend(monkeypatch):
    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="bridge"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    assert api._byok_supported() is False


def test_byok_supported_true_for_api_backend(api_backend):
    assert api._byok_supported() is True


def test_byok_supported_false_when_profile_missing(monkeypatch):
    """Defensive: some tests inject a bare fake pipeline with no .profile at all."""
    monkeypatch.setattr(api, "_get_pipeline", lambda: SimpleNamespace())
    assert api._byok_supported() is False


# ── _reserve_tokens (conversation pool) ───────────────────────────────────────
def test_no_key_behaves_exactly_as_before(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    res = api._reserve_tokens("u1", "he", "qa")
    assert res.tokens > 0 and res.used_byok is False
    assert db.usage_today("u1", meter=db.TOKENS) == res.tokens


def test_key_unused_while_the_plan_quota_still_has_room(fresh_db, api_backend, monkeypatch):
    """A key is only ever spent as a FALLBACK — never touched while the plan's own pool has room."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    res = api._reserve_tokens("u2", "he", "qa", user_key="sk-user")
    assert res.used_byok is False
    assert db.usage_today("u2", meter=db.BYOK_TOKENS) == 0


def test_key_admits_a_second_allowance_once_the_plan_quota_is_spent(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    db.bump_usage("u3", _DAY_CAP, units=_DAY_CAP, meter=db.TOKENS)   # spend the plan's own pool outright

    res = api._reserve_tokens("u3", "he", "qa", user_key="sk-user")
    assert res.used_byok is True and res.tokens > 0
    assert db.usage_today("u3", meter=db.BYOK_TOKENS) == res.tokens
    assert db.usage_today("u3", meter=db.TOKENS) == _DAY_CAP     # the plan's own pool untouched


def test_no_key_still_refuses_once_the_plan_quota_is_spent(fresh_db, api_backend, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u4", _DAY_CAP, units=_DAY_CAP, meter=db.TOKENS)

    with pytest.raises(HTTPException) as exc:
        api._reserve_tokens("u4", "he", "qa")
    assert exc.value.status_code == 429


def test_key_also_refused_once_both_pools_are_spent(fresh_db, api_backend, monkeypatch):
    """A key is not an unlimited escape hatch — it is exactly one more allowance the same size."""
    from fastapi import HTTPException

    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u5", _DAY_CAP, units=_DAY_CAP, meter=db.TOKENS)
    db.bump_usage("u5", _DAY_CAP, units=_DAY_CAP, meter=db.BYOK_TOKENS)

    with pytest.raises(HTTPException) as exc:
        api._reserve_tokens("u5", "he", "qa", user_key="sk-user")
    assert exc.value.status_code == 429


def test_key_ignored_when_backend_does_not_support_byok(fresh_db, monkeypatch):
    """The bridge backend has no provider-key concept — a supplied key must not grant anything."""
    from fastapi import HTTPException

    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="bridge"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u6", _DAY_CAP, units=_DAY_CAP, meter=db.TOKENS)

    with pytest.raises(HTTPException):
        api._reserve_tokens("u6", "he", "qa", user_key="sk-user")
    assert db.usage_today("u6", meter=db.BYOK_TOKENS) == 0


# ── _charge_lesson_unit (its own weekly-count pool, charged post-hoc for a REAL lesson only —
# see _metered / test_bug_regressions.py for the fix that made "post-hoc" true) ───────────────
def test_lesson_unit_goes_to_the_byok_pool_when_the_turn_ran_on_byok(fresh_db, api_backend, monkeypatch):
    """used_byok is now an INPUT (decided once, at reservation time, by _resolve_llm_for_request) —
    not re-derived here. A turn that ran on the caller's own key charges BYOK_LESSON directly,
    leaving the plan's own LESSON pool untouched either way."""
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    db.bump_usage("u7", 0, weekly_limit=1, units=1, meter=db.LESSON)   # the plan's own lesson already spent

    api._charge_lesson_unit("u7", api.Reservation(0), used_byok=True)
    assert db.usage_this_week("u7", meter=db.BYOK_LESSON) == 1
    assert db.usage_this_week("u7", meter=db.LESSON) == 1    # unchanged


def test_lesson_unit_goes_to_the_plan_pool_by_default(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "3")
    api._charge_lesson_unit("u7b", api.Reservation(0), used_byok=False)
    assert db.usage_this_week("u7b", meter=db.LESSON) == 1
    assert db.usage_this_week("u7b", meter=db.BYOK_LESSON) == 0


def test_lesson_unit_falls_back_to_credits_once_the_plan_pool_is_spent(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    db.bump_usage("u7c", 0, weekly_limit=1, units=1, meter=db.LESSON)
    spent_calls = []
    monkeypatch.setattr(db, "spend_credits",
                        lambda owner, cost: (spent_calls.append((owner, cost)), (True, 3))[1])

    api._charge_lesson_unit("u7c", api.Reservation(0), used_byok=False)
    assert spent_calls == [("u7c", api.plans.credit_cost("lesson"))]


def test_lesson_unit_never_raises_even_fully_exhausted(fresh_db, api_backend, monkeypatch):
    """Charged post-hoc, after the lesson is already built and being returned — must never 429 a
    completed request. Falls through to a log line instead (see the function's own docstring)."""
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    db.bump_usage("u7d", 0, weekly_limit=1, units=1, meter=db.LESSON)
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))

    api._charge_lesson_unit("u7d", api.Reservation(0), used_byok=False)   # must not raise


# ── _resolve_llm_for_request (route-level wiring) ─────────────────────────────
def test_resolve_llm_for_request_builds_a_llm_override_only_on_byok(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    sentinel = object()
    monkeypatch.setattr(api, "_byok_llm", lambda key, base_url="", model="": sentinel)

    # Plan quota has room: no override, TOKENS meter.
    reserved, llm, meter = api._resolve_llm_for_request("u8", "he", "qa", "sk-user")
    assert llm is None and meter == db.TOKENS

    # Plan quota spent: override present, BYOK_TOKENS meter.
    db.bump_usage("u8", 25_000, units=25_000, meter=db.TOKENS)
    reserved, llm, meter = api._resolve_llm_for_request("u8", "he", "qa", "sk-user")
    assert llm is sentinel and meter == db.BYOK_TOKENS and reserved.tokens > 0


def test_resolve_llm_for_request_tolerates_the_fastapi_header_marker(fresh_db, api_backend, monkeypatch):
    """A handful of existing tests call route functions directly, bypassing FastAPI's dependency
    injection — the Header(...) marker object itself lands in user_key rather than a str/None. Must
    not crash, and must behave exactly like "no key supplied"."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")

    class _NotAString:
        pass

    reserved, llm, meter = api._resolve_llm_for_request("u9", "he", "qa", _NotAString())
    assert llm is None and meter == db.TOKENS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── The reservation is carried, not re-resolved (spec 004) ───────────────────
# Both docstrings claimed this and neither implementation did it: _reserve_tokens discarded the
# context it had just resolved and _settle_tokens looked it up again. Everything below is a way for
# the world to change between those two moments, which the async paths make minutes long.

@pytest.fixture
def school(fresh_db):
    import app.orgs as orgs
    oid = orgs.create_org("boss", "בית ספר", "institution")
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.STUDENT), "pupil")
    return oid


def test_removing_a_member_mid_request_still_releases_the_schools_reservation(school, api_backend):
    """Otherwise the pool keeps the full estimate for that turn, permanently — nothing left in the
    world knows it is owed. An admin removing a class at end of term does this once per in-flight
    turn, and the school's day and week drift upward forever."""
    import app.orgs as orgs
    res = api._reserve_tokens("pupil", "he", "qa")
    pool = res.ctx["pool_id"]
    reserved_total = db.usage_today(pool)
    assert reserved_total == res.tokens

    orgs.remove_member(school, "pupil")
    api._settle_tokens("pupil", res, {"prompt_tokens": 100, "completion_tokens": 10}, "qa")

    assert db.usage_today(pool) == plans.normalized_tokens(100, 10)


def test_joining_mid_request_does_not_refund_a_stranger_into_the_pool(school, api_backend):
    """The mirror direction: a non-member reserves on their own counter, joins while the job runs,
    and settlement credited the SCHOOL capacity it had never spent."""
    import app.orgs as orgs
    res = api._reserve_tokens("newcomer", "he", "qa")
    assert res.ctx is None
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0,
                   units=50_000)

    orgs.remove_member(school, "pupil")
    orgs.accept_invite(orgs.create_invite(school, "boss", orgs.STUDENT), "newcomer")
    api._settle_tokens("newcomer", res, {"prompt_tokens": 100, "completion_tokens": 10}, "qa")

    assert db.usage_today(ctx["pool_id"]) == 50_000       # untouched by a turn it never admitted
    assert db.usage_today("newcomer") == plans.normalized_tokens(100, 10)


def test_a_turn_that_crosses_midnight_settles_against_the_day_it_reserved(fresh_db, api_backend,
                                                                          monkeypatch):
    """Reserve at 23:59, settle at 00:01: yesterday used to keep the full estimate forever while
    today was credited usage it never had — both counters drifting, in opposite directions."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    res = api._reserve_tokens("owl", "he", "qa")
    assert db.usage_today("owl") == res.tokens

    monkeypatch.setattr(db, "today_il", lambda: "2999-01-01")     # the clock rolls over
    api._settle_tokens("owl", res, {"prompt_tokens": 100, "completion_tokens": 10}, "qa")

    assert db.usage_today("owl") == 0                             # the new day was never charged
    with db._LOCK:
        row = db.get_conn().execute(
            "SELECT count FROM usage_counters WHERE owner_id=? AND day=? AND meter=?",
            ("owl", res.day, db.TOKENS)).fetchone()
    assert row["count"] == plans.normalized_tokens(100, 10)       # the reserving day was corrected


# ── A lesson nobody could pay for is not free ────────────────────────────────
def test_a_lesson_past_the_schools_weekly_count_is_paid_for_in_tokens(school, api_backend):
    """It used to cost NOTHING: the refused lesson bump left the counter pinned, and the turn's token
    reservation was refunded in full — so lesson #81 and every one after it was free and unbounded,
    at the most expensive operation in the product, with the panel still reporting '80 of 80'."""
    import app.orgs as orgs
    ctx = orgs.quota_context("pupil")
    db.bump_usage(ctx["pool_id"], 0, weekly_limit=0, units=ctx["weekly_lessons"], meter=db.LESSON)

    res = api._reserve_tokens("pupil", "he", "lesson")
    unpaid = api._charge_lesson_unit("pupil", res, used_byok=False)
    assert unpaid is True

    api._settle_tokens("pupil", res, {"prompt_tokens": 40_000, "completion_tokens": 6_000}, "lesson")
    assert db.usage_today(ctx["pool_id"]) == plans.normalized_tokens(40_000, 6_000)


def test_a_lesson_within_the_count_still_costs_no_tokens(school, api_backend):
    """The rule that must survive the fix above: a lesson is paid for by the lesson pool, once."""
    import app.orgs as orgs
    ctx = orgs.quota_context("pupil")
    res = api._reserve_tokens("pupil", "he", "lesson")
    assert api._charge_lesson_unit("pupil", res, used_byok=False) is False
    api._settle_tokens("pupil", res, {}, "lesson")
    assert db.usage_today(ctx["pool_id"]) == 0
    assert db.usage_this_week(ctx["pool_id"], meter=db.LESSON) == 1


# ── Two pools, one generation: it must not be paid for twice ─────────────────
def test_one_lesson_does_not_cost_two_credit_charges(fresh_db, api_backend, monkeypatch):
    """When BOTH pools are exhausted, _reserve_tokens spent credits to admit the turn and
    _charge_lesson_unit spent the same amount again — ten credits for one lesson, twice its
    documented price, and told nobody."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", str(_DAY_CAP))
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    db.add_credits("u10", 10)
    db.bump_usage("u10", _DAY_CAP, units=_DAY_CAP, meter=db.TOKENS)      # tokens gone
    db.bump_usage("u10", 0, weekly_limit=1, units=1, meter=db.LESSON)    # lessons gone

    res = api._reserve_tokens("u10", "he", "lesson")
    assert res.paid_with_credits is True
    after_entry = db.get_credits("u10")

    assert api._charge_lesson_unit("u10", res, used_byok=False) is False   # already paid for
    assert db.get_credits("u10") == after_entry
    assert after_entry == 10 - plans.credit_cost("lesson")


def test_a_lesson_nobody_could_pay_for_reports_itself_unpaid(fresh_db, api_backend, monkeypatch):
    """The personal mirror of the org case: over the weekly lesson count with no credits left. Its
    return value is what makes _metered settle the turn at real usage instead of refunding it."""
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u11", 0, weekly_limit=1, units=1, meter=db.LESSON)
    assert api._charge_lesson_unit("u11", api.Reservation(0), used_byok=False) is True


def test_a_lesson_within_quota_reports_itself_paid(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "3")
    assert api._charge_lesson_unit("u12", api.Reservation(0), used_byok=False) is False
    assert api._charge_lesson_unit("local", api.Reservation(0), used_byok=False) is False


def test_metered_settles_an_unpayable_lesson_at_real_usage(fresh_db, api_backend, monkeypatch):
    """The other half of the seam: _charge_lesson_unit returning True only matters if _metered acts
    on it. Inverting the ternary there makes the most expensive operation free again."""
    from chavruta.llm import metering as metering_mod

    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "500000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    monkeypatch.setattr(api, "_record_event", lambda *a, **k: None)
    db.bump_usage("u13", 0, weekly_limit=1, units=1, meter=db.LESSON)
    res = api._reserve_tokens("u13", "he", "lesson")     # a REAL reservation, really charged

    def _lesson():
        metering_mod.record(40_000, 6_000)
        return api.QueryResponse(answer="a", citations=[], grounded=True, intent="lesson",
                                 files=[{"name": "f", "title": "t", "content": "c"}],
                                 lesson_id="L9")

    api._metered("u13", res, "lesson", _lesson)()
    assert db.usage_today("u13") == plans.normalized_tokens(40_000, 6_000)


# ── What a refused member is actually told ───────────────────────────────────
@pytest.fixture
def _school(fresh_db):
    import app.orgs as orgs
    oid = orgs.create_org("boss", "ישיבת דוגמה", "institution")
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.STUDENT), "pupil")
    return oid


def _refusal(intent="qa", lang="he"):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        api._reserve_tokens("pupil", lang, intent)
    assert exc.value.status_code == 429
    return exc.value.detail


def test_an_exhausted_week_does_not_claim_it_resets_tomorrow(_school, api_backend, monkeypatch):
    """The old message said 'tomorrow' whichever of the three ceilings bit, and closed by telling
    the reader to upgrade their plan or redeem a coupon — two things the server refuses a member."""
    import app.orgs as orgs
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_INSTITUTION", "1000")
    orgs.set_member_cap(_school, "pupil", 10_000_000)
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0,
                   units=999)
    detail = _refusal()
    assert "ראשון" in detail and "מחר" not in detail
    assert "קופון" not in detail and "שדרג" not in detail


def test_a_blocked_member_is_told_they_were_paused_by_their_school(_school, api_backend):
    import app.orgs as orgs
    orgs.set_member_cap(_school, "pupil", orgs.CAP_BLOCKED)
    assert "מנהל המוסד" in _refusal()


def test_a_member_over_their_own_cap_is_told_it_is_theirs(_school, api_backend):
    import app.orgs as orgs
    orgs.set_member_cap(_school, "pupil", 100)
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0,
                   units=100)
    detail = _refusal()
    assert "מנהל המוסד" in detail and "מחר" in detail          # their own ceiling, renewed daily


def test_the_schools_exhausted_day_names_the_school(_school, api_backend, monkeypatch):
    import app.orgs as orgs
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_INSTITUTION", "1000")
    # An explicit ceiling well above the pool, so it is the POOL that refuses and not the member cap
    # (which is floored at the pool size — see orgs.member_cap).
    orgs.set_member_cap(_school, "pupil", 10_000_000)
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0,
                   units=999)
    assert "ישיבת דוגמה" in _refusal()
