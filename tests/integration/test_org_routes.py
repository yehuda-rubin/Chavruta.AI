"""HTTP-level coverage of /orgs/* — spec 004.

Everything here was previously proven only at the module level, which is why the roster leak below
survived the first review: the role floors, the 404-never-403 convention and the JoinRefused mapping
all live in the ROUTE, and no test had ever issued a request to one.

Same TestClient fixture as test_admin_routes.py. Callers are distinguished by API key, since in
API-key mode `_owner_from_key` hashes the presented key into a stable owner id — which gives us
several distinct authenticated accounts without standing up Supabase.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.db as db
import app.orgs as orgs


def _owner_of(key: str) -> str:
    """The owner id app.security derives from an API key — so a test can seed rows for that account
    before it ever makes a request."""
    return "u_" + hashlib.sha256(key.encode()).hexdigest()[:16]


BOSS, TEACH, PUPIL, OUTSIDER, SECOND = ("k-boss", "k-teach", "k-pupil",
                                        "k-outsider", "k-second")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(api, "_assert_config_usable", lambda: None)
    fake_pipeline = SimpleNamespace(
        embedding=SimpleNamespace(embed_query=lambda q: SimpleNamespace(dense=[0.0], sparse={})))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake_pipeline)
    monkeypatch.delenv("CHAVRUTA_ADMIN_OWNERS", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.setenv("CHAVRUTA_API_KEYS", ",".join([BOSS, TEACH, PUPIL, OUTSIDER, SECOND]))
    with TestClient(api.app) as c:
        yield c


@pytest.fixture
def school(client):
    """A school with an owner-admin, a teacher and a student, built through the real join flow."""
    oid = orgs.create_org(_owner_of(BOSS), "בית ספר", "institution")
    for key, role in ((TEACH, orgs.TEACHER), (PUPIL, orgs.STUDENT)):
        code = orgs.create_invite(oid, _owner_of(BOSS), role)
        orgs.accept_invite(code, _owner_of(key))
    return oid


def h(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# ── The roster: a student must not receive a list of their classmates ─────────
# This is the finding that motivated the file. /orgs/panel was the one route with no role floor, and
# the masking inside it considered teacher-vs-admin only — so every student got every classmate's
# account id, role and cap. In a school that is a roster of minors handed to every other minor, and
# the button being hidden from students in the UI is decoration, not a control.
def test_a_student_sees_only_their_own_row(client, school):
    body = client.get("/orgs/panel", headers=h(PUPIL)).json()
    assert [m["owner_id"] for m in body["members"]] == [_owner_of(PUPIL)]
    assert body["topics"] == []


def test_a_teacher_sees_the_roster_but_not_each_members_figures(client, school):
    """The masking has to be tested against usage that actually exists — asserting 0 on a member who
    has never asked anything passes whether the mask is there or not."""
    db.bump_usage(orgs.member_meter_id(school, _owner_of(PUPIL)), 0, units=90_000)
    db.bump_usage(orgs.member_meter_id(school, _owner_of(TEACH)), 0, units=40_000)

    body = client.get("/orgs/panel", headers=h(TEACH)).json()
    assert {m["owner_id"] for m in body["members"]} == {
        _owner_of(BOSS), _owner_of(TEACH), _owner_of(PUPIL)}
    rows = {m["owner_id"]: m for m in body["members"]}
    assert rows[_owner_of(PUPIL)]["tokens_today"] == 0        # masked: a teacher is not an admin
    assert rows[_owner_of(TEACH)]["tokens_today"] == 40_000   # their own row is theirs to see

    admin_rows = {m["owner_id"]: m for m in
                  client.get("/orgs/panel", headers=h(BOSS)).json()["members"]}
    assert admin_rows[_owner_of(PUPIL)]["tokens_today"] == 90_000


def test_the_panel_never_returns_conversation_text(client, school):
    """Spec 004 decision 1. `sessions.first_q` is the verbatim opening question of every chat, and
    joining that table is the innocent-looking way this promise gets broken."""
    db.create_session("מה אומר רש\"י על בראשית א א", owner_id=_owner_of(PUPIL))
    r = client.get("/orgs/panel", headers=h(BOSS))
    assert r.status_code == 200
    # The panel really did render this member — so the absence below is a mask, not an empty body.
    assert _owner_of(PUPIL) in r.text
    assert "רש" not in r.text and "בראשית" not in r.text


# ── 404, never 403 ───────────────────────────────────────────────────────────
def test_a_non_member_gets_404_from_every_org_route(client, school):
    """403 would tell an outsider the org is real and that they merely lack a role."""
    assert client.get("/orgs/panel", headers=h(OUTSIDER)).status_code == 404
    assert client.get("/orgs/invites", headers=h(OUTSIDER)).status_code == 404
    assert client.post("/orgs/invite", json={"role": "student"}, headers=h(OUTSIDER)).status_code == 404
    assert client.post("/orgs/leave", headers=h(OUTSIDER)).status_code == 404
    assert client.post("/orgs/close", headers=h(OUTSIDER)).status_code == 404
    assert client.post("/orgs/members/remove", json={"owner_id": "x"},
                       headers=h(OUTSIDER)).status_code == 404


def test_a_student_gets_404_from_every_write_route(client, school):
    assert client.post("/orgs/invite", json={"role": "student"}, headers=h(PUPIL)).status_code == 404
    assert client.post("/orgs/members/remove", json={"owner_id": _owner_of(TEACH)},
                       headers=h(PUPIL)).status_code == 404
    assert client.post("/orgs/members/cap", json={"owner_id": _owner_of(TEACH), "daily_cap": 1},
                       headers=h(PUPIL)).status_code == 404


def test_a_teacher_cannot_remove_the_admin_over_http(client, school):
    r = client.post("/orgs/members/remove", json={"owner_id": _owner_of(BOSS)}, headers=h(TEACH))
    assert r.status_code == 404
    assert orgs.membership(_owner_of(BOSS)) is not None


# ── Invites ──────────────────────────────────────────────────────────────────
def test_the_route_will_not_mint_an_admin_code(client, school):
    """A multi-use admin code is a bearer credential handing over a school of minors."""
    assert client.post("/orgs/invite", json={"role": "admin"}, headers=h(BOSS)).status_code == 422


def test_a_teacher_code_admits_exactly_one_person(client, school):
    """Asserted by joining twice, not by reading the response back: the echo is the same local
    variable the route just computed and would stay 1 even if the stored row said 200."""
    code = client.post("/orgs/invite", json={"role": "teacher", "max_uses": 200},
                       headers=h(BOSS)).json()["code"]
    assert client.post("/orgs/join", json={"code": code}, headers=h(OUTSIDER)).status_code == 200
    assert client.post("/orgs/join", json={"code": code}, headers=h(SECOND)).status_code == 409
    assert orgs.membership(_owner_of(SECOND)) is None


def test_every_minted_code_expires(client, school):
    """The mechanism existed and the only caller never used it, so every code the product issued was
    eternal — and there was no way to revoke one either."""
    code = client.post("/orgs/invite", json={"role": "student"}, headers=h(BOSS)).json()["code"]
    with db._LOCK:
        row = db.get_conn().execute("SELECT expires_at FROM org_invites WHERE code=?",
                                    (code,)).fetchone()
    assert row["expires_at"]


def test_a_revoked_code_no_longer_admits(client, school):
    code = client.post("/orgs/invite", json={"role": "student"}, headers=h(BOSS)).json()["code"]
    assert client.post("/orgs/invite/revoke", json={"code": code}, headers=h(BOSS)).status_code == 200
    r = client.post("/orgs/join", json={"code": code}, headers=h(OUTSIDER))
    assert r.status_code == 409
    assert orgs.membership(_owner_of(OUTSIDER)) is None


def test_one_school_cannot_revoke_anothers_code(client, school):
    other = orgs.create_org("other-boss", "אחר", "institution")
    code = orgs.create_invite(other, "other-boss", orgs.STUDENT)
    assert client.post("/orgs/invite/revoke", json={"code": code}, headers=h(BOSS)).status_code == 404


def test_removing_a_member_kills_the_codes_they_minted(client, school):
    """Otherwise removal is advisory: a dismissed teacher walks back in with a code they minted while
    employed, and the admin has no route that stops it."""
    code = client.post("/orgs/invite", json={"role": "student"}, headers=h(TEACH)).json()["code"]
    client.post("/orgs/members/remove", json={"owner_id": _owner_of(TEACH)}, headers=h(BOSS))
    assert client.post("/orgs/join", json={"code": code}, headers=h(OUTSIDER)).status_code == 409


def test_a_bad_code_is_a_409_with_a_reason_for_the_joiner(client, school):
    r = client.post("/orgs/join", json={"code": "NOPENOPE12"}, headers=h(OUTSIDER))
    assert r.status_code == 409
    assert r.json()["detail"]


# ── Caps ─────────────────────────────────────────────────────────────────────
def test_a_cap_of_zero_is_the_tier_default_and_minus_one_blocks(client, school):
    """The two used to be one value, so an admin who set 0 to stop a disruptive student handed them
    the highest cap in the system instead."""
    client.post("/orgs/members/cap", json={"owner_id": _owner_of(PUPIL), "daily_cap": 0},
                headers=h(BOSS))
    assert orgs.quota_context(_owner_of(PUPIL))["member_cap"] == orgs.member_cap("institution")

    client.post("/orgs/members/cap", json={"owner_id": _owner_of(PUPIL), "daily_cap": -1},
                headers=h(BOSS))
    ctx = orgs.quota_context(_owner_of(PUPIL))
    assert ctx["member_cap"] == orgs.CAP_BLOCKED
    charge = db.bump_pooled(ctx["member_id"], ctx["pool_id"], member_cap=ctx["member_cap"],
                            pool_daily=0, pool_weekly=0, units=1)
    assert charge.allowed is False and charge.refused == "blocked"


def test_a_second_admin_cannot_throttle_the_paying_owner(client, school):
    """require_can_act_on permits equal ranks by design, and the owner has no route to read or reset
    their own cap — so without this an admin could cap the person paying at a single token."""
    orgs.set_member_cap(school, _owner_of(TEACH), 0)
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE org_members SET role='admin' WHERE org_id=? AND owner_id=?",
                     (school, _owner_of(TEACH)))
    r = client.post("/orgs/members/cap", json={"owner_id": _owner_of(BOSS), "daily_cap": 1},
                    headers=h(TEACH))
    assert r.status_code == 409


# ── Leaving and closing ──────────────────────────────────────────────────────
def test_leaving_ends_the_membership_frees_the_seat_and_is_recorded(client, school):
    before = orgs.seats_used(school)
    assert client.post("/orgs/leave", headers=h(PUPIL)).status_code == 200
    assert orgs.membership(_owner_of(PUPIL)) is None
    assert orgs.seats_used(school) == before - 1
    with db._LOCK:
        actions = [r["action"] for r in db.get_conn().execute(
            "SELECT action FROM org_access_log WHERE org_id=?", (school,)).fetchall()]
    assert "leave" in actions


def test_the_owner_closes_the_school_rather_than_leaving_it(client, school):
    assert client.post("/orgs/leave", headers=h(BOSS)).status_code == 409
    assert client.post("/orgs/close", headers=h(BOSS)).status_code == 200
    assert orgs.get_org(school) is None
    # Members revert to their own free accounts — the school bought quota, not anyone's work.
    assert orgs.membership(_owner_of(PUPIL)) is None
    assert orgs.quota_context(_owner_of(PUPIL)) is None


def test_a_teacher_cannot_close_the_school(client, school):
    assert client.post("/orgs/close", headers=h(TEACH)).status_code == 404
    assert orgs.get_org(school) is not None


def test_closing_the_school_unblocks_the_owners_account_deletion(client, school):
    """The closed loop this route exists to open: the owner could not leave, could not delete their
    account, and nothing anywhere deleted an org row."""
    assert client.post("/account/delete", headers=h(BOSS)).status_code == 409
    client.post("/orgs/close", headers=h(BOSS))
    assert client.post("/account/delete", headers=h(BOSS)).status_code == 200


# ── The operator's sample school ─────────────────────────────────────────────
def test_the_demo_panel_is_operator_only_and_enrols_nobody(client, monkeypatch):
    """Opening it used to convert the operator's real account into a school member for good: their
    questions started charging the demo pool, they could no longer buy or be granted anything, and
    their account became undeletable."""
    operator = _owner_of(BOSS)
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", operator)
    assert client.get("/orgs/panel?demo=true", headers=h(PUPIL)).status_code == 404

    body = client.get("/orgs/panel?demo=true", headers=h(BOSS)).json()
    assert body["is_demo"] is True
    assert orgs.membership(operator) is None
    assert orgs.quota_context(operator) is None
    assert db.owns_org(operator) is False
    assert all(m["owner_id"].startswith("demo-") for m in body["members"])


# ── A refused request must not keep the school's money ───────────────────────
def test_a_404_on_someone_elses_session_releases_the_reservation(client, school):
    """Quota is reserved BEFORE the ownership gate on purpose, so an over-quota account cannot probe
    session ids for free. That left the estimate charged to the school with the only object able to
    release it thrown away — no LLM call, no usage_events row, nothing to see. A member could spend
    their whole daily cap on 404s in seconds, and a class together could empty a school's week in a
    morning. It also happens by accident: a chat deleted in another tab is the same 404."""
    pool = orgs.pool_id(school)
    before = db.usage_today(pool)
    for _ in range(5):
        r = client.post("/sessions/not-my-session/query",
                        json={"question": "x", "intent": "compare"}, headers=h(PUPIL))
        assert r.status_code == 404
    assert db.usage_today(pool) == before


# ── An administrator's decisions outlive the membership row ──────────────────
def test_a_blocked_student_cannot_clear_the_block_by_rejoining(client, school):
    """The class code is multi-use and every student holds it. Deleting the row on removal took the
    stored cap with it, so leaving and rejoining returned a blocked student at the tier default —
    the largest per-member allowance in the system. In a school this is a safeguarding control."""
    code = client.post("/orgs/invite", json={"role": "student", "max_uses": 30},
                       headers=h(BOSS)).json()["code"]
    client.post("/orgs/members/cap", json={"owner_id": _owner_of(PUPIL), "daily_cap": -1},
                headers=h(BOSS))

    assert client.post("/orgs/leave", headers=h(PUPIL)).status_code == 200
    assert client.post("/orgs/join", json={"code": code}, headers=h(PUPIL)).status_code == 200
    assert orgs.quota_context(_owner_of(PUPIL))["member_cap"] == orgs.CAP_BLOCKED


def test_an_expelled_student_cannot_readmit_themselves(client, school):
    code = client.post("/orgs/invite", json={"role": "student", "max_uses": 30},
                       headers=h(BOSS)).json()["code"]
    client.post("/orgs/members/remove", json={"owner_id": _owner_of(PUPIL)}, headers=h(BOSS))

    assert client.post("/orgs/join", json={"code": code}, headers=h(PUPIL)).status_code == 409
    assert orgs.membership(_owner_of(PUPIL)) is None

    # ...but an administrator can let them back in — a removal that sticks needs a way back.
    assert client.post("/orgs/members/readmit", json={"owner_id": _owner_of(PUPIL)},
                       headers=h(BOSS)).status_code == 200
    assert client.post("/orgs/join", json={"code": code}, headers=h(PUPIL)).status_code == 200


def test_leaving_of_your_own_accord_lets_you_come_back(client, school):
    """A voluntary departure is not an expulsion; only the cap follows them."""
    code = client.post("/orgs/invite", json={"role": "student", "max_uses": 30},
                       headers=h(BOSS)).json()["code"]
    client.post("/orgs/leave", headers=h(PUPIL))
    assert client.post("/orgs/join", json={"code": code}, headers=h(PUPIL)).status_code == 200


# ── /me is the surface a member actually looks at ────────────────────────────
def test_me_reports_the_school_not_the_free_tier(client, school):
    db.bump_usage(orgs.member_meter_id(school, _owner_of(PUPIL)), 0, units=300_000)
    me = client.get("/me", headers=h(PUPIL)).json()
    assert me["plan"] == "institution"
    assert me["org_role"] == "student"
    # Against the member cap (1,200,000), not the free tier's 200,000 — which would have read 0%
    # remaining at a quarter of what the school actually bought them.
    assert me["day_left"] == 0.75
    # No BYOK allowance is offered: the request path refuses a member's key.
    assert me["byok_supported"] is False and me["byok_day_left"] is None


def test_a_blocked_member_sees_an_empty_gauge_not_an_unlimited_one(client, school):
    """_left returns None for any cap <= 0 and None means 'uncapped' — so the sentinel that means
    'may spend nothing' read as 'no ceiling', and the student saw a full bar and then a 429."""
    client.post("/orgs/members/cap", json={"owner_id": _owner_of(PUPIL), "daily_cap": -1},
                headers=h(BOSS))
    assert client.get("/me", headers=h(PUPIL)).json()["day_left"] == 0.0


# ── The panel shows the school's study, not a member's private past ──────────
def test_topics_exclude_what_a_member_did_before_they_joined(client, school):
    def _event(at, intent):
        db.record_usage_event(
            at=at, hour_local=9, dow=1, owner_id=_owner_of(PUPIL), plan="free", intent=intent,
            lang="he", prompt_tokens=1, completion_tokens=1, billed_tokens=1, llm_calls=1, ms=1,
            concurrent_at_start=0, grounded=1, no_source=0, citations=0, audience=None,
            grade_band=None, length=None, attachments=0, error=None)

    _event("2000-01-01T00:00:00", "halacha")     # a year of private study, long before the school
    _event(db._now(), "lesson")                  # ...and what they have done since joining
    topics = client.get("/orgs/panel", headers=h(BOSS)).json()["topics"]
    assert [t["intent"] for t in topics] == ["lesson"]


def test_a_teacher_cannot_reverse_an_admins_removal(client, school):
    """The safeguarding control introduced last round was reversible by exactly the people it
    constrains: readmit had a TEACHER floor and no rank check, so a colleague could undo a dismissal
    and mint the staff code that let the person back in."""
    client.post("/orgs/members/remove", json={"owner_id": _owner_of(PUPIL)}, headers=h(BOSS))
    assert client.post("/orgs/members/readmit", json={"owner_id": _owner_of(PUPIL)},
                       headers=h(TEACH)).status_code == 404

    code = client.post("/orgs/invite", json={"role": "student"}, headers=h(TEACH)).json()["code"]
    assert client.post("/orgs/join", json={"code": code}, headers=h(PUPIL)).status_code == 409


def test_readmit_cannot_be_pointed_at_a_higher_rank(client, school):
    """require_can_act_on, for the same reason remove has it: without it a teacher could readmit a
    removed ADMIN — someone they could never have removed in the first place."""
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE org_members SET role='admin', accepted_at=NULL, removed_at=? "
                     "WHERE org_id=? AND owner_id=?", (db._now(), school, _owner_of(PUPIL)))
    assert client.post("/orgs/members/readmit", json={"owner_id": _owner_of(PUPIL)},
                       headers=h(TEACH)).status_code == 404


def test_a_credit_paid_turn_that_404s_gets_the_credits_back(client, school, monkeypatch):
    """The release guard gave back reserved TOKENS but not credits, and a credit-admitted turn
    reserves none — so a stale session id destroyed real credits per attempt, five at a time for a
    lesson, with no generation and nothing to see."""
    import app.plans as plans
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "1")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    db.add_credits(_owner_of(OUTSIDER), 50)

    r = client.post("/sessions/no-such-session/query",
                    json={"question": "x", "intent": "lesson"}, headers=h(OUTSIDER))
    assert r.status_code == 404
    assert db.get_credits(_owner_of(OUTSIDER)) == 50
    assert plans.credit_cost("lesson") > 0     # the refund is not vacuous
