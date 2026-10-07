"""Development helpers — accounts the operator invites to test the product.

A helper is an ordinary account with three differences, and no others:

  1. a **basic-tier allowance** instead of free — applied as a FLOOR, so someone who already pays
     for more keeps what they pay for (`plan_floor` + `orgs.effective_plan`);
  2. access to whatever the operator has opened **for them specifically** — the same beta features
     an allowlist would grant, per person rather than per env var;
  3. notices the operator can send them inside the product.

CONSENT IS THE POINT, NOT PAPERWORK
-----------------------------------
`accepted_at` is NULL until the person agrees, and until then NOTHING applies — not the quota, not
the features, and a message can still be sent but arrives alongside the offer. Being enrolled
changes what an account can do and exposes it to code nobody has reviewed in front of users. An
operator who could enrol accounts silently from a text box could hand an unreleased feature to a
stranger who never asked. So it is an offer.

Revocation needs no consent, obviously — it only takes back what was given.

WHY OWNER IDS AND NOT EMAILS
----------------------------
The app database stores no email addresses at all; the only identifier that crosses from Supabase is
the owner_id (docs/USER_DATA.md). Asking the operator for an id is not a UX compromise — it is the
only key that exists here. The admin dashboard's top-users table shows them, which is where one is
copied from in practice.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import app.db as db
import app.plans as plans

_log = logging.getLogger("chavruta.devhelpers")

# The allowance a helper draws on. A floor, never a ceiling — see plan_floor.
HELPER_PLAN = "basic"

# Features an operator may open for a helper. Checked against this list rather than accepted as free
# text: a typo would create a grant that silently matches nothing, which looks exactly like the
# feature being broken.
FEATURES: tuple[str, ...] = ("sugya", "calendar", "sourcesheet")

FEATURE_LABELS_HE = {
    "sugya": "משחק הסוגיה",
    "calendar": "פרשת שבוע ודף יומי",
    "sourcesheet": "ניתוח דפי מקורות",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ── Enrolment ─────────────────────────────────────────────────────────────────
def invite(owner_id: str, *, by: str, note: str = "", features: list[str] | None = None) -> dict:
    """Offer helper status to an account. Idempotent: re-inviting someone who already has a pending
    or accepted row updates the note and features rather than resetting their consent.

    Re-inviting someone who DECLINED clears the decline — that is a deliberate second ask, made by a
    person who can see they were turned down, not an automatic re-prompt.
    """
    owner_id = (owner_id or "").strip()
    if not owner_id:
        raise ValueError("owner_id is required")
    if owner_id == by:
        # Nothing technical stops it; it is just always a mistake. The operator already has every
        # feature, and enrolling themselves would floor their own plan at basic in the admin views.
        raise ValueError("cannot enrol yourself as your own helper")
    feats = _clean_features(features)
    existing = get(owner_id)
    # Re-inviting someone whose status was REVOKED must ask again. Clearing `revoked_at` while
    # leaving `accepted_at` in place re-armed a consent that had already been ended: the row went
    # straight back to "accepted", the basic-tier floor returned, and any newly-ticked feature
    # applied — with no prompt, because the invitation panel only renders for status "invited". That
    # is exactly the door this module's docstring says cannot exist. An accepted row that was never
    # revoked keeps its consent (editing a note or a grant must not silently un-enrol someone).
    reask = bool(existing and existing.get("revoked_at"))
    with db._tx(db.get_conn()) as conn:
        if existing:
            conn.execute(
                "UPDATE dev_helpers SET note=?, features=?, revoked_at=NULL, declined_at=NULL"
                + (", accepted_at=NULL" if reask else "")
                + " WHERE owner_id=?",
                (note or existing.get("note") or "", json.dumps(feats), owner_id))
        else:
            conn.execute(
                "INSERT INTO dev_helpers (owner_id, added_at, added_by, note, features) "
                "VALUES (?,?,?,?,?)", (owner_id, _now(), by, note or "", json.dumps(feats)))
    _log.info("dev helper %s invited by %s (features=%s)", owner_id, by, feats)
    return get(owner_id) or {}


def accept(owner_id: str) -> bool:
    """The person says yes. Returns False if they were never invited, or the offer was withdrawn."""
    row = get(owner_id)
    if not row or row.get("revoked_at"):
        return False
    if row.get("accepted_at"):
        return True                     # already in; saying yes twice is not an error
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE dev_helpers SET accepted_at=?, declined_at=NULL WHERE owner_id=?",
                     (_now(), owner_id))
    _log.info("dev helper %s accepted", owner_id)
    return True


def decline(owner_id: str) -> bool:
    """The person says no.

    What survives is the MINIMUM that keeps the operator from asking again blindly: the account id,
    the fact of a refusal, and when. The operator's free-text note about them is **erased**, and so
    are any notices already sent — a person who refused should not be carrying our description of
    them around, and should not keep receiving messages.

    Keeping the row at all is a deliberate trade. Deleting it outright would mean the operator sees
    nothing and re-invites the same person indefinitely, which is worse for them than a two-column
    record that exists to prevent exactly that. It is disclosed in the privacy policy rather than
    justified here alone (section 1) — an earlier draft of that section claimed no record existed for
    someone who refused, which was simply untrue of this code.
    """
    row = get(owner_id)
    if not row:
        return False
    if row["declined_at"] or row["revoked_at"]:
        # Already stopped. Returning False here is what makes the route 404 on a repeat, and it is
        # deliberate rather than tidiness — see the note on _clear_period_usage about why anything
        # this path does must happen at most once.
        return False
    with db._tx(db.get_conn()) as conn:
        conn.execute(
            "UPDATE dev_helpers SET declined_at=?, accepted_at=NULL, note='', features='[]' "
            "WHERE owner_id=?", (_now(), owner_id))
        conn.execute("DELETE FROM helper_messages WHERE owner_id=?", (owner_id,))
    # NOTE: the period counters are deliberately NOT cleared here, unlike revoke(). This is the one
    # stop the SUBJECT initiates, and a reset the beneficiary can trigger is a reset they can farm.
    # Someone who chooses to stop after spending a helper's allowance keeps that spend on the meter
    # and waits for the period to roll over; they took the benefit, on their own timing.
    _log.info("dev helper %s declined", owner_id)
    return True


def revoke(owner_id: str) -> bool:
    """Withdraw helper status. Takes back only what was given — no consent needed for that."""
    row = get(owner_id)
    if not row or row["revoked_at"]:
        return False                    # never enrolled, or already off — nothing to take back
    was_active = row["active"]
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE dev_helpers SET revoked_at=? WHERE owner_id=?", (_now(), owner_id))
    if was_active:
        # Only for someone who actually HELD the raised allowance. Revoking an invitation that was
        # never accepted takes nothing away, so there is nothing to hand back and clearing would be
        # a plain gift of a free period.
        _clear_period_usage(owner_id)
    _log.info("dev helper %s revoked", owner_id)
    return True


def _clear_period_usage(owner_id: str) -> None:
    """Zero this account's CURRENT day and week counters when their allowance drops.

    Quota compares an accumulated counter against the CURRENT limit, so lowering the limit applies
    retroactively to spend already made under the higher one. A helper who used their basic-tier
    allowance during a day of testing and was then revoked found every further request refused —
    until midnight for the daily cap and until Sunday for the weekly one — with a message telling
    them to buy a subscription. Being thanked for helping by being locked out is not a defensible
    outcome, and the spend was legitimate when it happened.

    The counters are cleared rather than clamped because clamping to the lower cap leaves them at
    the ceiling, which is the same lockout. It hands back at most one period's free allowance to
    someone the operator invited personally; that is the cheaper mistake by a wide margin.

    **Two rules govern every caller, and both are load-bearing.** This function is a free period of
    generation on the operator's own API key, so:

      1. Only an OPERATOR action may reach it — revoke and remove, both behind the admin gate. It
         was briefly wired to decline() too, which the person themself calls, and that made
         `POST /helper/decline` a repeatable self-service quota reset: spend the cap, decline, spend
         it again. The row is never deleted on a decline, so the button stayed live forever, and
         nothing rate-limits it. Anyone ever invited — including someone already revoked — had
         unmetered generation for as long as they cared to keep pressing.
      2. It may fire only for a row that was ACTIVE, and only once. An invitation that was never
         accepted raised no limit, so there is nothing to give back.
    """
    try:
        with db._tx(db.get_conn()) as conn:
            # The whole CURRENT WEEK, not just today: the weekly cap is summed across the week's
            # daily rows (db._counts -> week_days), so clearing only today would leave the weekly
            # total above a lowered weekly limit and the lockout would simply last until Sunday.
            days = db.week_days(db.today_il())
            conn.execute(
                f"DELETE FROM usage_counters WHERE owner_id=? "        # noqa: S608 — placeholders
                f"AND day IN ({','.join('?' * len(days))})", (owner_id, *days))
    except Exception:                   # noqa: BLE001 — never let this fail an operator action
        _log.exception("failed to clear period usage for %s", owner_id)


def remove(owner_id: str) -> bool:
    """Delete the row entirely, and the notices sent to them with it — for taking someone off the
    list rather than merely switching them off."""
    was_active = (get(owner_id) or {}).get("active", False)
    with db._tx(db.get_conn()) as conn:
        cur = conn.execute("DELETE FROM dev_helpers WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM helper_messages WHERE owner_id=?", (owner_id,))
    if was_active:
        _clear_period_usage(owner_id)   # takes the allowance away exactly as revoke does
    return cur.rowcount > 0


# ── Reading ───────────────────────────────────────────────────────────────────
def _row(r) -> dict[str, Any]:
    d = dict(r)
    try:
        d["features"] = json.loads(d.get("features") or "[]")
    except (TypeError, ValueError):
        d["features"] = []
    d["active"] = bool(d.get("accepted_at")) and not d.get("revoked_at")
    d["status"] = ("revoked" if d.get("revoked_at") else
                   "accepted" if d.get("accepted_at") else
                   "declined" if d.get("declined_at") else "invited")
    return d


def get(owner_id: str) -> dict[str, Any] | None:
    with db._LOCK:
        r = db.get_conn().execute(
            "SELECT * FROM dev_helpers WHERE owner_id=?", (owner_id,)).fetchone()
    return _row(r) if r else None


def listing() -> list[dict[str, Any]]:
    """Everyone ever enrolled, newest first, with their unread-notice count — the operator wants to
    see at a glance who has actually read what was sent."""
    with db._LOCK:
        rows = db.get_conn().execute(
            """SELECT h.*, (SELECT COUNT(*) FROM helper_messages m
                            WHERE m.owner_id = h.owner_id AND m.read_at IS NULL) AS unread
               FROM dev_helpers h ORDER BY h.added_at DESC""").fetchall()
    return [_row(r) for r in rows]


def is_active(owner_id: str) -> bool:
    row = get(owner_id)
    return bool(row and row["active"])


def plan_floor(owner_id: str) -> str | None:
    """The tier an active helper is lifted TO, or None. A floor: `orgs.effective_plan` applies it
    only when it beats what the account already has, so a helper who also pays for pro stays on pro
    — being asked to test must never cost someone allowance they bought."""
    return HELPER_PLAN if is_active(owner_id) else None


def has_feature(owner_id: str, feature: str) -> bool:
    row = get(owner_id)
    return bool(row and row["active"] and feature in row["features"])


def _clean_features(features: list[str] | None) -> list[str]:
    """Keep only known ids, deduplicated, in FEATURES order so the list is stable in the UI."""
    given = {f.strip() for f in (features or []) if f and f.strip()}
    return [f for f in FEATURES if f in given]


def set_features(owner_id: str, features: list[str]) -> list[str]:
    feats = _clean_features(features)
    with db._tx(db.get_conn()) as conn:
        conn.execute("UPDATE dev_helpers SET features=? WHERE owner_id=?",
                     (json.dumps(feats), owner_id))
    return feats


# ── Notices ───────────────────────────────────────────────────────────────────
MAX_BODY = 2000


def send(owner_ids: list[str], body: str, *, by: str) -> int:
    """Send one notice to one or more helpers. Returns how many were actually written.

    Only to people on the list — including those who have not answered yet, because "would you help
    me test?" is exactly the kind of thing worth being able to say alongside the offer. Never to an
    arbitrary account: this is not a channel for messaging users at large, and letting it become one
    would put an unreviewed broadcast tool one text box away.

    **Never to someone who declined or was revoked.** Filtering on `revoked_at` alone let a refusal
    be ignored: the person pressed "no thank you" and kept receiving notices, with a read receipt
    recorded for each. That is the one case where continuing to write to them is not a grey area.
    """
    body = (body or "").strip()[:MAX_BODY]
    if not body:
        raise ValueError("empty message")
    known = {h["owner_id"] for h in listing()
             if not h.get("revoked_at") and not h.get("declined_at")}
    targets = [o for o in dict.fromkeys(owner_ids) if o in known]
    if not targets:
        return 0
    now = _now()
    with db._tx(db.get_conn()) as conn:
        conn.executemany(
            "INSERT INTO helper_messages (at, sent_by, owner_id, body) VALUES (?,?,?,?)",
            [(now, by, o, body) for o in targets])
    _log.info("notice sent to %d helper(s) by %s", len(targets), by)
    return len(targets)


def inbox(owner_id: str, *, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT id, at, body, read_at FROM helper_messages WHERE owner_id=?"
    if unread_only:
        sql += " AND read_at IS NULL"
    with db._LOCK:
        rows = db.get_conn().execute(sql + " ORDER BY id DESC LIMIT ?",
                                     (owner_id, max(1, int(limit)))).fetchall()
    return [dict(r) for r in rows]


def mark_read(owner_id: str, message_id: int) -> bool:
    """Scoped to the owner, always: an id from a client is not proof of who it belongs to."""
    with db._tx(db.get_conn()) as conn:
        cur = conn.execute(
            "UPDATE helper_messages SET read_at=? WHERE id=? AND owner_id=? AND read_at IS NULL",
            (_now(), int(message_id), owner_id))
    return cur.rowcount > 0


def status_for(owner_id: str) -> dict[str, Any]:
    """Everything the app needs to decide what to show this account — one call, because the client
    asks on every load and three round trips for a feature most accounts do not have is waste."""
    row = get(owner_id)
    if not row or row.get("revoked_at"):
        return {"status": "none", "features": [], "unread": []}
    return {
        "status": row["status"],
        "note": row.get("note") or "",
        "features": row["features"] if row["active"] else [],
        "plan": HELPER_PLAN if row["active"] else "",
        "unread": inbox(owner_id, unread_only=True, limit=20),
    }


def label(feature: str) -> str:
    return FEATURE_LABELS_HE.get(feature, feature)


def rank_at_least(current: str, floor: str) -> str:
    """The better of the two tiers. Uses plans.rank rather than a local ordering — there is already
    one source of truth for which tier beats which, and a second would drift."""
    return floor if plans.rank(floor) > plans.rank(current) else current
