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

import secrets
import string
from datetime import UTC, datetime, timedelta
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

# How long a join code lives. See create_invite.
INVITE_DAYS = 14

DEMO_ORG_ID = "org-demo"
# The sample school's owner. Synthetic on purpose — see ensure_demo_org.
DEMO_OWNER = "demo-admin"
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def rank(role: str) -> int:
    return _RANK.get((role or "").strip().lower(), -1)


def pool_id(org_id: str) -> str:
    """The synthetic owner id the org's shared counters live under.

    `usage_counters` is keyed (owner_id, day, meter), so an org needs no schema of its own — the
    existing primary key indexes this for free and `_counts` / week summing work unchanged.
    """
    return f"org:{org_id}"


def member_meter_id(org_id: str, owner_id: str) -> str:
    """The identity a member's SHARE of the pool is counted under — deliberately not their own.

    The first cut charged the member's share to their real owner id, which is the same row the free
    tier reads. Two things fell out of that, both invisible until someone complains:

    A student who spent 600,000 tokens of the school's pool on Sunday and left the school on Monday
    was locked out of the free product for the rest of the week — their personal weekly allowance is
    525,000, and the school's spending had already filled it. And in the other direction, a free user
    who had spent 200,000 that morning joined at noon and got 400,000 of a 600,000 cap, for a reason
    nobody could see.

    Separate identities keep the two allowances from ever touching. It also makes leaving a school a
    clean boundary: the org rows stay with the org, the personal row is untouched throughout.
    """
    return f"org:{org_id}:{owner_id}"


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


# What a stored `daily_cap` means. The column is NOT NULL DEFAULT 0 and the two sides of the
# boundary read 0 differently — quota_context treats it as "use the tier default", db.bump_pooled
# treats it as "no ceiling at all" — so an admin who set 0 meaning "stop this student" got the
# HIGHEST cap in the system. These constants make the three intentions distinct and nameable.
CAP_DEFAULT = 0      # stored: fall back to member_cap(plan)
CAP_BLOCKED = -1     # stored: this member may spend nothing


def member_cap(org_plan: str) -> int:
    """Default per-member daily ceiling for an org on `org_plan`.

    Derived from the tier rather than fixed, so retuning a tier's pool or seat count carries the
    per-member ceiling with it. All three institution tiers currently share one per-seat allowance,
    which is what made a constant look correct — nothing enforced that, and `daily_tokens` also
    honours per-tier env overrides, so a throttled pool would have kept a ceiling two members could
    drain it with.

    MEMBER_CAP_MULTIPLE times an even share is deliberate over-subscription: an even split is nothing
    to buy, and capacity moving to whoever is studying today is what pooling IS. Never below the free
    allowance — a school seat that buys less than no school seat would be absurd.
    """
    t = plans.tier(org_plan)
    share = plans.daily_tokens(org_plan) // max(1, t.seats)
    return max(plans.daily_tokens("free"), share * MEMBER_CAP_MULTIPLE)


def quota_context(owner_id: str) -> dict[str, Any] | None:
    """Everything a metered request needs, resolved ONCE and carried through settlement.

    Returning None means "not in an org" — the caller keeps its existing per-owner path untouched,
    which is what makes this safe to add to a live single-user product.
    """
    m = membership(owner_id)
    if not m:
        return None
    plan = plans.canonical(m["plan"])
    stored = int(m["daily_cap"])
    return {
        "org_id": m["org_id"],
        "org_name": m["name"],
        "role": m["role"],
        "plan": plan,
        "pool_id": pool_id(m["org_id"]),
        "member_id": member_meter_id(m["org_id"], owner_id),
        "member_cap": member_cap(plan) if stored == CAP_DEFAULT else stored,
        "pool_daily": plans.daily_tokens(plan),
        "pool_weekly": plans.weekly_tokens(plan),
        "weekly_lessons": plans.weekly_lessons(plan),
    }


