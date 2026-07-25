"""Coupons: issuing, redemption, and the rules that protect revenue.

The concurrency tests matter most — a coupon is money, and the failure mode of a sloppy redemption
path is "one code, many subscriptions".
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Point the DB at a scratch file per test, and reset the module-level connection."""
    monkeypatch.setenv("CHAVRUTA_DB_PATH", str(tmp_path / "t.db"))
    import app.db as db

    db._conn = None
    db.DB_PATH = tmp_path / "t.db"
    yield db
    db._conn = None


@pytest.fixture(autouse=True)
def _clear_throttle():
    import app.coupons as coupons

    coupons._attempts.clear()
    yield
    coupons._attempts.clear()


# ── Issuing ───────────────────────────────────────────────────────────────────
def test_generated_codes_are_unique_and_unambiguous():
    """Codes are guessed at, so they need entropy; they're also read aloud, so no O/0/I/1/U."""
    import app.coupons as coupons

    codes = {coupons.generate_code() for _ in range(500)}
    assert len(codes) == 500
    assert not (set("OI01U") & set("".join(codes).replace("-", "")))


def test_issue_rejects_unknown_plan_and_nonsense_amounts():
    import app.coupons as coupons

    with pytest.raises(ValueError):
        coupons.issue_plan_coupon(plan="platinum", days=30)
    with pytest.raises(ValueError):
        coupons.issue_plan_coupon(plan="pro", days=0)
    with pytest.raises(ValueError):
        coupons.issue_credit_coupon(credits=0)


def test_duplicate_code_is_refused_not_overwritten():
    """Overwriting would silently change what an already-distributed code grants."""
    import app.coupons as coupons

    coupons.issue_credit_coupon(credits=50, code="CHV-DUP")
    with pytest.raises(ValueError):
        coupons.issue_plan_coupon(plan="pro", days=30, code="CHV-DUP")


def test_code_normalisation_is_forgiving():
    import app.coupons as coupons

    coupons.issue_credit_coupon(credits=50, code="CHV-ABC-123", max_redemptions=0)
    for i, typed in enumerate(("chv-abc-123", "CHVABC123", " chv abc 123 ")):
        assert coupons.redeem(f"typer{i}", typed)["credits_added"] == 50


# ── Redemption ────────────────────────────────────────────────────────────────
def test_credits_coupon_grants_balance():
    import app.coupons as coupons
    import app.db as db

    code = coupons.issue_credit_coupon(credits=200)
    res = coupons.redeem("alice", code)
    assert res["credits_added"] == 200
    assert db.get_credits("alice") == 200


def test_plan_coupon_sets_tier_and_an_end_date():
    import app.coupons as coupons
    import app.db as db
    from app import plans

    code = coupons.issue_plan_coupon(plan="pro", days=30)
    res = coupons.redeem("bob", code)

    assert plans.canonical(db.get_plan("bob")) == "pro"
    sub = db.get_subscription("bob")
    # Written as a non-renewing grant so the EXISTING downgrade sweep expires it — no new machinery.
    assert sub["provider"] == "coupon" and sub["status"] == "canceled"
    assert sub["cancel_at_period_end"] == 1
    assert res["until"] == sub["current_period_end"]


def test_expired_plan_is_swept_back_to_free():
    """The whole point of `days`: access has to actually end."""
    import app.billing.service as billing
    import app.coupons as coupons
    import app.db as db

    code = coupons.issue_plan_coupon(plan="pro", days=1)
    coupons.redeem("carol", code, now=datetime.now(UTC) - timedelta(days=2))
    assert db.get_plan("carol") == "pro"

    assert billing.sweep_downgrades() == 1
    assert db.get_plan("carol") == "free"


def test_same_user_cannot_redeem_one_code_twice():
    import app.coupons as coupons

    code = coupons.issue_credit_coupon(credits=50, max_redemptions=10)
    coupons.redeem("dave", code)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("dave", code)
    assert e.value.reason == "already_redeemed"


def test_single_use_code_is_exhausted_after_one_person():
    import app.coupons as coupons

    code = coupons.issue_credit_coupon(credits=50)
    coupons.redeem("eve", code)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("frank", code)
    assert e.value.reason == "exhausted"


def test_multi_use_code_serves_exactly_its_cap():
    import app.coupons as coupons

    code = coupons.issue_credit_coupon(credits=10, max_redemptions=3)
    for i in range(3):
        coupons.redeem(f"user{i}", code)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("user4", code)
    assert e.value.reason == "exhausted"


def test_expired_code_is_refused():
    import app.coupons as coupons

    code = coupons.issue_credit_coupon(credits=10, expires_in_days=1)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("gina", code, now=datetime.now(UTC) + timedelta(days=2))
    assert e.value.reason == "expired"


def test_revoked_code_reads_as_invalid_not_revoked():
    """Distinguishing "revoked" from "never existed" would confirm real codes to someone probing."""
    import app.coupons as coupons
    import app.db as db

    code = coupons.issue_credit_coupon(credits=10)
    db.set_coupon_active(coupons.normalize(code), False)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("hank", code)
    assert e.value.reason == "invalid"


def test_local_user_cannot_redeem():
    import app.coupons as coupons

    code = coupons.issue_credit_coupon(credits=10)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("local", code)
    assert e.value.reason == "sign_in_required"


