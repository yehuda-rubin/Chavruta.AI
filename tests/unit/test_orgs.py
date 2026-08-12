"""Organisations: membership, the shared pool, and the attacks the security review predicted.

Spec 004. Each test names the failure it prevents, because most of them are things that looked fine
in the first draft of the plan and only broke under a concrete scenario.
"""

from __future__ import annotations

import pytest

import app.db as db
import app.orgs as orgs
import app.plans as plans


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "orgs.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


@pytest.fixture
def school(fresh_db):
    oid = orgs.create_org("boss", "בית ספר", "institution")
    return oid


def _join(oid, who, role=orgs.STUDENT, by="boss"):
    return orgs.accept_invite(orgs.create_invite(oid, by, role), who)


# ── The rank check: a teacher must not be able to remove the paying admin ─────
# All three of the plan's originally-stated checks pass for this — member of the org, role permits
# "remove", target in the same org — and the org ends up headless or inherited by the teacher.
def test_a_teacher_cannot_act_on_the_admin(school):
    _join(school, "teach", orgs.TEACHER)
    actor = orgs.require_member("teach", school, orgs.TEACHER)
    with pytest.raises(orgs.OrgAccessError):
        orgs.require_can_act_on(actor, "boss")


def test_a_teacher_can_act_on_a_student(school):
    _join(school, "teach", orgs.TEACHER)
    _join(school, "pupil")
    actor = orgs.require_member("teach", school, orgs.TEACHER)
    assert orgs.require_can_act_on(actor, "pupil")["role"] == orgs.STUDENT


def test_a_student_has_no_management_role(school):
    _join(school, "pupil")
    with pytest.raises(orgs.OrgAccessError):
        orgs.require_member("pupil", school, orgs.TEACHER)


def test_membership_in_another_org_is_not_membership_here(fresh_db):
    a = orgs.create_org("boss-a", "A", "institution")
    orgs.create_org("boss-b", "B", "institution")
    with pytest.raises(orgs.OrgAccessError):
        orgs.require_member("boss-b", a, orgs.STUDENT)


# ── Quota resolution must be decidable ────────────────────────────────────────
def test_a_person_can_hold_only_one_accepted_membership(fresh_db):
    """With two, 'which pool does this turn charge' has no answer — and whichever way bump_pooled
    happened to be wired would become the answer by accident."""
    a = orgs.create_org("boss-a", "A", "institution")
    b = orgs.create_org("boss-b", "B", "institution")
    _join(a, "pupil", by="boss-a")
    with pytest.raises(orgs.JoinRefused):
        orgs.accept_invite(orgs.create_invite(b, "boss-b", orgs.STUDENT), "pupil")


def test_an_account_with_a_paid_plan_cannot_join(school, fresh_db):
    """And the test is on the EFFECTIVE plan, not subscriptions.status — a coupon-granted plan is
    stored as 'canceled' with a future period end and would otherwise slip straight past."""
    db.set_plan("richer", "pro")
    with pytest.raises(orgs.JoinRefused):
        orgs.accept_invite(orgs.create_invite(school, "boss", orgs.STUDENT), "richer")


def test_an_org_owner_cannot_join_another_org(fresh_db):
    a = orgs.create_org("boss-a", "A", "institution")
    b = orgs.create_org("boss-b", "B", "institution")
    with pytest.raises(orgs.JoinRefused):
        orgs.accept_invite(orgs.create_invite(b, "boss-b", orgs.STUDENT), "boss-a")


def test_a_pending_invitation_grants_nothing(school):
    orgs.create_invite(school, "boss", orgs.STUDENT)
    assert orgs.membership("nobody") is None
    assert orgs.quota_context("nobody") is None


# ── Join codes ────────────────────────────────────────────────────────────────
def test_a_code_cannot_be_spent_past_its_use_count(school):
    code = orgs.create_invite(school, "boss", orgs.STUDENT, max_uses=1)
    orgs.accept_invite(code, "first")
    with pytest.raises(orgs.JoinRefused):
        orgs.accept_invite(code, "second")


