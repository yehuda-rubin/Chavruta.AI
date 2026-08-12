"""Organisations (schools) — membership, roles, the shared quota pool. Spec 004.

This module is the ONE place that answers "which pool does this person spend, and what may they do".
It lives here rather than in `app/plans.py` deliberately: that module is pure, stateless and
database-free, and every one of its functions maps a plan string to a number. A shared pool is not a
number, it is a counter identity — putting it there would make the pricing module depend on the
database and drag a DB fixture into tests that currently need none.

Three roles, strictly ordered. A member may only act on someone at or below their own rank, which is
a fourth check beyond "are you a member / does your role permit this / is the target in your org" —
without it a teacher can remove the org's admin and all three of those pass.
"""

from __future__ import annotations

import os
import secrets
import string
from typing import Any

import app.db as db
import app.plans as plans

ADMIN, TEACHER, STUDENT = "admin", "teacher", "student"
_RANK = {STUDENT: 0, TEACHER: 1, ADMIN: 2}

# A member's default share of the pool: deliberate OVER-subscription. An even split would give each
# person exactly the free allowance (the institution pool is sized at the free tier x its seat
# count), which is nothing to buy. Letting one member draw several shares is what pooling IS —
# capacity moves to whoever is studying today — and it is why the 80% warning matters rather than
# being decoration.
MEMBER_CAP_MULTIPLE = 3

DEMO_ORG_ID = "org-demo"
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def rank(role: str) -> int:
    return _RANK.get((role or "").strip().lower(), -1)


def pool_id(org_id: str) -> str:
    """The synthetic owner id the org's shared counters live under.

    `usage_counters` is keyed (owner_id, day, meter), so an org needs no schema of its own — the
    existing primary key indexes this for free and `_counts` / week summing work unchanged.
    """
    return f"org:{org_id}"


# ── membership ────────────────────────────────────────────────────────────────
def membership(owner_id: str) -> dict[str, Any] | None:
    """The caller's ACCEPTED membership, or None. A pending invitation grants nothing."""
    with db._LOCK:
        row = db.get_conn().execute(
            """SELECT m.org_id, m.owner_id, m.role, m.daily_cap, m.accepted_at,
                      o.name, o.plan, o.owner_id AS org_owner, o.is_demo
               FROM org_members m JOIN orgs o ON o.id = m.org_id
               WHERE m.owner_id = ? AND m.accepted_at IS NOT NULL""",
            (owner_id,)).fetchone()
    return dict(row) if row else None


def effective_plan(owner_id: str) -> str:
    """The tier whose allowance this account draws on — the org's for a member, else their own."""
    m = membership(owner_id)
    return plans.canonical(m["plan"]) if m else plans.canonical(db.get_plan(owner_id))


def member_cap(org_plan: str) -> int:
    """Default per-member daily ceiling for an org on `org_plan`."""
    return plans.daily_tokens("free") * MEMBER_CAP_MULTIPLE


def quota_context(owner_id: str) -> dict[str, Any] | None:
    """Everything a metered request needs, resolved ONCE and carried through settlement.

    Returning None means "not in an org" — the caller keeps its existing per-owner path untouched,
    which is what makes this safe to add to a live single-user product.
    """
    m = membership(owner_id)
    if not m:
        return None
    plan = plans.canonical(m["plan"])
    return {
        "org_id": m["org_id"],
        "org_name": m["name"],
        "role": m["role"],
        "plan": plan,
        "pool_id": pool_id(m["org_id"]),
        "member_cap": int(m["daily_cap"]) or member_cap(plan),
        "pool_daily": plans.daily_tokens(plan),
        "pool_weekly": plans.weekly_tokens(plan),
        "weekly_lessons": plans.weekly_lessons(plan),
    }


def members(org_id: str) -> list[dict[str, Any]]:
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT owner_id, role, daily_cap, invited_at, accepted_at FROM org_members "
            "WHERE org_id=? ORDER BY accepted_at IS NULL, role, invited_at", (org_id,)).fetchall()
    return [dict(r) for r in rows]


