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
            try:
                run_due_purges()
            except Exception:               # noqa: BLE001 — keep the sweeper alive across errors
                _log.exception("deletion sweep failed")

    threading.Thread(target=_loop, name="deletion-sweeper", daemon=True).start()
    _log.info("account-deletion sweeper started (every %.0fs, grace %dd)", interval, grace_days())