def test_an_expired_code_is_refused(school):
    code = orgs.create_invite(school, "boss", orgs.STUDENT, expires_at="2000-01-01T00:00:00")
    with pytest.raises(orgs.JoinRefused):
        orgs.accept_invite(code, "late")


def test_seats_are_bounded_by_the_tier(fresh_db, monkeypatch):
    """Seat admission is check-and-insert in ONE transaction, like bump_usage — otherwise concurrent
    accepts each read 'there is room' and all of them proceed."""
    small = orgs.create_org("boss", "S", "institution")
    monkeypatch.setattr(plans, "tier", lambda p: plans.Tier(
        "institution", 8_000_000, 21_000_000, 80, 40, 649.0, 6490.0, "x", "x", 2))
    _join(small, "one")                                   # owner + one = 2 seats, full
    with pytest.raises(orgs.JoinRefused):
        orgs.accept_invite(orgs.create_invite(small, "boss", orgs.STUDENT), "two")


def test_removal_deletes_the_row_so_a_code_cannot_resurrect_it(school):
    _join(school, "pupil")
    assert orgs.remove_member(school, "pupil") is True
    assert orgs.membership("pupil") is None


# ── The shared pool ───────────────────────────────────────────────────────────
def test_a_turn_charges_both_the_member_and_the_pool(school):
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    ok, pool_day, _, _ = db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=ctx["member_cap"],
                                     pool_daily=ctx["pool_daily"], pool_weekly=ctx["pool_weekly"],
                                     units=1000)
    assert ok and pool_day == 1000
    assert db.usage_today(ctx["member_id"]) == 1000
    assert db.usage_today(ctx["pool_id"]) == 1000


def test_the_member_cap_bounds_one_persons_share_of_the_pool(school):
    """Without it a single student spends the school's entire day in an hour."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    ok, _, _, _ = db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=500,
                              pool_daily=ctx["pool_daily"], pool_weekly=ctx["pool_weekly"],
                              units=501)
    assert ok is False
    assert db.usage_today(ctx["member_id"]) == 0        # refused means NOTHING moved, on either counter
    assert db.usage_today(ctx["pool_id"]) == 0


def test_the_pool_bounds_the_school_even_when_a_member_is_under_their_cap(school):
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    ok, _, _, _ = db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=100,
                              pool_weekly=0, units=101)
    assert ok is False


def test_a_refused_pooled_charge_moves_neither_counter(school):
    """The reason this is one transaction rather than two bump_usage calls: charging the member and
    then discovering the pool is full would need an exact refund, and settle floors at zero."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=1000, pool_weekly=0, units=900)
    before_member = db.usage_today(ctx["member_id"])
    before_pool = db.usage_today(ctx["pool_id"])
    ok, _, _, _ = db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=1000,
                              pool_weekly=0, units=200)
    assert ok is False
    assert db.usage_today(ctx["member_id"]) == before_member
    assert db.usage_today(ctx["pool_id"]) == before_pool


def test_settlement_corrects_both_counters(school):
    """Reservations are deliberately generous, so settlement is normally a refund. If only the
    member's row were settled the school would be charged the ESTIMATE for every turn and its pool
    would empty several times faster than real use."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0, units=30_000)
    db.settle_pooled(ctx["member_id"], ctx["pool_id"], reserved=30_000, actual=4_000)
    assert db.usage_today(ctx["member_id"]) == 4_000
    assert db.usage_today(ctx["pool_id"]) == 4_000


def test_a_non_member_has_no_quota_context(fresh_db):
    """The whole existing single-user path must stay untouched — that is what makes this safe to add
    to a live product."""
    assert orgs.quota_context("someone") is None


def test_the_member_cap_defaults_to_more_than_an_even_share(school):
    """An even split of an institution pool IS the free allowance, which is nothing to buy. The
    default cap is deliberate over-subscription — capacity moving to whoever studies today is what
    pooling means."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    even_share = plans.daily_tokens("institution") // plans.tier("institution").seats
    assert ctx["member_cap"] > even_share


# ── The operator's sample school ──────────────────────────────────────────────
def test_the_demo_org_is_a_fixed_id_and_is_idempotent(fresh_db):
    """It takes no id from the client, which is what makes it a simulator and not impersonation."""
    first = orgs.ensure_demo_org()
    assert first == orgs.DEMO_ORG_ID
    assert orgs.ensure_demo_org() == first
    assert orgs.get_org(first)["is_demo"] == 1
    assert len(orgs.members(first)) > 1