def seats_used(org_id: str) -> int:
    with db._LOCK:
        return db.get_conn().execute(
            "SELECT COUNT(*) FROM org_members WHERE org_id=? AND accepted_at IS NOT NULL",
            (org_id,)).fetchone()[0]


def get_org(org_id: str) -> dict[str, Any] | None:
    with db._LOCK:
        row = db.get_conn().execute("SELECT * FROM orgs WHERE id=?", (org_id,)).fetchone()
    return dict(row) if row else None


# ── the gate ──────────────────────────────────────────────────────────────────
class OrgAccessError(Exception):
    """Not a member, or not permitted. Callers translate this to 404 — never 403.

    404 follows the convention `_require_admin` already sets: a 403 tells an outsider that the org
    id is real and that they merely lack a role, which is exactly the fact worth withholding.
    """


def require_member(owner_id: str, org_id: str, min_role: str = STUDENT) -> dict[str, Any]:
    """Assert the caller is an accepted member of THIS org with at least `min_role`."""
    m = membership(owner_id)
    if not m or m["org_id"] != org_id:
        raise OrgAccessError("not a member of this organisation")
    if rank(m["role"]) < rank(min_role):
        raise OrgAccessError("insufficient role")
    return m


def require_can_act_on(actor: dict[str, Any], target_owner_id: str) -> dict[str, Any]:
    """Assert the actor outranks (or equals) the target, and that both are in the same org.

    The check the original plan was missing. Without it every stated condition still passes while a
    teacher removes the paying admin — leaving the org headless, or leaving the teacher as its
    highest-ranked member.
    """
    with db._LOCK:
        row = db.get_conn().execute(
            "SELECT owner_id, role FROM org_members WHERE org_id=? AND owner_id=?",
            (actor["org_id"], target_owner_id)).fetchone()
    if row is None:
        raise OrgAccessError("no such member in this organisation")
    if rank(row["role"]) > rank(actor["role"]):
        raise OrgAccessError("cannot act on a higher role")
    return dict(row)


def log_access(org_id: str, actor: str, action: str, target: str | None = None) -> None:
    with db._tx(db.get_conn()) as conn:
        conn.execute(
            "INSERT INTO org_access_log (org_id, actor_owner_id, target_owner_id, action, at) "
            "VALUES (?,?,?,?,?)", (org_id, actor, target, action, db._now()))


# ── lifecycle ─────────────────────────────────────────────────────────────────
def create_org(owner_id: str, name: str, plan: str, *, is_demo: bool = False) -> str:
    org_id = DEMO_ORG_ID if is_demo else f"org-{secrets.token_hex(8)}"
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        conn.execute("INSERT INTO orgs (id, name, owner_id, plan, created_at, is_demo) "
                     "VALUES (?,?,?,?,?,?)",
                     (org_id, name, owner_id, plans.canonical(plan), now, 1 if is_demo else 0))
        conn.execute("INSERT INTO org_members (org_id, owner_id, role, invited_at, accepted_at) "
                     "VALUES (?,?,?,?,?)", (org_id, owner_id, ADMIN, now, now))
    return org_id


def create_invite(org_id: str, created_by: str, role: str, *, max_uses: int = 1,
                  expires_at: str | None = None) -> str:
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))
    with db._tx(db.get_conn()) as conn:
        conn.execute(
            "INSERT INTO org_invites (code, org_id, role, max_uses, created_by, created_at, "
            "expires_at) VALUES (?,?,?,?,?,?,?)",
            (code, org_id, role, max(1, int(max_uses)), created_by, db._now(), expires_at))
    return code


class JoinRefused(Exception):
    """Why a join could not happen — the message is shown to the JOINER, never to the inviter."""