# ── Rules that protect existing state ─────────────────────────────────────────
def test_coupon_will_not_clobber_a_live_paid_subscription():
    """A PayPlus subscription owns its provider_ref; overwriting it would detach the account from a
    recurring charge the user is still paying."""
    import app.coupons as coupons
    import app.db as db

    db.upsert_subscription("ivan", provider="payplus", provider_ref="rec-123",
                           status="active", updated_at=datetime.now(UTC).isoformat())
    db.set_plan("ivan", "paid")
    code = coupons.issue_plan_coupon(plan="pro", days=30)

    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("ivan", code)
    assert e.value.reason == "has_paid_subscription"
    assert db.get_subscription("ivan")["provider_ref"] == "rec-123"


def test_coupon_cannot_downgrade_an_existing_tier():
    import app.coupons as coupons
    import app.db as db

    db.set_plan("judy", "institution")
    code = coupons.issue_plan_coupon(plan="basic", days=30)
    with pytest.raises(coupons.RedeemError) as e:
        coupons.redeem("judy", code)
    assert e.value.reason == "downgrade"
    assert db.get_plan("judy") == "institution"


def test_same_tier_coupons_stack_instead_of_truncating():
    """Redeeming a second 30-day code on day 1 must not throw away the other 29 days."""
    import app.coupons as coupons

    now = datetime.now(UTC)
    first = coupons.redeem("kim", coupons.issue_plan_coupon(plan="pro", days=30), now=now)
    second = coupons.redeem("kim", coupons.issue_plan_coupon(plan="pro", days=30), now=now)

    end1 = datetime.fromisoformat(first["until"])
    end2 = datetime.fromisoformat(second["until"])
    assert (end2 - end1).days == 30


def test_a_failed_redemption_grants_nothing_and_burns_nothing():
    import app.coupons as coupons
    import app.db as db

    code = coupons.issue_plan_coupon(plan="basic", days=30)
    db.set_plan("leo", "pro")
    with pytest.raises(coupons.RedeemError):
        coupons.redeem("leo", code)
    assert db.get_coupon(coupons.normalize(code))["redeemed_count"] == 0
    assert db.list_redemptions(coupons.normalize(code)) == []


# ── Concurrency: a coupon is money ────────────────────────────────────────────
def test_single_use_code_survives_a_redemption_stampede():
    """20 accounts race for one use. Exactly one may win, or the coupon has printed money."""
    import app.coupons as coupons
    import app.db as db

    code = coupons.issue_credit_coupon(credits=500)
    wins: list[str] = []
    lock = threading.Lock()

    def go(i: int) -> None:
        try:
            coupons.redeem(f"racer{i}", code)
            with lock:
                wins.append(f"racer{i}")
        except coupons.RedeemError:
            pass

    threads = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(wins) == 1, f"{len(wins)} accounts redeemed a single-use coupon"
    assert db.get_coupon(coupons.normalize(code))["redeemed_count"] == 1
    assert sum(db.get_credits(f"racer{i}") for i in range(20)) == 500


def test_credits_cannot_be_overspent_concurrently():
    """The last credit must not be spent twice — that's a free generation per race won."""
    import app.db as db

    db.add_credits("spender", 10)
    ok: list[bool] = []
    lock = threading.Lock()

    def go() -> None:
        spent, _ = db.spend_credits("spender", 1)
        with lock:
            ok.append(spent)

    threads = [threading.Thread(target=go) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(ok) == 10
    assert db.get_credits("spender") == 0


# ── Throttling ────────────────────────────────────────────────────────────────
def test_guessing_is_throttled_per_account(monkeypatch):
    import app.coupons as coupons

    monkeypatch.setattr(coupons, "_MAX_ATTEMPTS", 5)
    reasons = []
    for _ in range(8):
        try:
            coupons.redeem("prober", "ZZZZ-ZZZZ-ZZZZ")
        except coupons.RedeemError as e:
            reasons.append(e.reason)
    assert reasons.count("throttled") == 3


def test_a_success_clears_the_attempt_counter(monkeypatch):
    """Someone who mistyped twice then got it right shouldn't stay near the limit."""
    import app.coupons as coupons

    monkeypatch.setattr(coupons, "_MAX_ATTEMPTS", 5)
    code = coupons.issue_credit_coupon(credits=10)
    for _ in range(3):
        with pytest.raises(coupons.RedeemError):
            coupons.redeem("typo", "WRON-GWRO-NGXX")
    coupons.redeem("typo", code)
    assert "typo" not in coupons._attempts


# ── Plans / credit costs ──────────────────────────────────────────────────────
def test_legacy_paid_plan_still_maps_to_a_real_tier():
    """Pre-tier accounts and the PayPlus webhook both write 'paid'."""
    from app import plans

    assert plans.canonical("paid") == "pro"
    assert plans.daily_quota("paid") == plans.daily_quota("pro")


def test_unknown_plan_falls_back_to_free_not_to_access():
    from app import plans

    assert plans.canonical("sudo-admin") == "free"


def test_expensive_intents_cost_more_credits():
    from app import plans

    assert plans.credit_cost("lesson") > plans.credit_cost("qa")
    assert plans.credit_cost("qa") == 1


def test_credit_costs_can_be_flattened_by_env(monkeypatch):
    from app import plans

    monkeypatch.setenv("CHAVRUTA_CREDIT_COSTS", "")
    assert plans.credit_cost("lesson") == 1


def test_quota_env_overrides_apply(monkeypatch):
    from app import plans

    monkeypatch.setenv("CHAVRUTA_QUOTA_BASIC", "99")
    assert plans.daily_quota("basic") == 99