def test_the_demo_org_holds_only_synthetic_members(fresh_db, monkeypatch):
    """Every id in the sample school is invented, INCLUDING the owner.

    The previous version of this assertion excused any id without an '@' in it — true of every
    Supabase UUID, so it passed while the demo org was owned by the operator's real production
    account. One look at the panel turned that account into a school member for good: its questions
    charged the demo pool, it could no longer buy or be granted anything, and it became undeletable.
    """
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "real-operator-uuid")
    orgs.ensure_demo_org()
    owners = {m["owner_id"] for m in orgs.members(orgs.DEMO_ORG_ID)}
    assert owners == {orgs.DEMO_OWNER, "demo-teacher-1", "demo-student-1",
                      "demo-student-2", "demo-student-3"}
    assert orgs.get_org(orgs.DEMO_ORG_ID)["owner_id"] == orgs.DEMO_OWNER
    assert orgs.membership("real-operator-uuid") is None
    assert db.owns_org("real-operator-uuid") is False


# ── The access log ────────────────────────────────────────────────────────────
def test_opening_the_panel_is_recorded(school):
    orgs.log_access(school, "boss", "view_panel", "pupil")
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT actor_owner_id, target_owner_id, action FROM org_access_log WHERE org_id=?",
            (school,)).fetchall()
    assert [tuple(r) for r in rows] == [("boss", "pupil", "view_panel")]


# ── A member has no personal wallet ───────────────────────────────────────────
# Everything below defends the same invariant from a different door: a school member spends the
# org's pool and NOTHING else. app/api.py::_reserve_tokens branches on orgs.quota_context before it
# ever reaches credits or a personal plan, so anything sold or granted to a member personally is
# money (or operator goodwill) that buys literally nothing. Silence would look like success.

def test_a_member_cannot_check_out_a_personal_plan(school, monkeypatch):
    from app.billing import payplus, service as billing

    monkeypatch.setattr(payplus, "enabled", lambda: True)
    _join(school, "pupil")
    with pytest.raises(ValueError):
        billing.start_checkout("pupil", "p@example.com", "Pupil", plan="pro")


def test_a_non_member_can_still_check_out(school, monkeypatch):
    """The guard must not touch the path every existing paying user takes."""
    from app.billing import payplus, service as billing

    monkeypatch.setattr(payplus, "enabled", lambda: True)
    monkeypatch.setattr(payplus, "create_payment_page",
                        lambda *a, **k: {"link": "https://pay.example/x"})
    assert billing.start_checkout("outsider", "o@example.com", "O", plan="pro")


def test_a_member_cannot_redeem_a_plan_coupon(school):
    import app.coupons as coupons

    _join(school, "pupil")
    code = coupons.issue_plan_coupon(plan="pro", days=30, max_redemptions=1)
    with pytest.raises(coupons.RedeemError) as exc:
        coupons.redeem("pupil", code)
    assert exc.value.reason == "org_member"


def test_a_member_cannot_be_granted_credits_either(school):
    """Same door as /admin/grant, which mints a code and redeems it on the account's behalf — so the
    refusal has to live in redeem() to cover the operator path too."""
    import app.coupons as coupons

    _join(school, "pupil")
    code = coupons.issue_credit_coupon(credits=100, max_redemptions=1)
    with pytest.raises(coupons.RedeemError) as exc:
        coupons.redeem("pupil", code, bypass_throttle=True)
    assert exc.value.reason == "org_member"
    assert db.get_credits("pupil") == 0


def test_leaving_the_org_restores_the_ability_to_buy(school):
    import app.coupons as coupons

    _join(school, "pupil")
    orgs.remove_member(school, "pupil")
    code = coupons.issue_plan_coupon(plan="pro", days=30, max_redemptions=1)
    assert coupons.redeem("pupil", code)["kind"] == "plan"


