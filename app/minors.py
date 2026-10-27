"""Age records and the minor/adult decision (spec 009-school-minors).

The age record is the ONLY source of truth for "is this account a minor". It lives in SQLite, not in
Supabase `user_metadata`: that field is writable by the account holder with the public anon key, and
two of the gates that depend on it (`db.reviewable_questions` is pure SQL; the retention sweeper is a
background thread) cannot read a JWT at all — a metadata flag would make both fail OPEN.

Rules that the rest of the code relies on:
  * No record means ADULT. Accounts that declared 18+ before this feature existed (Supabase
    `age_confirmed_18`) have no record and must stay exactly as they were; defaulting missing data to
    "minor" would silently empty every review/training query. `require_auth` is what demands a record
    from NEW accounts (`age_required`).
  * A record is written once by its owner (`set_age_once`). After that only a linked parent or the
    operator may change it (`correct_age`), and every change is appended to `age_record_log`.
  * `adult_from` is the first day of the month AFTER the 18th-birthday month. Only month and year are
    stored, so this is the earliest date on which the person is certainly 18: conservative in the
    direction that protects the child. The minimum-age check (12) uses the same rule.
  * `messages.minor_until` (and the same column on saved lessons and source sheets) is set at INSERT time
    from the author's record and never updated, so a message written as a minor stays excluded from
    review and training, and still expires, after its author turns 18.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import app.db as db
from chavruta.corpus.audience import ADULT, AudienceScope
from chavruta.retrieval.denylist import resolve_denylist

MIN_AGE = 12
ADULT_AGE = 18
DEFAULT_MINOR_RETENTION_DAYS = 60


class AgeError(ValueError):
    """Base for every refusal here. `code` is the API error code the route returns."""
    code = "invalid_age"


class InvalidBirth(AgeError):
    code = "invalid_birth"


class UnderMinimumAge(AgeError):
    code = "under_minimum_age"


class AgeAlreadySet(AgeError):
    code = "age_already_set"


class AgeNotSet(AgeError):
    code = "age_required"


class NotAdultYet(AgeError):
    code = "not_adult_yet"


def minor_retention_days() -> int:
    """How long anything written as a minor is kept. Never 0 or negative: that would mean "delete at
    once", which an env typo must not be able to do (nor "keep forever", which is the other misreading)."""
    try:
        return max(1, int(os.environ.get("CHAVRUTA_MINOR_RETENTION_DAYS", str(DEFAULT_MINOR_RETENTION_DAYS))))
    except ValueError:
        return DEFAULT_MINOR_RETENTION_DAYS


def _today(today: date | None = None) -> date:
    return today or datetime.now(UTC).date()


def _month_after(year: int, month: int, years: int) -> date:
    """First day of the month after the `years`-th anniversary month of (year, month)."""
    y, m = year + years, month + 1
    if m == 13:
        y, m = y + 1, 1
    return date(y, m, 1)


def adult_from(birth_year: int, birth_month: int) -> str:
    """ISO date from which the person is treated as an adult (see the module docstring)."""
    return _month_after(birth_year, birth_month, ADULT_AGE).isoformat()


def _validate(birth_year: Any, birth_month: Any, today: date) -> tuple[int, int]:
    if isinstance(birth_year, bool) or isinstance(birth_month, bool):
        raise InvalidBirth("birth year and month must be integers")
    try:
        y, m = int(birth_year), int(birth_month)
    except (TypeError, ValueError):
        raise InvalidBirth("birth year and month must be integers") from None
    if not (1 <= m <= 12) or not (1900 <= y <= today.year):
        raise InvalidBirth("birth year or month out of range")
    if _month_after(y, m, MIN_AGE) > today:
        raise UnderMinimumAge(f"the minimum age is {MIN_AGE}")
    return y, m