def refuse_personal_purchase(owner_id: str, plan: str | None) -> str | None:
    """Why this account may not buy or be granted `plan` for itself — or None if it may.

    The rule is "would this change what the account can spend", not "is this person in a school".
    A member draws on the pool and nothing else (api.py::_reserve_tokens branches on quota_context
    before it reaches a personal plan, credits or BYOK), so a personal tier buys them nothing.

    But the ADMIN who pays for the school is a member of it too — the first cut of this guard tested
    membership alone and locked the paying customer out of buying, renewing or being granted the very
    subscription that funds the org. An institutional tier bought by the account that owns the org is
    the school's own subscription, and must go through.
    """
    m = membership(owner_id)
    if not m:
        return None
    if plan and plans.is_institutional(plan) and m["org_owner"] == owner_id:
        return None
    return ("member" if m["org_owner"] != owner_id else "owner")


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


def owned_org(owner_id: str) -> dict[str, Any] | None:
    """The organisation this account PAYS for, if any."""
    with db._LOCK:
        row = db.get_conn().execute("SELECT * FROM orgs WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


def sync_plan_from_owner(owner_id: str, plan: str) -> str | None:
    """Move the org's tier to match what its payer now holds. Returns the org id, or None.

    Without this the school's tier was written once at creation and never again: `quota_context`
    sizes the pool from `orgs.plan`, and no code path anywhere updated it. A school that stopped
    paying kept its full institution pool forever — the largest money leak in the feature, and
    invisible, because the panel reads the same stale row and cheerfully renders the whole pool. It
    also ran the other way: a school that UPGRADED could not be given what it had just bought.

    A non-institutional plan (the payer lapsed to free) degrades the pool rather than dissolving the
    school: members keep their accounts, their history and their seats, and the tier comes straight
    back when payment resumes. Nobody is locked out of their own study by a billing failure.
    """
    org = owned_org(owner_id)
    if not org:
        return None
    target = plans.canonical(plan)
    if target == plans.canonical(org["plan"]):
        return org["id"]
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE orgs SET plan=? WHERE id=?", (target, org["id"]))
    return org["id"]


def create_invite(org_id: str, created_by: str, role: str, *, max_uses: int = 1,
                  expires_at: str | None = None) -> str:
    """Mint a join code. It EXPIRES — the default is not "never".

    A code is a bearer credential: whoever holds the string takes a seat and spends the pool. The
    first cut left `expires_at` NULL on every code the product actually issued, so a class code
    screenshotted into a group chat stayed live forever, with no route to revoke it either. A
    fortnight is long enough to get a class signed up and short enough that a leak stops mattering.
    """
    if expires_at is None:
        expires_at = (datetime.now(UTC) + timedelta(days=INVITE_DAYS)).isoformat()
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
        # A checkout in flight counts as holding one. start_checkout writes a 'pending' subscription
        # but does NOT set accounts.plan, so the plan test above still reads 'free' for someone
        # sitting on the payment page — join here and the webhook then activates a real recurring
        # charge on an account whose spending goes to the pool instead. That is money taken monthly
        # for an entitlement the system deliberately ignores.
        sub = db.get_subscription(owner_id) or {}
        if sub.get("status") in ("pending", "active"):
            raise JoinRefused("this account has a subscription in progress; finish or cancel it first")
        # Credits are unspendable for a member (no fallback behind the pool), so joining with a
        # balance would quietly strand something they paid for.
        if db.get_credits(owner_id) > 0:
            raise JoinRefused("this account holds unused credits; spend them before joining")
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


def live_invites(org_id: str) -> list[dict[str, Any]]:
    """Codes that can still admit someone. An admin cannot revoke what they cannot see."""
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT code, role, max_uses, used_count, created_by, created_at, expires_at "
            "FROM org_invites WHERE org_id=? AND revoked_at IS NULL AND used_count < max_uses "
            "ORDER BY created_at DESC", (org_id,)).fetchall()
    return [dict(r) for r in rows]


def revoke_invite(org_id: str, code: str) -> bool:
    """Kill a code. Scoped by org_id so one school cannot revoke another's."""
    with db._tx(db.get_conn()) as conn:
        cur = conn.execute(
            "UPDATE org_invites SET revoked_at=? WHERE org_id=? AND code=? AND revoked_at IS NULL",
            (db._now(), org_id, code.strip().upper()))
    return cur.rowcount > 0