# ── Deletion ──────────────────────────────────────────────────────────────────
def test_deleting_a_member_frees_the_seat(school):
    _join(school, "pupil")
    assert orgs.seats_used(school) == 2
    db.purge_owner("pupil")
    assert orgs.seats_used(school) == 1
    assert orgs.membership("pupil") is None


def test_deleting_a_member_keeps_the_audit_trail_but_not_their_name(school):
    """A departing administrator must not be able to erase the record of what they looked at — the
    one thing that trail exists to prevent."""
    _join(school, "teach", orgs.TEACHER)
    orgs.log_access(school, "teach", "view_panel", "pupil")
    db.purge_owner("teach")
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT actor_owner_id, action FROM org_access_log WHERE org_id=?", (school,)).fetchall()
    assert [tuple(r) for r in rows] == [(db.DELETED_OWNER, "view_panel")]


def test_the_org_owner_cannot_be_purged(school):
    """orgs.owner_id is the only link between a school and the person who pays for it. Purging them
    would leave a live org pointing at a dead account: the members keep spending a pool nobody can
    administer, and nothing anywhere would error."""
    with pytest.raises(db.OwnsOrganisation):
        db.purge_owner("boss")
    assert orgs.get_org(school) is not None


def test_purging_an_unrelated_account_is_unaffected(school):
    db.purge_owner("stranger")     # must not raise
    assert orgs.get_org(school) is not None


# ── The payer must be able to pay ─────────────────────────────────────────────
# create_org makes the owner an accepted ADMIN member, so the first cut of the wallet guard — which
# tested membership alone — locked the paying customer out of buying, renewing or being granted the
# very subscription that funds the school, with no transfer route and no way to leave. One test per
# role, so which side of the line each sits on is written down rather than implied.

@pytest.fixture
def _payplus(monkeypatch):
    from app.billing import payplus
    monkeypatch.setattr(payplus, "enabled", lambda: True)
    monkeypatch.setattr(payplus, "create_payment_page", lambda *a, **k: {"link": "https://pay/x"})
    return payplus


def test_the_owner_can_buy_the_schools_own_plan(school, _payplus):
    from app.billing import service as billing
    assert billing.start_checkout("boss", "b@e.com", "B", plan="institution_50")


def test_the_owner_still_cannot_buy_a_personal_plan(school, _payplus):
    """They spend the pool like everyone else, so 'pro' would buy them nothing either."""
    from app.billing import service as billing
    with pytest.raises(ValueError):
        billing.start_checkout("boss", "b@e.com", "B", plan="pro")


def test_a_teacher_cannot_buy_an_institution_plan_for_themselves(school, _payplus):
    from app.billing import service as billing
    _join(school, "teach", orgs.TEACHER)
    with pytest.raises(ValueError):
        billing.start_checkout("teach", "t@e.com", "T", plan="institution")


def test_the_operator_can_grant_a_school_its_plan(school):
    """/admin/grant mints a code and redeems it on the account's behalf — the provisioning path."""
    import app.coupons as coupons
    code = coupons.issue_plan_coupon(plan="institution", days=30, max_redemptions=1)
    assert coupons.redeem("boss", code, bypass_throttle=True)["kind"] == "plan"


def test_the_owner_cannot_be_granted_credits(school):
    import app.coupons as coupons
    code = coupons.issue_credit_coupon(credits=50, max_redemptions=1)
    with pytest.raises(coupons.RedeemError):
        coupons.redeem("boss", code, bypass_throttle=True)


# ── Joining in the other order ────────────────────────────────────────────────
def test_a_checkout_in_flight_blocks_joining(school):
    """start_checkout writes a 'pending' subscription but does NOT set accounts.plan, so the plan
    test alone still read 'free' for someone sitting on the payment page. Join there and the webhook
    then activates a real recurring charge on an account that spends the pool instead."""
    db.upsert_subscription("shopper", provider="payplus", status="pending", plan="pro",
                           updated_at=db._now())
    with pytest.raises(orgs.JoinRefused):
        _join(school, "shopper")


def test_unspent_credits_block_joining(school):
    """A member has no credit fallback, so joining with a balance strands something they paid for."""
    db.add_credits("saver", 40)
    with pytest.raises(orgs.JoinRefused):
        _join(school, "saver")