def accept_invite(code: str, owner_id: str) -> dict[str, Any]:
    """Redeem a join code. Eligibility and the seat check happen in ONE transaction.

    Concurrency matters here: 60 people accepting at once must not each read "there is room" and all
    insert. Same shape as `db.bump_usage`, and for the same reason.
    """
    now = db._now()
    conn = db.get_conn()
    with db._LOCK, db._tx(conn):
        inv = conn.execute("SELECT * FROM org_invites WHERE code=?", (code.strip().upper(),)).fetchone()
        if inv is None or inv["revoked_at"] or inv["used_count"] >= inv["max_uses"]:
            raise JoinRefused("invalid or spent join code")
        if inv["expires_at"] and inv["expires_at"] < now:
            raise JoinRefused("this join code has expired")

        # A member may not hold their own paid plan, may not own an org, and may not already belong
        # to one. Note the plan test is on the EFFECTIVE plan, not on subscriptions.status: a
        # coupon-granted plan is stored as 'canceled' with a future period end and would slip past.
        if plans.canonical(db.get_plan(owner_id)) != "free":
            raise JoinRefused("this account holds a paid plan; leave or let it lapse first")
        if conn.execute("SELECT 1 FROM orgs WHERE owner_id=?", (owner_id,)).fetchone():
            raise JoinRefused("this account owns an organisation")
        if conn.execute("SELECT 1 FROM org_members WHERE owner_id=? AND accepted_at IS NOT NULL",
                        (owner_id,)).fetchone():
            raise JoinRefused("this account already belongs to an organisation")

        org = conn.execute("SELECT * FROM orgs WHERE id=?", (inv["org_id"],)).fetchone()
        seats = plans.tier(org["plan"]).seats
        taken = conn.execute(
            "SELECT COUNT(*) FROM org_members WHERE org_id=? AND accepted_at IS NOT NULL",
            (org["id"],)).fetchone()[0]
        if taken >= seats:
            raise JoinRefused("this organisation has no seats left")

        conn.execute(
            "INSERT INTO org_members (org_id, owner_id, role, invited_by, invited_at, accepted_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(org_id, owner_id) DO UPDATE SET "
            "role=excluded.role, accepted_at=excluded.accepted_at",
            (org["id"], owner_id, inv["role"], inv["created_by"], now, now))
        conn.execute("UPDATE org_invites SET used_count = used_count + 1 WHERE code=?",
                     (inv["code"],))
    return {"org_id": org["id"], "name": org["name"], "role": inv["role"]}


def remove_member(org_id: str, owner_id: str) -> bool:
    """Delete the row rather than nulling accepted_at — a revoked membership that still exists is
    one re-POST away from being live again."""
    with db._tx(db.get_conn()) as conn:
        cur = conn.execute("DELETE FROM org_members WHERE org_id=? AND owner_id=?",
                           (org_id, owner_id))
    return cur.rowcount > 0


def set_member_cap(org_id: str, owner_id: str, daily_cap: int) -> bool:
    with db._tx(db.get_conn()) as conn:
        cur = conn.execute("UPDATE org_members SET daily_cap=? WHERE org_id=? AND owner_id=?",
                           (max(0, int(daily_cap)), org_id, owner_id))
    return cur.rowcount > 0


# ── the operator's sample school ──────────────────────────────────────────────
def ensure_demo_org() -> str:
    """A fixed synthetic organisation the operator can open to inspect the panel.

    NOT impersonation. It holds invented members and their own usage counters, so the operator sees
    what a school administrator sees WITHOUT opening a real school's records — which would be a back
    door to exactly the data spec 004 decided no one outside a school may read. Nothing here accepts
    an org id from the client; the id is this constant, so there is nothing to parameterise.
    """
    if get_org(DEMO_ORG_ID):
        return DEMO_ORG_ID
    operator = (os.environ.get("CHAVRUTA_ADMIN_OWNERS", "").split(",") or [""])[0].strip() or "local"
    create_org(operator, "בית ספר לדוגמה", "institution", is_demo=True)
    now = db._now()
    demo = [("demo-teacher-1", TEACHER), ("demo-student-1", STUDENT),
            ("demo-student-2", STUDENT), ("demo-student-3", STUDENT)]
    with db._tx(db.get_conn()) as conn:
        for oid, role in demo:
            conn.execute(
                "INSERT OR IGNORE INTO org_members (org_id, owner_id, role, invited_at, accepted_at)"
                " VALUES (?,?,?,?,?)", (DEMO_ORG_ID, oid, role, now, now))
    return DEMO_ORG_ID