def get_age(owner_id: str) -> dict[str, Any] | None:
    """The stored record, or None (a legacy adult, a local user, or someone who has not declared yet)."""
    with db._LOCK:
        row = db.get_conn().execute(
            "SELECT owner_id, birth_year, birth_month, adult_from, adult_terms_accepted_at, "
            "created_at, updated_at FROM age_records WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


def _is_minor_row(row: dict[str, Any] | None, today: date) -> bool:
    return row is not None and today.isoformat() < row["adult_from"]


def is_minor(owner_id: str, today: date | None = None) -> bool:
    """True only when a record exists and the person is not yet an adult. No record ⇒ False."""
    if owner_id == "local":
        return False
    return _is_minor_row(get_age(owner_id), _today(today))


def minor_owner_ids(today: date | None = None) -> set[str]:
    """Every owner with a record that still makes them a minor — for bulk filters (marketing, review)."""
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT owner_id FROM age_records WHERE adult_from > ?", (_today(today).isoformat(),)).fetchall()
    return {r["owner_id"] for r in rows}


def set_age_once(owner_id: str, birth_year: int, birth_month: int,
                 today: date | None = None) -> dict[str, Any]:
    """Create the owner's age record. Refuses under-12s, and refuses to overwrite: the first answer is
    the answer, so a child cannot retry until a form lets them through.

    A person who is an adult at declaration already accepted the Terms at signup (the route is only
    reachable behind `consent_required`), so `adult_terms_accepted_at` is stamped now. A minor's stays
    NULL and is what `adult_terms_required` later keys on."""
    if owner_id == "local":
        raise AgeError("the shared local user has no age record")
    t = _today(today)
    y, m = _validate(birth_year, birth_month, t)
    af = adult_from(y, m)
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        if conn.execute("SELECT 1 FROM age_records WHERE owner_id=?", (owner_id,)).fetchone():
            raise AgeAlreadySet("an age record already exists")
        conn.execute(
            "INSERT INTO age_records (owner_id, birth_year, birth_month, adult_from, "
            "adult_terms_accepted_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (owner_id, y, m, af, now if t.isoformat() >= af else None, now, now))
        conn.execute(
            "INSERT INTO age_record_log (owner_id, actor, actor_kind, old_birth_year, old_birth_month, "
            "new_birth_year, new_birth_month, at) VALUES (?,?,?,?,?,?,?,?)",
            (owner_id, owner_id, "self", None, None, y, m, now))
    return get_age(owner_id)  # type: ignore[return-value]


def correct_age(owner_id: str, birth_year: int, birth_month: int, *, actor: str,
                actor_kind: str, today: date | None = None) -> dict[str, Any]:
    """Change an existing record. Only a parent or the operator may; the CALLER is responsible for
    having verified that (an active `parent_links` row, or the admin gate) — this function only
    enforces that the actor kind is one of those two and that the change is logged. Routes must call
    `app.parents.correct_child_age` / `correct_age_as_operator`, never this directly (T082)."""
    if actor_kind not in ("parent", "operator"):
        raise ValueError("actor_kind must be 'parent' or 'operator'")
    y, m = _validate(birth_year, birth_month, _today(today))
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        old = conn.execute(
            "SELECT birth_year, birth_month FROM age_records WHERE owner_id=?", (owner_id,)).fetchone()
        if old is None:
            raise AgeNotSet("no age record to correct")
        conn.execute(
            "UPDATE age_records SET birth_year=?, birth_month=?, adult_from=?, updated_at=? WHERE owner_id=?",
            (y, m, adult_from(y, m), now, owner_id))
        conn.execute(
            "INSERT INTO age_record_log (owner_id, actor, actor_kind, old_birth_year, old_birth_month, "
            "new_birth_year, new_birth_month, at) VALUES (?,?,?,?,?,?,?,?)",
            (owner_id, actor, actor_kind, old["birth_year"], old["birth_month"], y, m, now))
    return get_age(owner_id)  # type: ignore[return-value]


def adult_terms_required(owner_id: str, today: date | None = None) -> bool:
    """A record exists, its owner is now an adult, and they have not accepted the adult Terms yet.
    False for no record (legacy adults accepted at signup) and for the local user."""
    if owner_id == "local":
        return False
    row = get_age(owner_id)
    return (row is not None and not _is_minor_row(row, _today(today))
            and not row["adult_terms_accepted_at"])


def accept_adult_terms(owner_id: str, today: date | None = None) -> None:
    row = get_age(owner_id)
    if row is None:
        raise AgeNotSet("no age record")
    if _is_minor_row(row, _today(today)):
        raise NotAdultYet("not an adult yet")
    with db._tx(db.get_conn()) as conn:
        conn.execute(
            "UPDATE age_records SET adult_terms_accepted_at=COALESCE(adult_terms_accepted_at, ?), "
            "updated_at=? WHERE owner_id=?", (db._now(), db._now(), owner_id))


def minor_until_for(conn: Any, owner_id: str, now: datetime | None = None) -> str | None:
    """The deletion date to stamp on something this owner is writing RIGHT NOW, or None for an adult.
    Takes the caller's connection so it reads inside the same transaction as the insert."""
    if not owner_id or owner_id == "local":
        return None
    row = conn.execute(
        "SELECT adult_from FROM age_records WHERE owner_id=?", (owner_id,)).fetchone()
    if row is None:
        return None
    now = now or datetime.now(UTC)
    if now.date().isoformat() >= row["adult_from"]:
        return None
    return (now + timedelta(days=minor_retention_days())).isoformat()


def status(owner_id: str, *, legacy_adult: bool = False, supabase: bool = False,
           today: date | None = None) -> dict[str, bool]:
    """The `/me` fields. `legacy_adult` is the JWT's `age_confirmed_18`; `supabase` says whether the
    deployment demands a declared age at all (open local / API-key mode never does)."""
    if owner_id == "local":
        return {"is_minor": False, "age_required": False, "adult_terms_required": False}
    row = get_age(owner_id)
    t = _today(today)
    minor = _is_minor_row(row, t)
    return {
        "is_minor": minor,
        "age_required": supabase and row is None and not legacy_adult,
        "adult_terms_required": row is not None and not minor and not row["adult_terms_accepted_at"],
    }


def parental_consent_ok(owner_id: str) -> bool:
    """May this person send messages as far as PARENTAL CONSENT goes (spec 009 T090)? True for an adult,
    the local user, and a minor who has any of: an accepted school membership (the school holds parental
    consent), an active `parent_links` row (a parent with an account), or an approved, unrevoked emailed
    consent. Everything else is a minor with no consent."""
    if owner_id == "local" or not is_minor(owner_id):
        return True
    import app.orgs as orgs

    if orgs.membership(owner_id):
        return True
    with db._LOCK:
        conn = db.get_conn()
        return bool(
            conn.execute("SELECT 1 FROM parent_links WHERE child_owner_id=? AND status='active' LIMIT 1",
                         (owner_id,)).fetchone()
            or conn.execute("SELECT 1 FROM parental_consents WHERE child_owner_id=? AND status='approved' "
                            "LIMIT 1", (owner_id,)).fetchone())


# ── Route gates (called from security.require_auth) ────────────────────────────
# Which requests a gate applies to is a property of ROUTES, so it lives in one table here rather than
# as a Depends() on a dozen handlers (the three referral aliases alone are nine decorators): a route
# added later under these prefixes is covered, one added elsewhere is not, and the list is greppable.
_MESSAGE_SEND = re.compile(
    r"^/(query(/stream|/async)?"
    r"|sessions(/stream|/async)?"
    r"|sessions/[^/]+/(query|stream|query/async))$")
_PURCHASE = re.compile(
    r"^/(billing/checkout|coupons/redeem|(api/)?referrals?/(status|settings|generate|claim))$")


def gate_error(owner_id: str, method: str, path: str) -> dict[str, str] | None:
    """The 403 body for this request, or None. `minor_no_purchase` for billing/coupon/referral routes
    while a minor; `adult_terms_required` for message-sending routes once adult but before accepting."""
    if owner_id == "local":
        return None
    is_send = method == "POST" and _MESSAGE_SEND.match(path) is not None
    is_buy = _PURCHASE.match(path) is not None
    if not (is_send or is_buy):
        return None
    st = status(owner_id)
    if is_buy and st["is_minor"]:
        return {"error": "minor_no_purchase",
                "message": "Purchases, coupons and referrals are not available for accounts under 18."}
    if is_send and st["adult_terms_required"]:
        return {"error": "adult_terms_required",
                "message": "Please accept the adult Terms of Use to continue."}
    return None


# ── What a minor may be shown (spec 009 FR-020..FR-024, T053) ──────────────────────────────────────
def effective_denylist_rows(owner_id: str) -> list[tuple[str, str]]:
    """(kind, value) rows that apply to this person: their school's, plus their parents'.

    A parent's rows are stored against the CHILD (`scope_kind='parent'`, `scope_id=child`) and only count
    while at least one parent link is `active`: revoking the link must lift the restriction, not leave the
    rows behind. The school's count while the account is an accepted member. A restriction is only ever
    added by either side, never removed by the other, which is why this is a plain union."""
    import app.orgs as orgs

    m = orgs.membership(owner_id)
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT kind, value FROM content_denylist WHERE "
            "(scope_kind='org' AND scope_id=?) OR "
            "(scope_kind='parent' AND scope_id=? AND EXISTS "
            "(SELECT 1 FROM parent_links WHERE child_owner_id=? AND status='active'))",
            (m["org_id"] if m else "", owner_id, owner_id)).fetchall()
    return [(r["kind"], r["value"]) for r in rows]


def audience_scope(owner_id: str, today: date | None = None) -> AudienceScope:
    """The scope to run this person's request under. Adults, legacy accounts and the local user get the
    default scope (not a minor, nothing denied), which every consumer treats as "behave as before"."""
    if not owner_id or not is_minor(owner_id, today):
        return ADULT
    return AudienceScope(minor=True, deny=resolve_denylist(effective_denylist_rows(owner_id)))