# ── The member's counter is not their personal one ───────────────────────────
def test_leaving_a_school_does_not_spend_the_persons_own_free_week(school):
    """A student who spent the school's pool on Sunday and left on Monday used to be locked out of
    the free product until the following Sunday — their personal weekly allowance is smaller than
    the school-funded day they had just had, and both were the same counter row."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0,
                   units=600_000)
    orgs.remove_member(school, "pupil")
    assert db.usage_today("pupil") == 0
    assert db.usage_this_week("pupil") == 0


def test_joining_mid_day_gives_the_full_member_cap(school):
    """The mirror: a free user who had already spent that morning used to get a reduced share of the
    school's pool, for a reason nobody could see."""
    db.bump_usage("newcomer", 0, units=150_000)
    _join(school, "newcomer")
    ctx = orgs.quota_context("newcomer")
    assert db.usage_today(ctx["member_id"]) == 0


def test_the_member_cap_follows_the_tier(fresh_db, monkeypatch):
    """It used to be a constant that ignored its argument, correct only because all three tiers
    happen to share a per-seat allowance — and daily_tokens honours per-tier env overrides, so a
    throttled pool kept a ceiling two members could drain it with."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_INSTITUTION", "1000000")
    assert orgs.member_cap("institution") < orgs.member_cap("institution_100")
    for tier_id in ("institution", "institution_50", "institution_100"):
        share = plans.daily_tokens(tier_id) // plans.tier(tier_id).seats
        assert orgs.member_cap(tier_id) >= share


# ── The pool's own ceilings ──────────────────────────────────────────────────
def test_the_weekly_pool_refuses_and_says_so(school):
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0,
                   pool_weekly=1000, units=900)
    charge = db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=0,
                            pool_weekly=1000, units=200)
    assert charge.allowed is False
    assert charge.refused == "week"      # not "day" — it resets on Sunday, not tomorrow


def test_each_ceiling_names_itself(school):
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    assert db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=10, pool_daily=0,
                          pool_weekly=0, units=99).refused == "member_cap"
    assert db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=0, pool_daily=10,
                          pool_weekly=0, units=99).refused == "day"


# ── A school's tier follows its payer ────────────────────────────────────────
def test_a_lapsed_subscription_degrades_the_pool(school):
    """Nothing used to write orgs.plan after creation, so a school that stopped paying kept its full
    institution pool forever while the panel cheerfully rendered it."""
    _join(school, "pupil")
    assert orgs.sync_plan_from_owner("boss", "free") == school
    assert orgs.get_org(school)["plan"] == "free"
    # The member keeps their seat, their account and their history — the pool shrinks, the school
    # does not dissolve. Nobody is locked out of their own study by a billing failure, and the tier
    # comes straight back when payment resumes.
    assert orgs.membership("pupil") is not None
    assert orgs.quota_context("pupil")["pool_daily"] == plans.daily_tokens("free")


def test_an_upgrade_reaches_the_school(school):
    assert orgs.sync_plan_from_owner("boss", "institution_100") == school
    assert plans.tier(orgs.get_org(school)["plan"]).seats == 100


def test_syncing_a_plan_for_someone_who_owns_no_school_does_nothing(school):
    assert orgs.sync_plan_from_owner("stranger", "pro") is None
    assert orgs.get_org(school)["plan"] == "institution"


# ── Deletion, continued ──────────────────────────────────────────────────────
def test_purging_a_teacher_clears_the_rows_that_named_them(school):
    _join(school, "teach", orgs.TEACHER)
    orgs.accept_invite(orgs.create_invite(school, "teach", orgs.STUDENT), "pupil")
    db.purge_owner("teach")
    with db._LOCK:
        row = db.get_conn().execute(
            "SELECT invited_by FROM org_members WHERE org_id=? AND owner_id=?",
            (school, "pupil")).fetchone()
    assert row["invited_by"] == db.DELETED_OWNER


def test_closing_a_school_frees_its_members(school):
    _join(school, "pupil")
    orgs.close_org(school)
    assert orgs.get_org(school) is None
    assert orgs.membership("pupil") is None
    db.purge_owner("boss")           # the owner is deletable again — must not raise
