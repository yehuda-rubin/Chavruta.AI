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
    ok, pool_day, _ = db.bump_pooled("pupil", ctx["pool_id"], member_cap=ctx["member_cap"],
                                     pool_daily=ctx["pool_daily"], pool_weekly=ctx["pool_weekly"],
                                     units=1000)
    assert ok and pool_day == 1000
    assert db.usage_today("pupil") == 1000
    assert db.usage_today(ctx["pool_id"]) == 1000


def test_the_member_cap_bounds_one_persons_share_of_the_pool(school):
    """Without it a single student spends the school's entire day in an hour."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    ok, _, _ = db.bump_pooled("pupil", ctx["pool_id"], member_cap=500,
                              pool_daily=ctx["pool_daily"], pool_weekly=ctx["pool_weekly"],
                              units=501)
    assert ok is False
    assert db.usage_today("pupil") == 0        # refused means NOTHING moved, on either counter
    assert db.usage_today(ctx["pool_id"]) == 0


def test_the_pool_bounds_the_school_even_when_a_member_is_under_their_cap(school):
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    ok, _, _ = db.bump_pooled("pupil", ctx["pool_id"], member_cap=0, pool_daily=100,
                              pool_weekly=0, units=101)
    assert ok is False


def test_a_refused_pooled_charge_moves_neither_counter(school):
    """The reason this is one transaction rather than two bump_usage calls: charging the member and
    then discovering the pool is full would need an exact refund, and settle floors at zero."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    db.bump_pooled("pupil", ctx["pool_id"], member_cap=0, pool_daily=1000, pool_weekly=0, units=900)
    before_member = db.usage_today("pupil")
    before_pool = db.usage_today(ctx["pool_id"])
    ok, _, _ = db.bump_pooled("pupil", ctx["pool_id"], member_cap=0, pool_daily=1000,
                              pool_weekly=0, units=200)
    assert ok is False
    assert db.usage_today("pupil") == before_member
    assert db.usage_today(ctx["pool_id"]) == before_pool


def test_settlement_corrects_both_counters(school):
    """Reservations are deliberately generous, so settlement is normally a refund. If only the
    member's row were settled the school would be charged the ESTIMATE for every turn and its pool
    would empty several times faster than real use."""
    _join(school, "pupil")
    ctx = orgs.quota_context("pupil")
    db.bump_pooled("pupil", ctx["pool_id"], member_cap=0, pool_daily=0, pool_weekly=0, units=30_000)
    db.settle_pooled("pupil", ctx["pool_id"], reserved=30_000, actual=4_000)
    assert db.usage_today("pupil") == 4_000
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


def test_the_demo_org_holds_only_synthetic_members(fresh_db):
    orgs.ensure_demo_org()
    owners = {m["owner_id"] for m in orgs.members(orgs.DEMO_ORG_ID)}
    assert all(o.startswith("demo-") or o in ("local",) or "@" not in o for o in owners)


# ── The access log ────────────────────────────────────────────────────────────
def test_opening_the_panel_is_recorded(school):
    orgs.log_access(school, "boss", "view_panel", "pupil")
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT actor_owner_id, target_owner_id, action FROM org_access_log WHERE org_id=?",
            (school,)).fetchall()
    assert [tuple(r) for r in rows] == [("boss", "pupil", "view_panel")]
