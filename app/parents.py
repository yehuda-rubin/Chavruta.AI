"""Parent links (spec 009 FR-007, FR-004, FR-023a). A parent may do exactly three things for a child:
correct the child's birth month/year, switch books off, and end the link. Nothing here reads the
child's conversations, and payment for a child is out of scope.

Authority lives HERE, not in `minors.correct_age`: that function only checks the actor kind and logs.
Every route that changes an age goes through `correct_child_age` (active parent link) or
`correct_age_as_operator` (the caller has already passed the operator gate), so the check cannot be
forgotten by a new caller (T082).
"""

from __future__ import annotations

from typing import Any

import app.db as db
import app.minors as minors

MAX_ACTIVE_PARENTS = 2


class NotLinked(Exception):
    """No active link between this parent and child. Routes turn it into 404."""


class AdultRequired(Exception):
    """The requesting parent is not an adult. Routes turn it into 403 adult_required."""


def is_adult(owner_id: str, *, legacy_adult: bool = False) -> bool:
    """An age record that says adult, or (no record) the legacy 18+ declaration from the JWT."""
    if owner_id == "local":
        return False
    row = minors.get_age(owner_id)
    if row is None:
        return legacy_adult
    return not minors._is_minor_row(row, minors._today())


def request_link(parent_id: str, child_id: str, *, legacy_adult: bool = False) -> bool:
    """Parent asks to link to a child. False when the child cannot be asked (unknown, not a minor,
    is the parent) so the route answers one indistinguishable 404. Raises AdultRequired first."""
    if not is_adult(parent_id, legacy_adult=legacy_adult):
        raise AdultRequired()
    if not child_id or child_id == parent_id or not minors.is_minor(child_id):
        return False
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        row = conn.execute("SELECT status FROM parent_links WHERE parent_owner_id=? AND child_owner_id=?",
                           (parent_id, child_id)).fetchone()
        if row is None:
            conn.execute("INSERT INTO parent_links (parent_owner_id, child_owner_id, status, created_at) "
                         "VALUES (?,?,'pending',?)", (parent_id, child_id, now))
        elif row["status"] in ("declined", "revoked"):
            conn.execute("UPDATE parent_links SET status='pending', created_at=?, decided_at=NULL "
                         "WHERE parent_owner_id=? AND child_owner_id=?", (now, parent_id, child_id))
        # pending / active: idempotent, nothing to change
    return True


def pending_for_child(child_id: str) -> list[dict[str, Any]]:
    """What the CHILD sees: who asked (account id) and the state. Active ones are listed too so the
    child can see and end them."""
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT parent_owner_id, status, created_at FROM parent_links "
            "WHERE child_owner_id=? AND status IN ('pending','active') ORDER BY created_at",
            (child_id,)).fetchall()
    return [dict(r) for r in rows]


def decide(child_id: str, parent_id: str, decision: str) -> str | None:
    """Child answers a PENDING request. Returns the new status, None if there is no pending request.
    Raises ValueError if approving would exceed MAX_ACTIVE_PARENTS."""
    if decision not in ("approve", "decline"):
        raise ValueError("decision must be 'approve' or 'decline'")
    with db._tx(db.get_conn()) as conn:
        row = conn.execute("SELECT status FROM parent_links WHERE parent_owner_id=? AND child_owner_id=?",
                           (parent_id, child_id)).fetchone()
        if row is None or row["status"] != "pending":
            return None
        if decision == "approve":
            active = conn.execute("SELECT COUNT(*) FROM parent_links WHERE child_owner_id=? "
                                  "AND status='active'", (child_id,)).fetchone()[0]
            if active >= MAX_ACTIVE_PARENTS:
                raise ValueError("a child may have at most two linked parents")
        new = "active" if decision == "approve" else "declined"
        conn.execute("UPDATE parent_links SET status=?, decided_at=? WHERE parent_owner_id=? "
                     "AND child_owner_id=?", (new, db._now(), parent_id, child_id))
    return new


def revoke(parent_id: str, child_id: str) -> bool:
    """End a link (either side). Only a pending or active link can be revoked."""
    with db._tx(db.get_conn()) as conn:
        return conn.execute(
            "UPDATE parent_links SET status='revoked', decided_at=? WHERE parent_owner_id=? "
            "AND child_owner_id=? AND status IN ('pending','active')",
            (db._now(), parent_id, child_id)).rowcount > 0


def is_active_parent(parent_id: str, child_id: str) -> bool:
    with db._LOCK:
        return db.get_conn().execute(
            "SELECT 1 FROM parent_links WHERE parent_owner_id=? AND child_owner_id=? AND status='active'",
            (parent_id, child_id)).fetchone() is not None


def children_of(parent_id: str) -> list[dict[str, Any]]:
    """The parent's linked children (account id and link state only; never any age or content)."""
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT child_owner_id, status FROM parent_links WHERE parent_owner_id=? "
            "AND status IN ('pending','active') ORDER BY created_at", (parent_id,)).fetchall()
    return [dict(r) for r in rows]


def require_active_parent(parent_id: str, child_id: str) -> None:
    if not is_active_parent(parent_id, child_id):
        raise NotLinked()


def correct_child_age(parent_id: str, child_id: str, birth_year: int, birth_month: int) -> dict[str, Any]:
    """The ONLY path by which a parent changes an age: verifies the active link, then logs as 'parent'."""
    require_active_parent(parent_id, child_id)
    return minors.correct_age(child_id, birth_year, birth_month, actor=parent_id, actor_kind="parent")


def correct_age_as_operator(operator_id: str, owner_id: str, birth_year: int, birth_month: int) -> dict[str, Any]:
    """The caller MUST have passed the operator gate (`_require_admin`); this only does the logged write."""
    return minors.correct_age(owner_id, birth_year, birth_month, actor=operator_id, actor_kind="operator")
