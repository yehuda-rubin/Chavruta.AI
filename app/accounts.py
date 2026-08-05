"""Account deletion with a grace period.

Product rule: a user can delete their account, but it isn't wiped immediately — it's SCHEDULED for a
grace period (default 30 days) during which they can cancel. At the deadline a background sweeper
purges all their data. This mirrors "cancel at period end": an accidental or coerced click stays
recoverable, and (once billing lands) the schedule aligns to the paid period end — instead of
renewing, the account lapses and is purged unless the user cancels.

Single-instance/in-process by design, like the rest of the public-hosting layer: the sweeper is a
daemon thread in this process. Behind multiple replicas you'd move it to a shared scheduler — noted,
not built.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import UTC, datetime, timedelta

import app.db as db

_log = logging.getLogger("chavruta.accounts")


def grace_days() -> int:
    try:
        return max(0, int(os.environ.get("CHAVRUTA_ACCOUNT_DELETION_GRACE_DAYS", "30")))
    except ValueError:
        return 30


def schedule(owner_id: str) -> str:
    """Schedule deletion `grace_days` from now and return the ISO timestamp it will happen."""
    now = datetime.now(UTC)
    scheduled = now + timedelta(days=grace_days())
    db.schedule_deletion(owner_id, now.isoformat(), scheduled.isoformat())
    _log.info("account %s scheduled for deletion at %s", owner_id, scheduled.isoformat())
    return scheduled.isoformat()


def cancel(owner_id: str) -> None:
    db.cancel_deletion(owner_id)
    _log.info("account %s deletion cancelled", owner_id)


def scheduled_for(owner_id: str) -> str | None:
    """The pending deletion time for this owner, or None."""
    acct = db.get_account(owner_id)
    return acct.get("deletion_scheduled_for") if acct else None


# ── Blocklist ─────────────────────────────────────────────────────────────────
def active_ban(owner_id: str, now_iso: str | None = None) -> dict | None:
    """The block currently in force for this owner, or None. Permanent blocks (banned_until IS NULL)
    are always active; timed blocks are active only until their deadline. Returns
    {permanent, until, reason} so the caller can tell the user how long the block lasts."""
    row = db.get_ban(owner_id)
    if not row:
        return None
    until = row.get("banned_until")
    if until is None:
        return {"permanent": True, "until": None, "reason": row.get("reason") or ""}
    now_iso = now_iso or datetime.now(UTC).isoformat()
    if until > now_iso:
        return {"permanent": False, "until": until, "reason": row.get("reason") or ""}
    return None      # the timed block has expired — no longer in force


# ── Purge execution ───────────────────────────────────────────────────────────
def _delete_supabase_user(owner_id: str) -> None:
    """Best-effort: remove the auth user from Supabase so the email can no longer sign in. Requires a
    service-role key (admin scope); without it we only purge app data and the auth user lingers until
    removed out of band. `owner_id` is the Supabase user id (the JWT `sub`)."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not (key and url):
        return
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"{url}/auth/v1/admin/users/{owner_id}",
        method="DELETE",
        headers={"Authorization": f"Bearer {key}", "apikey": key},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        _log.info("supabase auth user %s deleted", owner_id)
    except urllib.error.HTTPError as exc:
        # 404 = already gone; anything else is logged but must not stop the data purge.
        if exc.code != 404:
            _log.warning("supabase admin delete failed for %s: HTTP %s", owner_id, exc.code)
    except Exception as exc:                # noqa: BLE001 — never let this abort the purge
        _log.warning("supabase admin delete errored for %s: %s", owner_id, exc.__class__.__name__)


def count_supabase_users() -> int | None:
    """Total signed-up accounts, from Supabase's own record — not app.db's `accounts` table, which
    only gets a row when a plan changes or credits are granted (db.set_plan/add_credits). A free user
    who never touched billing has NO row there at all, so that table drastically undercounts real
    signups; this is the number the admin dashboard actually wants for "how many accounts do we have".
    Returns None (caller falls back to the local count) if Supabase isn't configured."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not (key and url):
        return None
    import urllib.request

    total = 0
    page = 1
    try:
        while True:
            req = urllib.request.Request(
                f"{url}/auth/v1/admin/users?page={page}&per_page=1000",
                headers={"Authorization": f"Bearer {key}", "apikey": key},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                users = json.loads(resp.read()).get("users", [])
            total += len(users)
            if len(users) < 1000:
                return total
            page += 1
    except Exception:                        # noqa: BLE001 — best-effort, never breaks the dashboard
        _log.warning("supabase user count failed", exc_info=True)
        return None


def run_due_purges(now_iso: str | None = None) -> int:
    """Purge every account whose grace period has lapsed. Returns how many were purged."""
    now_iso = now_iso or datetime.now(UTC).isoformat()
    due = db.due_deletions(now_iso)
    for owner_id in due:
        try:
            _delete_supabase_user(owner_id)     # remove the login first (best-effort)
            db.purge_owner(owner_id)            # then irreversibly drop all their data
            _log.info("account %s purged", owner_id)
        except Exception:                       # noqa: BLE001 — one bad row must not stop the rest
            _log.exception("failed to purge account %s", owner_id)
    return len(due)


# ── Chat retention ────────────────────────────────────────────────────────────
def retention_days() -> int:
    """How long a conversation is kept after its last activity. 0 disables retention entirely
    (chats are kept forever), which is the old behaviour and not the default any more."""
    try:
        return max(0, int(os.environ.get("CHAVRUTA_CHAT_RETENTION_DAYS", "90")))
    except ValueError:
        return 90


def run_retention(now: datetime | None = None) -> int:
    """Delete chats untouched for longer than the retention window. Returns how many.

    Data minimisation: keeping every conversation forever is a growing store of personal content
    with no stated purpose past a point. The window is disclosed to users in the Terms and the
    Privacy Policy — deleting quietly would be worse than not deleting at all.
    """
    days = retention_days()
    if days <= 0:
        return 0
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat()
    n = db.delete_sessions_older_than(cutoff)
    if n:
        _log.info("retention: deleted %d chat(s) untouched since %s (%dd window)", n, cutoff[:10], days)
    return n


# ── Background sweeper ────────────────────────────────────────────────────────
_sweeper_started = False
_sweeper_lock = threading.Lock()


def _sweep_interval() -> float:
    try:
        return max(60.0, float(os.environ.get("CHAVRUTA_DELETION_SWEEP_INTERVAL_S", "3600")))
    except ValueError:
        return 3600.0


def start_sweeper() -> None:
    """Start the daemon that periodically purges due accounts. Idempotent — safe to call at every
    startup; only the first call spawns the thread."""
    global _sweeper_started
    with _sweeper_lock:
        if _sweeper_started:
            return
        _sweeper_started = True

    interval = _sweep_interval()

    def _loop() -> None:
        while True:
            time.sleep(interval)
            # Two independent jobs, each guarded on its own: a failure in one must not stop the
            # other from running for the rest of the process's life.
            try:
                run_due_purges()
            except Exception:               # noqa: BLE001 — keep the sweeper alive across errors
                _log.exception("deletion sweep failed")
            try:
                run_retention()
            except Exception:               # noqa: BLE001
                _log.exception("chat retention sweep failed")

    threading.Thread(target=_loop, name="deletion-sweeper", daemon=True).start()
    _log.info("account sweeper started (every %.0fs, grace %dd, chat retention %dd)",
              interval, grace_days(), retention_days())