def remove_member(org_id: str, owner_id: str) -> bool:
    """Delete the row rather than nulling accepted_at — a revoked membership that still exists is
    one re-POST away from being live again.

    Their unspent codes die with the membership. Otherwise removal was advisory: a dismissed teacher
    walks back in with a code they minted while employed (every precondition in accept_invite passes
    again the moment they are removed), and the admin has no route to stop it. This is the only lever
    an admin has, so it has to actually hold.
    """
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE org_invites SET revoked_at=? WHERE org_id=? AND created_by=? "
                     "AND revoked_at IS NULL", (db._now(), org_id, owner_id))
        cur = conn.execute("DELETE FROM org_members WHERE org_id=? AND owner_id=?",
                           (org_id, owner_id))
    return cur.rowcount > 0


def close_org(org_id: str) -> None:
    """Wind up a school: memberships and codes go, the org row goes, the pool counters stay.

    The escape hatch the first cut had no equivalent of. An org owner could not delete their account
    (purge_owner refuses one), could not leave their own org, and there was no way to close it — so
    the paying administrator, the account most likely to receive an erasure request, was permanently
    undeletable through the product and support had only raw SQL. Members revert to their own free
    accounts untouched, which is what they had before joining.

    The pool's usage_counters rows are deliberately left: they are measurements under a synthetic id
    that names no person, and deleting them would rewrite history for aggregates already reported.
    """
    with db._tx(db.get_conn()) as conn:
        conn.execute("DELETE FROM org_invites WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM org_members WHERE org_id=?", (org_id,))
        conn.execute("DELETE FROM orgs WHERE id=?", (org_id,))


def set_member_cap(org_id: str, owner_id: str, daily_cap: int) -> bool:
    """Store a member's ceiling. See CAP_DEFAULT / CAP_BLOCKED for what the values mean."""
    value = CAP_BLOCKED if int(daily_cap) < 0 else int(daily_cap)
    with db._tx(db.get_conn()) as conn:
        cur = conn.execute("UPDATE org_members SET daily_cap=? WHERE org_id=? AND owner_id=?",
                           (value, org_id, owner_id))
    return cur.rowcount > 0


# ── the operator's sample school ──────────────────────────────────────────────
def ensure_demo_org() -> str:
    """A fixed synthetic organisation the operator can open to inspect the panel.

    NOT impersonation. It holds invented members and their own usage counters, so the operator sees
    what a school administrator sees WITHOUT opening a real school's records — which would be a back
    door to exactly the data spec 004 decided no one outside a school may read. Nothing here accepts
    an org id from the client; the id is this constant, so there is nothing to parameterise.

    Every id in here is synthetic, INCLUDING the owner. It used to be the operator's real account,
    on the reasoning that someone has to own it — and one look at the demo panel then quietly turned
    that account into a school member for good: its questions started charging the demo pool, it
    could no longer buy or be granted anything (the wallet guards test membership), and it became
    undeletable (purge_owner refuses an org owner). The operator's route into this panel is
    _is_admin, not membership — api.py::_org_for hardcodes the role for the demo branch — so nothing
    needed a real account here at all.
    """
    if get_org(DEMO_ORG_ID):
        return DEMO_ORG_ID
    create_org(DEMO_OWNER, "בית ספר לדוגמה", "institution", is_demo=True)
    now = db._now()
    demo = [("demo-teacher-1", TEACHER), ("demo-student-1", STUDENT),
            ("demo-student-2", STUDENT), ("demo-student-3", STUDENT)]
    with db._tx(db.get_conn()) as conn:
        for oid, role in demo:
            conn.execute(
                "INSERT OR IGNORE INTO org_members (org_id, owner_id, role, invited_at, accepted_at)"
                " VALUES (?,?,?,?,?)", (DEMO_ORG_ID, oid, role, now, now))
    return DEMO_ORG_ID
