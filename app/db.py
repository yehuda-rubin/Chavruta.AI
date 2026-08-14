"""Chavruta.AI — SQLite persistence for chat sessions and messages."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Collection, Mapping
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from app import moderation

# Location of the chat-history store. Configurable via CHAVRUTA_DB_PATH so the
# container can point it at a mounted volume (persists all conversations across
# restarts); defaults to the repo root for local dev.
DB_PATH = Path(
    os.environ.get("CHAVRUTA_DB_PATH", Path(__file__).resolve().parent.parent / "chavruta.db")
)

_telemetry_log = logging.getLogger("chavruta.telemetry")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# A single SQLite connection is shared across FastAPI's threadpool workers
# (check_same_thread=False). Serialize ALL access through one lock so concurrent
# requests can't interleave transactions — otherwise one request's rollback() can
# undo another's uncommitted INSERT, causing spurious FOREIGN KEY failures.
_LOCK = threading.RLock()


@contextmanager
def _tx(conn: sqlite3.Connection):
    with _LOCK:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
        _migrate(_conn)
    return _conn


# Bump when the schema changes; _migrate() applies forward steps idempotently on
# existing persisted databases (tracked via SQLite's PRAGMA user_version).
#
# WHY A PLAIN COUNTER AND NOT 30.1 / 31
# -------------------------------------
# `PRAGMA user_version` is a 32-bit signed INTEGER. It cannot hold "30.1" — that is SQLite's
# constraint, not a style choice. The nearest thing would be encoding major*100 + minor (3000, 3010,
# 3100), which preserves ordering and is what a project with real major/minor schema eras should do.
# This one does not have them: every migration here is additive and idempotent (CREATE TABLE IF NOT
# EXISTS, or ALTER TABLE ADD COLUMN behind a PRAGMA table_info check), there is no downgrade path,
# and nothing branches on the number beyond "have the steps up to here run yet". A two-part version
# would encode a distinction the code never reads.
#
# What was actually missing is below: WHAT each bump added. When a migration goes wrong the question
# is never "was that major or minor", it is "what changed at 28". Reconstructed from git history.
#
#   31  messages.source_note                                      2026-08-14
#   30  dev_helpers, helper_messages                              2026-08-13
#   29  guard_findings                                            2026-08-13
#   28  org_members.removed_at (a re-joinable block)              2026-08-13
#   27  orgs, org_members, org_invites, org_access_log            2026-08-12
#   26  usage_events.concurrent_at_start                          2026-08-07
#   25  sessions.excluded_from_review                             2026-08-06
#   24  calendar_cache                                            2026-08-05
#   23  sessions.title, sessions.pinned_at                        2026-08-04
#   22  message_reports; accounts/usage analytics columns         2026-08-02
#   21  coupon_redemptions ↔ subscriptions coupon columns         2026-07-29
#   20  billing_ledger.txn_uid (refunds are issued against it)    2026-07-27
#   19  usage_counters meter column (tokens vs lessons)           2026-07-26
#   18  billing_ledger                                            2026-07-26
#   17  coupons                                                   2026-07-26
#   ≤16 subscriptions, bans, deletion scheduling, per-owner scoping — see git log -G'^SCHEMA_VERSION'
SCHEMA_VERSION = 31


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _migrate(conn: sqlite3.Connection) -> None:
    # "Brand new" means the schema does not exist yet — NOT "zero rows". Keying the
    # one-time demo seed on row count would resurrect the demo chats every time the
    # user deletes all their conversations and restarts the process; keying it on a
    # freshly-created schema makes deletions survive restarts (true persistence).
    fresh_db = not _table_exists(conn, "sessions")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           TEXT PRIMARY KEY,
            first_q      TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            updated_at   TEXT,
            mode         TEXT,         -- the chat's locked mode (intent chosen on the first turn)
            owner_id     TEXT NOT NULL DEFAULT 'local',  -- who this belongs to; 'local' = single-user
            title        TEXT,         -- user-given name; NULL = display first_q instead (unrenamed)
            pinned_at    TEXT,         -- when pinned, for ordering pinned chats most-recent-first;
                                       -- NULL = not pinned. Capped at 3 pinned per owner (set_session_pinned).
            excluded_from_review INTEGER NOT NULL DEFAULT 0
                                       -- opt-out of the operator's post-10.8.2026 review/improvement
                                       -- use (privacy policy section 12); 0 = included (default)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role          TEXT NOT NULL CHECK(role IN ('user','assistant')),
            text          TEXT NOT NULL,
            intent        TEXT,
            citations     TEXT,
            caveats       TEXT,
            grounded      INTEGER,
            files         TEXT,
            source_note   TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, id);

        -- Flagged messages, for operator review — the defamation/quality safety net
        -- (docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding C): grounding reduces but does not
        -- eliminate the risk of a mischaracterizing answer about a real named person. Two sources:
        -- source='user' — a user flagged their own conversation's message (the original mechanism).
        -- source='auto' — app/moderation.py's keyword scan flagged it on save (see save_message);
        --   `reason` holds the matched category (e.g. 'defamation_risk'), never the message text
        --   itself — a reviewer looks up the real content via message_id, same as a user report.
        -- reviewed_at is NULL until an operator marks it handled (scripts/moderation_report.py), so
        -- the same backlog isn't re-reported forever.
        CREATE TABLE IF NOT EXISTS message_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id  INTEGER NOT NULL,
            owner_id    TEXT NOT NULL,
            reason      TEXT,
            source      TEXT NOT NULL DEFAULT 'user',
            reviewed_at TEXT,
            created_at  TEXT NOT NULL
        );

        -- Free-text feedback/suggestions — a general channel, not tied to any specific message
        -- (unlike message_reports, which is always about one flagged answer). reviewed_at is NULL
        -- until an operator marks it handled, same backlog convention as message_reports.
        CREATE TABLE IF NOT EXISTS feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id    TEXT NOT NULL,
            text        TEXT NOT NULL,
            reviewed_at TEXT,
            created_at  TEXT NOT NULL
        );

        -- ── Organisations (schools) — spec 004 ──────────────────────────────────────────────
        -- A school buys one subscription and its members study on that pool instead of their own.
        --
        -- `owner_id` is who PAYS (it keys `subscriptions`, whose owner_id is a PRIMARY KEY and whose
        -- PayPlus token belongs to the person who checked out). It is deliberately NOT the source of
        -- truth for permissions — org_members.role is. Two sources of truth for "is admin" is where
        -- privilege escalation lives, so: role decides what you may do, owner_id decides who is
        -- billed, and they are written together.
        --
        -- No FK on owner_id: `accounts` only gets a row when a plan changes or credits are granted,
        -- so most real people have none, exactly as sessions/usage_events already assume.
        CREATE TABLE IF NOT EXISTS orgs (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            owner_id    TEXT NOT NULL,       -- who pays; see above
            plan        TEXT NOT NULL,       -- institution | institution_50 | institution_100
            created_at  TEXT NOT NULL,
            is_demo     INTEGER NOT NULL DEFAULT 0
                        -- the operator's read-only sample school (spec 004 decision 6): a fixed
                        -- synthetic org so the panel can be inspected without impersonating anyone.
        );

        -- Membership. A row exists from the moment of invitation; `accepted_at IS NULL` grants
        -- NOTHING. The unique index below is the constraint that makes quota resolution decidable:
        -- with two accepted memberships there is no answer to "which pool does this turn charge".
        CREATE TABLE IF NOT EXISTS org_members (
            org_id      TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            owner_id    TEXT NOT NULL,
            role        TEXT NOT NULL,       -- admin | teacher | student
            daily_cap   INTEGER NOT NULL DEFAULT 0,   -- 0 = the tier default; see orgs.member_cap
            invited_by  TEXT,
            invited_at  TEXT NOT NULL,
            accepted_at TEXT,
            -- Set when an ADMIN removed this person; NULL if they left of their own accord. The row
            -- survives either way (accepted_at goes NULL, freeing the seat) so the decision outlives
            -- the membership: deleting it made both of an administrator's controls self-reversible.
            -- A blocked student could leave and rejoin with the class code every classmate holds,
            -- and come back at the tier default — the largest per-member allowance in the system.
            removed_at  TEXT,
            PRIMARY KEY (org_id, owner_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_org_members_one_accepted
            ON org_members(owner_id) WHERE accepted_at IS NOT NULL;

        -- Join codes. Membership is never conferred by an admin typing someone's account id: that
        -- would let any org owner attach any account in the system, and a typo attach a stranger.
        -- The code is how an invitation is ADDRESSED; the member performs the act of joining.
        -- It also avoids turning the invite endpoint into an account-enumeration oracle.
        CREATE TABLE IF NOT EXISTS org_invites (
            code        TEXT PRIMARY KEY,
            org_id      TEXT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            role        TEXT NOT NULL,
            max_uses    INTEGER NOT NULL DEFAULT 1,
            used_count  INTEGER NOT NULL DEFAULT 0,
            expires_at  TEXT,
            created_by  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            revoked_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_org_invites_org ON org_invites(org_id);

        -- Who looked at whom. Written even though v1 shows no conversation text: an audit trail
        -- added after the fact cannot describe what happened before it existed.
        CREATE TABLE IF NOT EXISTS org_access_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id          TEXT NOT NULL,
            actor_owner_id  TEXT NOT NULL,
            target_owner_id TEXT,
            action          TEXT NOT NULL,
            at              TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_org_access_log_org ON org_access_log(org_id, id DESC);

        -- 'My Shiurim' library: generated lessons persisted on their own (not just inside a chat),
        -- so teachers can browse, reopen and reuse them. CREATE IF NOT EXISTS is idempotent.
        CREATE TABLE IF NOT EXISTS saved_lessons (
            id          TEXT PRIMARY KEY,
            topic       TEXT NOT NULL,
            audience    TEXT,
            grade_band  TEXT,
            length      TEXT,
            lang        TEXT,
            files       TEXT NOT NULL,   -- JSON [{name,title,content}]
            citations   TEXT,            -- JSON
            created_at  TEXT NOT NULL,
            owner_id    TEXT NOT NULL DEFAULT 'local',  -- who this belongs to; 'local' = single-user
            -- Where this lesson also lives as a chat turn. The Word documents are stored twice — in
            -- `files` here and in messages.files — so without this link, deleting from the library
            -- left a full copy in the chat and "delete" did not delete. Written after the message is
            -- persisted (its id only exists then); NULL on rows predating the link.
            message_id  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_saved_lessons_time ON saved_lessons(created_at DESC);

        -- Per-owner daily usage, one row per (owner, UTC day, meter). Two meters, two independent
        -- pools (see app/plans.py):
        --   'tokens' — normalized conversation tokens (prompt + 3x completion), capped per day AND
        --              per week. A message count would charge a pasted daf like a one-line question.
        --   'lesson' — a COUNT of lessons, capped per week only. Discrete, planned around, and
        --              deliberately unaffected by the token pool running out.
        -- Weekly figures are SUMMED from these daily rows — one source of truth, no second table
        -- that could disagree. Persisted so a restart can't hand back a spent allowance.
        CREATE TABLE IF NOT EXISTS usage_counters (
            owner_id  TEXT NOT NULL,
            day       TEXT NOT NULL,          -- UTC date, YYYY-MM-DD
            meter     TEXT NOT NULL DEFAULT 'tokens',
            count     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (owner_id, day, meter)
        );

        -- Account lifecycle — currently just scheduled deletion. A user can request deletion; it's
        -- carried out after a grace period (during which they can cancel), so an accidental or
        -- coerced click is recoverable. NULL scheduled_for = no pending deletion.
        CREATE TABLE IF NOT EXISTS accounts (
            owner_id               TEXT PRIMARY KEY,
            deletion_requested_at  TEXT,      -- ISO ts when the user asked to delete (NULL = not asked)
            deletion_scheduled_for TEXT,      -- ISO ts when the purge runs (NULL = nothing scheduled)
            plan                   TEXT NOT NULL DEFAULT 'free',  -- see app/plans.py; flipped by billing
            -- Prepaid generations, spent only once the day's plan quota is used up. Granted by coupon
            -- today; a credit pack purchase would write the same column.
            credits                INTEGER NOT NULL DEFAULT 0
        );

        -- Coupons — operator-issued codes granting either a time-boxed plan or a pile of credits.
        -- Created by scripts/manage_coupons.py (no admin HTTP surface); redeemed by users at
        -- POST /coupons/redeem. `redeemed_count` is bumped in the same transaction as the redemption
        -- row, so a single-use code cannot be spent twice by concurrent requests.
        CREATE TABLE IF NOT EXISTS coupons (
            code            TEXT PRIMARY KEY,     -- stored normalised (upper, no dashes)
            kind            TEXT NOT NULL,        -- 'plan' | 'credits'
            plan            TEXT,                 -- kind='plan': which tier (app/plans.py)
            days            INTEGER,              -- kind='plan': how long the tier lasts
            credits         INTEGER,              -- kind='credits': how many generations
            max_redemptions INTEGER NOT NULL DEFAULT 1,   -- 0 = unlimited
            redeemed_count  INTEGER NOT NULL DEFAULT 0,
            expires_at      TEXT,                 -- ISO ts the CODE stops working; NULL = never
            active          INTEGER NOT NULL DEFAULT 1,   -- 0 = revoked by the operator
            note            TEXT,                 -- why it was issued (campaign, person, event)
            created_at      TEXT NOT NULL
        );

        -- Usage telemetry — one row per generation, for understanding how the product is actually
        -- used and what it costs: which modes people reach for, when they work, how much a real
        -- answer consumes, how often retrieval comes back empty.
        --
        -- What it deliberately does NOT hold: the question, the answer, the sources, or any file the
        -- user attached. Those already live in `messages` under the user's control; copying them
        -- into an analytics table would create a second store of personal content with a different
        -- lifetime and no way for anyone to see or delete it. Everything here is a measurement.
        --
        -- owner_id is kept so per-account usage can be understood and abuse traced, and is NULLed by
        -- purge_owner rather than deleted — the aggregate survives, the person does not.
        CREATE TABLE IF NOT EXISTS usage_events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            at             TEXT NOT NULL,      -- ISO ts (UTC)
            hour_local     INTEGER,            -- 0-23 in Israel time: "when do teachers prepare?"
            dow            INTEGER,            -- 0=Sunday .. 6=Saturday
            owner_id       TEXT,               -- NULLed on account purge
            plan           TEXT,
            intent         TEXT,               -- qa | explain | compare | halacha | chavruta | lesson
            lang           TEXT,
            prompt_tokens     INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            billed_tokens     INTEGER NOT NULL DEFAULT 0,   -- normalized (prompt + 3x completion)
            llm_calls      INTEGER NOT NULL DEFAULT 0,      -- >1 means the agentic loop ran
            ms             INTEGER NOT NULL DEFAULT 0,      -- wall time, to find what feels slow
            grounded       INTEGER,            -- 1/0 — the quality signal that matters most
            no_source      INTEGER,            -- 1 = answered honestly with nothing found
            citations      INTEGER NOT NULL DEFAULT 0,
            audience       TEXT,               -- lesson: yeshiva | school
            grade_band     TEXT,               -- lesson: a-c | d-f | g-i | j-l
            length         TEXT,               -- lesson: short | medium | long
            attachments    INTEGER NOT NULL DEFAULT 0,
            error          TEXT,               -- exception class when the request failed
            concurrent_at_start INTEGER         -- generations in flight (this one included) at start
        );
        CREATE INDEX IF NOT EXISTS idx_usage_events_at ON usage_events(at DESC);
        CREATE INDEX IF NOT EXISTS idx_usage_events_owner ON usage_events(owner_id);

        -- What the watching guards caught (src/chavruta/generation/guards.py). These checks add
        -- nothing a user sees; this table is the only place their findings survive, and it is what
        -- the admin panel reads. Deliberately has NO owner_id and NO session_id: a finding records
        -- how well the SYSTEM wrote, never who asked. That is also why it needs no handling in
        -- purge_owner — there is nothing here belonging to a person to delete. `detail` is JSON
        -- whose shape depends on `kind`, because the three guards have nothing in common to
        -- normalise into columns and inventing shared ones would only produce empty fields.
        CREATE TABLE IF NOT EXISTS guard_findings (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            at     TEXT NOT NULL,        -- ISO ts (UTC)
            kind   TEXT NOT NULL,        -- misattribution | deontic | calendar
            intent TEXT,                 -- qa | explain | lesson | halacha | chavruta …
            detail TEXT NOT NULL         -- JSON
        );
        CREATE INDEX IF NOT EXISTS idx_guard_findings_at ON guard_findings(at DESC);

        -- Development helpers: people the operator invites to test the product with a basic-tier
        -- allowance and early access to whatever has been opened for them. See app/devhelpers.py.
        --
        -- `accepted_at` is NULL until the person says yes, and NOTHING applies before then. Being
        -- made a helper changes someone's quota and exposes them to unreleased features, so it is
        -- an offer and not an assignment — an operator who could quietly enrol accounts from a text
        -- box would be able to hand strangers a feature nobody has reviewed.
        CREATE TABLE IF NOT EXISTS dev_helpers (
            owner_id    TEXT PRIMARY KEY,
            added_at    TEXT NOT NULL,
            added_by    TEXT NOT NULL,
            note        TEXT,                 -- the operator's own label, e.g. "David — lessons"
            features    TEXT NOT NULL DEFAULT '[]',   -- JSON list of feature ids
            accepted_at TEXT,                 -- NULL ⇒ invited, nothing granted yet
            declined_at TEXT,                 -- they said no; kept so the offer is not re-sent blind
            revoked_at  TEXT
        );

        -- Operator → helper notices, fanned out at send time (one row per recipient) rather than
        -- stored once with a recipient list: read state is per person, and a shared row would need
        -- a second table to track it.
        CREATE TABLE IF NOT EXISTS helper_messages (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            at       TEXT NOT NULL,
            sent_by  TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            body     TEXT NOT NULL,
            read_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_helper_messages_owner
            ON helper_messages(owner_id, read_at);

        -- Accounting ledger. Deliberately has NO owner_id and is NEVER purged: tax law requires
        -- keeping records of what was charged for ~7 years, while a user may ask to be forgotten
        -- long before that. Storing the money without storing the person satisfies both — a row
        -- says a charge happened, for how much, under which invoice, and nothing about who.
        -- `provider_ref` is the processor's own handle, which is how a dispute is traced back
        -- through them if it ever has to be.
        CREATE TABLE IF NOT EXISTS billing_ledger (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            charged_at    TEXT NOT NULL,      -- ISO ts of the charge
            amount        REAL NOT NULL,
            currency      TEXT NOT NULL DEFAULT 'ILS',
            plan          TEXT,               -- tier sold
            cycle         TEXT,               -- monthly | annual
            provider      TEXT,               -- e.g. 'payplus'
            provider_ref  TEXT,               -- the processor's subscription/charge handle
            invoice_ref   TEXT,               -- the accounting document's id at the invoicing service
            note          TEXT,
            txn_uid       TEXT                -- the processor's handle for THIS payment (refunds
                                              -- are issued against it, not against provider_ref)
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_time ON billing_ledger(charged_at DESC);

        -- One row per (code, owner): the uniqueness that stops the same user redeeming a
        -- multi-use code repeatedly.
        CREATE TABLE IF NOT EXISTS coupon_redemptions (
            code        TEXT NOT NULL,
            owner_id    TEXT NOT NULL,
            redeemed_at TEXT NOT NULL,
            granted     TEXT,                     -- human-readable summary of what was given
            PRIMARY KEY (code, owner_id)
        );

        -- Blocklist — an account can be blocked for a bounded window (hours / days / months) or for
        -- good (banned_until IS NULL = permanent). Enforced at the auth gate: a blocked owner is 403'd
        -- on every route except viewing/managing their own account. Admin-managed (scripts/manage_bans.py).
        CREATE TABLE IF NOT EXISTS account_bans (
            owner_id     TEXT PRIMARY KEY,
            banned_at    TEXT NOT NULL,        -- ISO ts the block was applied
            banned_until TEXT,                 -- ISO ts the block lifts; NULL = permanent
            reason       TEXT
        );

        -- Sefaria's /api/calendars is called at most once per cache bucket (once a Hebrew day for
        -- Daf Yomi, once a week for Parshat HaShavua) rather than once per request. date_key is the
        -- bucket's identity (today's ISO date for daf_yomi; the week's ISO date for parsha) — not a
        -- freshness timestamp, so a lookup is an exact match, not a "still fresh?" comparison.
        CREATE TABLE IF NOT EXISTS calendar_cache (
            kind        TEXT NOT NULL,   -- 'parsha' | 'daf_yomi'
            date_key    TEXT NOT NULL,
            payload     TEXT NOT NULL,   -- JSON-serialized ParshaInfo/DafYomiInfo
            resolved_at TEXT NOT NULL,
            PRIMARY KEY (kind, date_key)
        );

        -- Subscription state (billing). Provider-agnostic: `provider` names the processor (e.g.
        -- 'payplus') and `provider_ref` holds its handle for this subscriber (a saved card token /
        -- subscription id). The billing webhook writes status + period end here and flips accounts.plan.
        -- current_period_end is the "renew or lapse" moment cancellation and deletion align to.
        CREATE TABLE IF NOT EXISTS subscriptions (
            owner_id             TEXT PRIMARY KEY,
            provider             TEXT,
            provider_ref         TEXT,
            status               TEXT NOT NULL DEFAULT 'none',   -- none|pending|active|past_due|canceled
            current_period_end   TEXT,                           -- ISO ts the paid period ends
            cancel_at_period_end INTEGER NOT NULL DEFAULT 0,     -- 1 = don't renew, lapse at period end
            updated_at           TEXT,
            -- What was bought, recorded at CHECKOUT: the provider callback reports a successful
            -- charge and for whom, not which tier or period it was for. Without these an annual
            -- purchase would come back and be granted a single month.
            plan                 TEXT,                           -- tier id (app/plans.py)
            cycle                TEXT NOT NULL DEFAULT 'monthly', -- monthly | annual
            -- A coupon redeemed while a real PayPlus subscription is active never touches the
            -- fields above (that would detach the account from its recurring charge) — instead it
            -- lands here: either an ILS credit to rebate off the next charge(s), or a time-boxed
            -- upgrade that must revert to the plan the account actually pays for.
            coupon_discount_ils  REAL NOT NULL DEFAULT 0,  -- ILS credit balance rebated off the next PayPlus charge
            coupon_revert_plan   TEXT,                     -- plan to revert to when a coupon boost expires
            coupon_revert_at     TEXT                      -- UTC ISO timestamp when the boost must be reverted
        );
    """)

    # Forward migrations for databases created by an older schema version.
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "updated_at" not in cols:
            # ALTER ADD COLUMN can't use a non-constant default, so backfill in a
            # second statement: existing sessions sort by their creation time until
            # they next receive a message.
            conn.execute("ALTER TABLE sessions ADD COLUMN updated_at TEXT")
            conn.execute("UPDATE sessions SET updated_at = created_at WHERE updated_at IS NULL")

    if version < 3:
        # LESSON mode persists its 3 generated files with the assistant message so they
        # survive reloads / switching back to the session (they were in-memory only before).
        mcols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "files" not in mcols:
            conn.execute("ALTER TABLE messages ADD COLUMN files TEXT")

    if version < 5:
        # A chat's mode (lesson/explain/qa/shut/chavruta) is now locked to whatever was chosen on the
        # first turn — subsequent turns stay in that mode. Older sessions get NULL and fall back to the
        # per-request intent (unchanged behaviour) until they next start a fresh chat.
        scols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "mode" not in scols:
            conn.execute("ALTER TABLE sessions ADD COLUMN mode TEXT")

    if version < 6:
        # Per-owner scoping (public hosting): sessions/lessons belong to an owner so one user can't
        # read another's. Existing rows predate multi-user and become 'local' — the single-user
        # default, so local/offline behaviour is unchanged.
        for tbl in ("sessions", "saved_lessons"):
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})")}
            if "owner_id" not in cols:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local'")
                conn.execute(f"UPDATE {tbl} SET owner_id='local' WHERE owner_id IS NULL")

    if version < 9:
        # Subscription plan on the account (billing groundwork). Pre-existing accounts rows (created
        # in v8 without the column) get 'free' — the default, so behaviour is unchanged.
        acols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
        if "plan" not in acols:
            conn.execute("ALTER TABLE accounts ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")

    if version < 12:
        # Credit balance on the account (coupons / prepaid packs). The coupons tables themselves are
        # created by the CREATE TABLE IF NOT EXISTS block above, so only the column needs a step here.
        acols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
        if "credits" not in acols:
            conn.execute("ALTER TABLE accounts ADD COLUMN credits INTEGER NOT NULL DEFAULT 0")

    if version < 13:
        # Which tier and billing cycle a subscription is for. Existing rows predate multiple tiers
        # and the annual option, so they are exactly what the defaults describe: the paid tier,
        # billed monthly.
        scols = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
        if "plan" not in scols:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN plan TEXT")
            conn.execute("UPDATE subscriptions SET plan='pro' WHERE plan IS NULL")
        if "cycle" not in scols:
            conn.execute(
                "ALTER TABLE subscriptions ADD COLUMN cycle TEXT NOT NULL DEFAULT 'monthly'")

    if version < 14:
        # usage_counters gains a `meter` column and a wider primary key. SQLite cannot alter a PK,
        # so rebuild. Old rows counted GENERATIONS, which the new scheme has no equivalent for —
        # they are dropped rather than mislabelled as tokens or lessons, which would hand users a
        # wrong allowance on the changeover day. Losing at most one day of counters is the cheaper
        # error, and only for accounts that generated on that day.
        ucols = {r[1] for r in conn.execute("PRAGMA table_info(usage_counters)")}
        if "meter" not in ucols:
            conn.executescript("""
                DROP TABLE IF EXISTS usage_counters_old;
                ALTER TABLE usage_counters RENAME TO usage_counters_old;
                CREATE TABLE usage_counters (
                    owner_id  TEXT NOT NULL,
                    day       TEXT NOT NULL,
                    meter     TEXT NOT NULL DEFAULT 'tokens',
                    count     INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (owner_id, day, meter)
                );
                DROP TABLE usage_counters_old;
            """)

    if version < 15:
        # Link a saved lesson to its chat turn, so deleting it from the library also removes the
        # duplicate copy of the Word documents from the conversation. Existing rows keep NULL —
        # their message can no longer be identified, so deleting them clears the library only.
        lcols = {r[1] for r in conn.execute("PRAGMA table_info(saved_lessons)")}
        if "message_id" not in lcols:
            conn.execute("ALTER TABLE saved_lessons ADD COLUMN message_id INTEGER")

    if version < 18:
        # The ledger recorded the subscription handle but not the payment's own uid, and a refund is
        # issued against the payment. Existing rows keep NULL: those charges can still be refunded,
        # but only by looking the transaction up in the PayPlus dashboard first.
        bcols = {r[1] for r in conn.execute("PRAGMA table_info(billing_ledger)")}
        if "txn_uid" not in bcols:
            conn.execute("ALTER TABLE billing_ledger ADD COLUMN txn_uid TEXT")

    if version < 19:
        # Coupon discount balance and temporary boost tracking for accounts with an active PayPlus
        # subscription — see the subscriptions table comment above.
        scols = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
        for col, ddl in (("coupon_discount_ils", "REAL NOT NULL DEFAULT 0"),
                        ("coupon_revert_plan", "TEXT"),
                        ("coupon_revert_at", "TEXT")):
            if col not in scols:
                conn.execute(f"ALTER TABLE subscriptions ADD COLUMN {col} {ddl}")

    # v20: message_reports is a brand-new table (see CREATE TABLE IF NOT EXISTS above) — no ALTER
    # needed on an existing database, so there is nothing to do here beyond the version bump.

    if version < 21:
        # How many generations were in flight (this one included) when this request started —
        # a concurrency measurement, same "number, not content" rule as the rest of this table.
        # Existing rows predate the counter and keep NULL (unknown, not zero).
        ucols = {r[1] for r in conn.execute("PRAGMA table_info(usage_events)")}
        if "concurrent_at_start" not in ucols:
            conn.execute("ALTER TABLE usage_events ADD COLUMN concurrent_at_start INTEGER")

    if version < 22:
        # message_reports gains source (user vs the auto keyword scan) and reviewed_at (so the
        # operator's backlog shrinks as things get handled). Existing rows predate both — they are
        # all genuine user reports, so source defaults to 'user'; reviewed_at NULL means "not yet
        # reviewed", true of every pre-existing row since there was no review workflow before this.
        rcols = {r[1] for r in conn.execute("PRAGMA table_info(message_reports)")}
        if "source" not in rcols:
            conn.execute("ALTER TABLE message_reports ADD COLUMN source TEXT NOT NULL DEFAULT 'user'")
        if "reviewed_at" not in rcols:
            conn.execute("ALTER TABLE message_reports ADD COLUMN reviewed_at TEXT")

    if version < 23:
        # User-renamable chats + pinning (up to 3, enforced in set_session_pinned). Existing rows
        # predate both and get NULL — unrenamed (falls back to first_q) and unpinned, unchanged
        # behaviour.
        scols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "title" not in scols:
            conn.execute("ALTER TABLE sessions ADD COLUMN title TEXT")
        if "pinned_at" not in scols:
            conn.execute("ALTER TABLE sessions ADD COLUMN pinned_at TEXT")

    # v24: calendar_cache is a brand-new table (see CREATE TABLE IF NOT EXISTS above) — no ALTER
    # needed, the executescript already created it for both fresh and pre-existing databases.

    if version < 25:
        # Per-chat opt-out from the operator's post-10.8.2026 review/improvement use (privacy policy
        # section 12). Existing rows predate the flag and default to 0 (included) — the privacy
        # policy change only applies to sessions created from 10.8.2026 onward anyway, so pre-existing
        # rows never fall under that use regardless of this flag's value.
        scols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "excluded_from_review" not in scols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN excluded_from_review INTEGER NOT NULL DEFAULT 0")

    # v26: feedback is a brand-new table (see CREATE TABLE IF NOT EXISTS above) — no ALTER needed.
    # v27: orgs / org_members / org_access_log are likewise brand-new — nothing to migrate.

    # v28: org_members.removed_at. A database created at v27 has the table without it.
    if _table_exists(conn, "org_members"):
        mcols = {r[1] for r in conn.execute("PRAGMA table_info(org_members)")}
        if "removed_at" not in mcols:
            conn.execute("ALTER TABLE org_members ADD COLUMN removed_at TEXT")

    if version < 31:
        # The model's own list of the works it used (the HHH block) was returned in the API response
        # and stored nowhere, so it vanished the moment a conversation was reloaded — the feature
        # would have looked broken rather than absent. Additive, like every column above it.
        mcols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "source_note" not in mcols:
            conn.execute("ALTER TABLE messages ADD COLUMN source_note TEXT NOT NULL DEFAULT ''")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

    # The store starts empty by default — no demo content in the database. Set
    # CHAVRUTA_SEED_DEMO=1 to seed the showcase conversations into a brand-new DB
    # (used only for screenshots/demos); they are still seeded at most once.
    if fresh_db and os.environ.get("CHAVRUTA_SEED_DEMO", "0") == "1":
        _seed_demo(conn)


def _seed_demo(conn: sqlite3.Connection) -> None:
    """Insert demo conversations into a brand-new database (called once, ever)."""
    now_dt = datetime.now(UTC)

    def _seed_session(sid: str, first_q: str, ts: datetime) -> None:
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at, updated_at) VALUES (?,?,?,?)",
            (sid, first_q, ts.isoformat(), ts.isoformat()),
        )

    sid_1 = "shenayim-ochazin"
    sid_2 = "session-2"
    sid_3 = "session-3"
    sid_4 = "session-4"

    _seed_session(sid_1, "סוגיית שניים אוחזין", now_dt)
    _seed_session(sid_2, "דיני שומרים - בבא מציעא", now_dt - timedelta(minutes=10))
    _seed_session(sid_3, 'מצוות תלמוד תורה לרמב"ם', now_dt - timedelta(minutes=20))
    _seed_session(sid_4, "קניין חצר וארבע אמות", now_dt - timedelta(minutes=30))

    # Seed messages for Session 1 (Shenayim Ochazin) to match screen.png
    # Message 1: Assistant
    citations_1 = [
        {
            "ref": 'בבא מציעא ב\' ע"א',
            "text_he": '"שניים אוחזין בטלית, זה אומר אני מצאתיה וזה אומר אני מצאתיה..."',
            "text_en": '"Two hold a garment, this one says I found it and that one says I found it..."',
            "commentator": "Gemara",
            "deep_link": "https://www.sefaria.org/Bava_Metzia.2a"
        }
    ]
    conn.execute(
        """INSERT INTO messages (session_id, role, text, intent, citations, caveats, grounded, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            sid_1,
            "assistant",
            "המשנה פותחת במקרה של \"שניים אוחזין בטלית\". שים לב לדייק בלשון - לא \"שניים מחזיקים\", אלא \"אוחזין\", דבר המלמד על תפיסה משפטית של חזקה מיידית. האם תרצה להעמיק במחלוקת של זה אומר כולה שלי וזה אומר כולה שלי?",
            "qa",
            json.dumps(citations_1, ensure_ascii=False),
            "[]",
            1,
            (now_dt - timedelta(minutes=5)).isoformat()
        )
    )

    # Message 2: User
    conn.execute(
        """INSERT INTO messages (session_id, role, text, intent, citations, caveats, grounded, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            sid_1,
            "user",
            "כן, הייתי רוצה להבין איך רש\"י מסביר את הצורך בשבועה במקרה הזה. למה לא פוסקים \"כל דאלים גבר\" או חלוקה בלי שבועה?",
            None,
            "[]",
            "[]",
            None,
            (now_dt - timedelta(minutes=3)).isoformat()
        )
    )

    # Message 3: Assistant
    citations_3 = [
        {
            "ref": 'בבא מציעא ב\' ע"א',
            "text_he": '"שניים אוחזין בטלית, זה אומר אני מצאתיה וזה אומר אני מצאתיה..."',
            "text_en": '"Two hold a garment, this one says I found it and that one says I found it..."',
            "commentator": "Gemara",
            "deep_link": "https://www.sefaria.org/Bava_Metzia.2a"
        },
        {
            "ref": 'רש"י על ב\' ע"א',
            "text_he": '"תקנת חכמים היא שיהו נשבעין, כדי שלא יהיה כל אחד ואחד תוקף..."',
            "text_en": '"It is a rabbinic decree that they should swear, so that everyone does not grab..."',
            "commentator": "Rashi",
            "deep_link": "https://www.sefaria.org/Rashi_on_Bava_Metzia.2a"
        },
        {
            "ref": 'רמב"ם, הלכות גזילה',
            "text_he": 'פרק ט׳ הלכה א׳: דיני חלוקת אבידה בשניים אוחזין...',
            "text_en": 'Chapter 9 Halacha 1: Laws of dividing a lost item held by two...',
            "commentator": "Rambam",
            "deep_link": "https://www.sefaria.org/Mishneh_Torah%2C_Robbery_and_Lost_Property.9"
        },
        {
            "ref": 'תוספות ד"ה "ויחלוקו"',
            "text_he": 'הקשה ר״י, למה לא אמרינן יהא מונח עד שיבוא אליהו?',
            "text_en": 'Rabbi Isaac asked, why do we not say it should be left until Elijah comes?',
            "commentator": "Tosafot",
            "deep_link": "https://www.sefaria.org/Tosafot_on_Bava_Metzia.2a"
        }
    ]
    conn.execute(
        """INSERT INTO messages (session_id, role, text, intent, citations, caveats, grounded, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            sid_1,
            "assistant",
            "שאלה מצוינת. רש\"י במקום מסביר שהשבועה היא תקנת חכמים (ראה מקור 2 משמאל).\n\nהחשש הוא שאם יחלקו ללא שבועה, \"כל אחד ואחד ילך ויתקוף בטליתו של חברו\". השבועה מרתיעה את הרמאי. שים לב שזו שבועה מסוג \"נשבעין ונוטלין\", בניגוד לכלל הרגיל של \"המוציא מחברו עליו הראיה\".",
            "qa",
            json.dumps(citations_3, ensure_ascii=False),
            "[]",
            1,
            (now_dt - timedelta(minutes=1)).isoformat()
        )
    )
    conn.commit()


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(first_q: str, mode: str | None = None, owner_id: str = "local") -> str:
    sid = str(uuid.uuid4())
    now = _now()
    with _tx(get_conn()) as conn:
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at, updated_at, mode, owner_id) "
            "VALUES (?,?,?,?,?,?)",
            (sid, first_q, now, now, mode or None, owner_id),
        )
    return sid


def owns_session(sid: str, owner_id: str = "local") -> bool:
    """True if this owner may touch the session — the ownership gate every session route checks."""
    with _LOCK:
        r = get_conn().execute(
            "SELECT 1 FROM sessions WHERE id=? AND owner_id=?", (sid, owner_id)).fetchone()
    return r is not None


def get_session_mode(sid: str, owner_id: str = "local") -> str | None:
    """The chat's locked mode (the intent chosen on its first turn), or None for legacy/foreign."""
    with _LOCK:
        r = get_conn().execute(
            "SELECT mode FROM sessions WHERE id=? AND owner_id=?", (sid, owner_id)).fetchone()
    return (r["mode"] if r else None) or None


def list_sessions(owner_id: str = "local") -> list[dict[str, Any]]:
    with _LOCK:
        # Only this owner's sessions. Pinned chats bubble to the very top (most-recently-pinned
        # first), then the rest order by last activity; fall back to created_at for rows that
        # predate updated_at.
        rows = get_conn().execute(
            """SELECT id, first_q, created_at, updated_at, mode, title, pinned_at,
                      excluded_from_review
               FROM sessions
               WHERE owner_id=?
               ORDER BY pinned_at IS NULL, pinned_at DESC, COALESCE(updated_at, created_at) DESC
               LIMIT 100""",
            (owner_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(sid: str, owner_id: str = "local") -> bool:
    with _tx(get_conn()) as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id=? AND owner_id=?", (sid, owner_id))
    return cur.rowcount > 0


def rename_session(sid: str, owner_id: str, title: str) -> bool:
    """Set the user-given display name. `title` is already trimmed/validated by the caller."""
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            "UPDATE sessions SET title=? WHERE id=? AND owner_id=?", (title, sid, owner_id))
    return cur.rowcount > 0


def set_session_excluded(sid: str, owner_id: str, excluded: bool) -> bool:
    """Opt this chat in/out of the operator's post-10.8.2026 review/improvement use (privacy policy
    section 12). Returns False if the session isn't owned by this owner."""
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            "UPDATE sessions SET excluded_from_review=? WHERE id=? AND owner_id=?",
            (1 if excluded else 0, sid, owner_id),
        )
    return cur.rowcount > 0


# ── The single gate on reading user conversations for review/improvement ──────────────────────
#
# Privacy policy 1.8 / Terms 1.10 permit the operator to review conversation content to improve the
# service — but only under three conditions, all of which were promised to users in the notice email
# and all of which are enforced HERE and nowhere else. A second enforcement point is how one of them
# eventually gets forgotten.
#
#   1. NOT RETROACTIVE. Only conversations created from 2026-08-10 00:00 Israel time onward. Anything
#      older was collected under the previous promise ("used only to operate the service") and is
#      permanently out of scope — not "probably fine", out of scope.
#   2. The per-chat opt-out (sessions.excluded_from_review).
#   3. The account-wide opt-out, which lives in Supabase user_metadata (data_review_opt_out) and so
#      cannot be read from here — the caller passes the opted-out owner ids in. It OVERRIDES the
#      per-chat setting, which is why it is applied as an exclusion rather than merged.
#   4. A PENDING DELETION REQUEST. Someone who has asked to be deleted has withdrawn their consent to
#      be read; that the data still physically exists for another 30 days is an implementation detail
#      of making an accidental click reversible, not a licence to keep using it in the meantime. The
#      request is the moment the reading stops, not the purge. Cancelling the deletion puts the
#      account back in scope on its own — the row simply reappears in this query.
#
# Passing opted_out_owners=None means "the caller has not established who opted out", which is
# treated as ALL owners opted out rather than none: failing closed on a privacy gate is the only
# safe default, and a caller that genuinely has no opt-outs passes an empty collection.
REVIEW_EFFECTIVE_FROM = "2026-08-09T21:00:00"   # 2026-08-10 00:00 Israel time, in UTC


def reviewable_questions(*, since: str | None = None, limit: int = 200,
                         opted_out_owners: Collection[str] | None = ()) -> list[dict[str, Any]]:
    """User questions the operator is permitted to review, oldest first.

    The ONLY sanctioned way to read conversation text for review, evaluation or model improvement.
    Do not hand-roll a query over `messages` for those purposes — see the conditions above.
    """
    if opted_out_owners is None:
        return []
    cutoff = max(since or REVIEW_EFFECTIVE_FROM, REVIEW_EFFECTIVE_FROM)   # never before the promise
    with _LOCK:
        rows = get_conn().execute(
            """SELECT m.id, m.text, m.intent, m.created_at, s.id AS session_id, s.owner_id
               FROM messages m JOIN sessions s ON s.id = m.session_id
               WHERE m.role = 'user'
                 AND s.excluded_from_review = 0
                 AND s.owner_id NOT IN (SELECT owner_id FROM accounts
                                        WHERE deletion_scheduled_for IS NOT NULL)
                 AND s.created_at >= ?
               ORDER BY m.id ASC
               LIMIT ?""",
            (cutoff, max(1, int(limit))),
        ).fetchall()
    excluded = {o for o in opted_out_owners}
    return [dict(r) for r in rows if r["owner_id"] not in excluded]


MAX_PINNED_SESSIONS = 3


class TooManyPinnedError(Exception):
    """Raised by set_session_pinned when pinning would exceed MAX_PINNED_SESSIONS."""


def set_session_pinned(sid: str, owner_id: str, pinned: bool) -> bool:
    """Pin (or unpin) a chat so it sorts to the top of the list. Returns False if the session isn't
    owned by this owner. Raises TooManyPinnedError if pinning would exceed MAX_PINNED_SESSIONS —
    the caller must unpin one first, same as the frontend's own pre-emptive disabled state."""
    with _tx(get_conn()) as conn:
        row = conn.execute(
            "SELECT pinned_at FROM sessions WHERE id=? AND owner_id=?", (sid, owner_id)).fetchone()
        if row is None:
            return False
        if pinned:
            if row["pinned_at"] is not None:
                return True  # already pinned — idempotent
            count = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE owner_id=? AND pinned_at IS NOT NULL",
                (owner_id,),
            ).fetchone()[0]
            if count >= MAX_PINNED_SESSIONS:
                raise TooManyPinnedError(f"already {MAX_PINNED_SESSIONS} pinned chats")
            conn.execute(
                "UPDATE sessions SET pinned_at=? WHERE id=? AND owner_id=?",
                (_now(), sid, owner_id))
        else:
            conn.execute(
                "UPDATE sessions SET pinned_at=NULL WHERE id=? AND owner_id=?", (sid, owner_id))
    return True


# ── Messages ──────────────────────────────────────────────────────────────────

def save_message(
    session_id: str,
    role: str,
    text: str,
    intent: str | None = None,
    citations: list[dict] | None = None,
    caveats: list[str] | None = None,
    grounded: bool | None = None,
    files: list[dict] | None = None,
    source_note: str = "",
) -> int:
    now = _now()
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            """INSERT INTO messages
               (session_id, role, text, intent, citations, caveats, grounded, files,
                source_note, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                role,
                text,
                intent,
                json.dumps(citations, ensure_ascii=False) if citations is not None else None,
                json.dumps(caveats, ensure_ascii=False) if caveats is not None else None,
                int(grounded) if grounded is not None else None,
                json.dumps(files, ensure_ascii=False) if files else None,
                source_note or "",
                now,
            ),
        )
        message_id = cur.lastrowid
        # Touch the parent session so it sorts to the top of the chat list.
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
        _auto_flag_if_problematic(conn, message_id, session_id, text, now)
    return message_id


def _auto_flag_if_problematic(conn: sqlite3.Connection, message_id: int, session_id: str,
                              text: str, now: str) -> None:
    """Heuristic keyword scan (app/moderation.py) on every saved message. Never raises and never
    blocks the save — a scan failure or a hit is not a reason to lose the user's message."""
    try:
        categories = moderation.scan(text)
        if not categories:
            return
        owner_row = conn.execute(
            "SELECT owner_id FROM sessions WHERE id=?", (session_id,)).fetchone()
        owner_id = owner_row["owner_id"] if owner_row else "local"
        for category in categories:
            conn.execute(
                "INSERT INTO message_reports (message_id, owner_id, reason, source, created_at) "
                "VALUES (?,?,?,'auto',?)",
                (message_id, owner_id, category, now))
    except Exception:                       # noqa: BLE001
        _telemetry_log.exception("auto content scan failed for message %s", message_id)


def get_messages(session_id: str, owner_id: str = "local") -> list[dict[str, Any]]:
    with _LOCK:
        # Scoped to the owner via a subquery, so a guessed session id from another owner reads
        # nothing (the route then 404s) rather than leaking the conversation.
        rows = get_conn().execute(
            "SELECT * FROM messages WHERE session_id=? "
            "AND session_id IN (SELECT id FROM sessions WHERE id=? AND owner_id=?) ORDER BY id",
            (session_id, session_id, owner_id),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["citations"] = json.loads(d["citations"]) if d["citations"] else []
        d["caveats"] = json.loads(d["caveats"]) if d["caveats"] else []
        d["grounded"] = bool(d["grounded"]) if d["grounded"] is not None else None
        d["files"] = json.loads(d["files"]) if d.get("files") else []
        d["source_note"] = d.get("source_note") or ""
        out.append(d)
    return out


def report_message(message_id: int, owner_id: str, reason: str) -> None:
    """Record a user-flagged answer for operator review — see message_reports in _migrate() for why
    this exists. Verifies the message belongs to a session the caller owns (same scoping as
    get_messages), so one account can't flag into another's private conversation; raises ValueError
    if it doesn't, which the route turns into a 404."""
    with _tx(get_conn()) as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE id=? "
            "AND session_id IN (SELECT id FROM sessions WHERE owner_id=?)",
            (message_id, owner_id),
        ).fetchone()
        if row is None:
            raise ValueError("message not found")
        conn.execute(
            "INSERT INTO message_reports (message_id, owner_id, reason, created_at) VALUES (?,?,?,?)",
            (message_id, owner_id, (reason or "").strip()[:500], datetime.now(UTC).isoformat()),
        )


def list_flagged_messages(reviewed: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    """Reports awaiting operator review by default (reviewed=False); pass True to see the ones
    already handled. Joins in the actual message text — unlike usage_events, a report exists
    precisely so a human can read what triggered it; there is no separate content-free path here."""
    return _agg(
        "SELECT r.id, r.message_id, r.owner_id, r.reason, r.source, r.created_at, "
        "r.reviewed_at, m.role, m.text, m.session_id "
        "FROM message_reports r JOIN messages m ON m.id = r.message_id "
        "WHERE (r.reviewed_at IS NOT NULL) = ? "
        "ORDER BY r.created_at DESC LIMIT ?",
        (int(reviewed), limit))


def mark_report_reviewed(report_id: int) -> bool:
    """Mark one report as handled, so it drops off the default (unreviewed) backlog."""
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            "UPDATE message_reports SET reviewed_at=? WHERE id=? AND reviewed_at IS NULL",
            (datetime.now(UTC).isoformat(), report_id))
    return cur.rowcount > 0


def submit_feedback(owner_id: str, text: str) -> None:
    """Record a general comment/correction/suggestion — not tied to any specific message, unlike
    report_message(). `text` is already trimmed/length-checked by the caller."""
    with _tx(get_conn()) as conn:
        conn.execute(
            "INSERT INTO feedback (owner_id, text, created_at) VALUES (?,?,?)",
            (owner_id, text, datetime.now(UTC).isoformat()),
        )


def list_feedback(reviewed: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    """Feedback awaiting operator review by default (reviewed=False); pass True for handled ones."""
    return _agg(
        "SELECT id, owner_id, text, created_at, reviewed_at FROM feedback "
        "WHERE (reviewed_at IS NOT NULL) = ? ORDER BY created_at DESC LIMIT ?",
        (int(reviewed), limit))


def mark_feedback_reviewed(feedback_id: int) -> bool:
    """Mark one feedback item as handled, so it drops off the default (unreviewed) backlog."""
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            "UPDATE feedback SET reviewed_at=? WHERE id=? AND reviewed_at IS NULL",
            (datetime.now(UTC).isoformat(), feedback_id))
    return cur.rowcount > 0


# ── 'My Shiurim' saved-lesson library ────────────────────────────────────────

def save_lesson(lesson_id: str, topic: str, audience: str, grade_band: str, length: str,
                lang: str, files: list[dict], citations: list[dict] | None = None,
                owner_id: str = "local") -> None:
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT OR REPLACE INTO saved_lessons "
            "(id, topic, audience, grade_band, length, lang, files, citations, created_at, owner_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (lesson_id, topic, audience or "", grade_band or "", length or "", lang or "he",
             json.dumps(files, ensure_ascii=False),
             json.dumps(citations or [], ensure_ascii=False), _now(), owner_id),
        )


def list_lessons(owner_id: str = "local") -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT id, topic, audience, grade_band, length, lang, created_at "
            "FROM saved_lessons WHERE owner_id=? ORDER BY created_at DESC",
            (owner_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_lesson(lesson_id: str, owner_id: str = "local") -> dict[str, Any] | None:
    with _LOCK:
        r = get_conn().execute(
            "SELECT * FROM saved_lessons WHERE id=? AND owner_id=?", (lesson_id, owner_id)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["files"] = json.loads(d["files"]) if d.get("files") else []
    d["citations"] = json.loads(d["citations"]) if d.get("citations") else []
    return d


def record_usage_event(**fields: Any) -> None:
    """Append one generation's measurements. Never raises — telemetry must not be able to fail a
    request that otherwise worked."""
    cols = ("at", "hour_local", "dow", "owner_id", "plan", "intent", "lang", "prompt_tokens",
            "completion_tokens", "billed_tokens", "llm_calls", "ms", "grounded", "no_source",
            "citations", "audience", "grade_band", "length", "attachments", "error",
            "concurrent_at_start")
    row = {k: fields.get(k) for k in cols}
    try:
        conn = get_conn()
        with _LOCK, _tx(conn):
            conn.execute(
                f"INSERT INTO usage_events ({','.join(cols)}) "     # noqa: S608 — fixed column list
                f"VALUES ({','.join('?' * len(cols))})",
                tuple(row[k] for k in cols))
    except Exception:                       # noqa: BLE001
        _telemetry_log.exception("failed to record a usage event")


def _agg(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(r) for r in get_conn().execute(sql, args).fetchall()]


def usage_by_owner(since: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Per-account totals — who is using it and what they cost.

    Anonymised rows are EXCLUDED. purge_owner sets usage_events.owner_id to NULL rather than deleting
    the row, so the measurements stay true (see there) — but a plain GROUP BY then collapses every
    account ever deleted into a single nameless row, which ranked fourth in "top users" and would
    only climb. It is not a user: it is the sum of people who left. The totals that should include
    those requests (usage_health, revenue, by-intent) still do — this is the one view that is per
    ACCOUNT, and an event with no account has nothing to say in it.
    """
    clauses = ["owner_id IS NOT NULL"]
    args: list[Any] = []
    if since:
        clauses.append("at >= ?")
        args.append(since)
    where = "WHERE " + " AND ".join(clauses)
    return _agg(
        f"SELECT owner_id, COUNT(*) AS requests, SUM(billed_tokens) AS tokens, "   # noqa: S608
        f"SUM(llm_calls) AS calls, AVG(ms) AS avg_ms, "
        f"SUM(CASE WHEN grounded=1 THEN 1 ELSE 0 END) AS grounded "
        f"FROM usage_events {where} GROUP BY owner_id ORDER BY tokens DESC LIMIT ?",
        (*args, limit))


def usage_by_intent(since: str | None = None) -> list[dict[str, Any]]:
    """Which modes people actually reach for, and what each one costs on average."""
    where = "WHERE at >= ?" if since else ""
    return _agg(
        f"SELECT intent, COUNT(*) AS requests, SUM(billed_tokens) AS tokens, "     # noqa: S608
        f"AVG(billed_tokens) AS avg_tokens, AVG(ms) AS avg_ms, "
        f"SUM(CASE WHEN grounded=1 THEN 1 ELSE 0 END) AS grounded, "
        f"SUM(CASE WHEN no_source=1 THEN 1 ELSE 0 END) AS no_source "
        f"FROM usage_events {where} GROUP BY intent ORDER BY requests DESC",
        ((since,) if since else ()))


def usage_by_intent_for(joined_at: Mapping[str, str]) -> list[dict[str, Any]]:
    """What an organisation's members have been studying — as MODE COUNTS, never as text.

    This is the whole "topics" view a school gets (spec 004 decision 1), and it reads `usage_events`
    for a reason: that table's columns are a fixed list of measurements, so there is no path from it
    to anything a member wrote. The intuitive alternative — joining `sessions` — would hand a teacher
    `first_q`, the verbatim opening question of every conversation.

    Takes {owner_id: accepted_at} and bounds EACH member to their OWN join date — not one cutoff for
    the group, which would still hand the school everything a late joiner did before they arrived. A
    school is entitled to see what it is paying for; it is not entitled to the year of private study
    someone did on their own free account beforehand. Without the bound, the first panel load after a
    teacher joins reports their entire personal history as "what this member has been studying".
    """
    pairs = [(o, s) for o, s in (joined_at or {}).items() if o and s]
    if not pairs:
        return []
    clause = " OR ".join("(owner_id = ? AND at >= ?)" for _ in pairs)
    args = tuple(v for pair in pairs for v in pair)
    return _agg(
        f"SELECT intent, COUNT(*) AS requests, SUM(billed_tokens) AS tokens "      # noqa: S608
        f"FROM usage_events WHERE {clause} "
        f"GROUP BY intent ORDER BY requests DESC",
        args)


def usage_by_hour(since: str | None = None) -> list[dict[str, Any]]:
    """When the product is used, in local time — what a maintenance window has to avoid."""
    where = "WHERE at >= ?" if since else ""
    return _agg(
        f"SELECT hour_local AS hour, COUNT(*) AS requests, SUM(billed_tokens) AS tokens "  # noqa: S608
        f"FROM usage_events {where} GROUP BY hour_local ORDER BY hour_local",
        ((since,) if since else ()))


def usage_by_dow(since: str | None = None) -> list[dict[str, Any]]:
    return _agg(
        f"SELECT dow, COUNT(*) AS requests FROM usage_events "                    # noqa: S608
        f"{'WHERE at >= ?' if since else ''} GROUP BY dow ORDER BY dow",
        ((since,) if since else ()))


def lesson_breakdown(since: str | None = None) -> list[dict[str, Any]]:
    """Who lessons are being built for — the audience/grade mix drives which templates matter."""
    where = "WHERE intent='lesson'" + (" AND at >= ?" if since else "")
    return _agg(
        f"SELECT audience, grade_band, length, COUNT(*) AS requests, "            # noqa: S608
        f"AVG(billed_tokens) AS avg_tokens FROM usage_events {where} "
        f"GROUP BY audience, grade_band, length ORDER BY requests DESC",
        ((since,) if since else ()))


def usage_health(since: str | None = None) -> dict[str, Any]:
    """The headline numbers: volume, cost, how often we answer from real sources, what breaks."""
    where = "WHERE at >= ?" if since else ""
    rows = _agg(
        f"SELECT COUNT(*) AS requests, SUM(billed_tokens) AS tokens, "            # noqa: S608
        f"SUM(CASE WHEN grounded=1 THEN 1 ELSE 0 END) AS grounded, "
        f"SUM(CASE WHEN no_source=1 THEN 1 ELSE 0 END) AS no_source, "
        f"SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors, "
        f"SUM(CASE WHEN llm_calls > 1 THEN 1 ELSE 0 END) AS agentic, "
        f"AVG(ms) AS avg_ms, COUNT(DISTINCT owner_id) AS users "
        f"FROM usage_events {where}", ((since,) if since else ()))
    return rows[0] if rows else {}


def usage_concurrency(since: str | None = None) -> dict[str, Any]:
    """Peak and average concurrent generations — how many requests were actually running (this one
    included) at the moment each one started. Distinct from CHAVRUTA_MAX_CONCURRENT_GENERATIONS,
    which is the CEILING we allow; this is what was ACTUALLY observed."""
    where = "WHERE at >= ? AND concurrent_at_start IS NOT NULL" if since \
        else "WHERE concurrent_at_start IS NOT NULL"
    rows = _agg(
        f"SELECT MAX(concurrent_at_start) AS peak, AVG(concurrent_at_start) AS avg "  # noqa: S608
        f"FROM usage_events {where}", ((since,) if since else ()))
    return rows[0] if rows else {}


def usage_by_week(since: str | None = None) -> list[dict[str, Any]]:
    """Distinct users per ISO week — the trend line behind the single-period 'users' figure in
    usage_health(). One row per calendar week that had any activity."""
    where = "WHERE at >= ?" if since else ""
    return _agg(
        f"SELECT strftime('%Y-W%W', at) AS week, COUNT(*) AS requests, "           # noqa: S608
        f"COUNT(DISTINCT owner_id) AS users "
        f"FROM usage_events {where} GROUP BY week ORDER BY week",
        ((since,) if since else ()))


def usage_over_time(since: str | None = None, bucket: str = "day") -> list[dict[str, Any]]:
    """Token spend per day or per week — what was actually consumed, and in which direction.

    `prompt` and `completion` are kept SEPARATE rather than summed, because the ratio between them is
    the number that turned out to matter: measured on 2026-08-13 it was 6,550 in to 442 out per model
    call, 15:1. A single "tokens" figure hides that entirely, and the input side is both the larger
    cost and the one that can be reduced without shortening a single answer.

    `billed` is the normalized unit (prompt + 3x completion) the quota is metered in — it is what a
    turn costs us, so it is what a spend figure has to be counted in.

    Anonymised rows ARE included, unlike usage_by_owner: a request made by someone who has since
    deleted their account still cost what it cost, and a spend total that quietly drops history would
    be wrong in the one direction that matters.
    """
    fmt = "%Y-W%W" if bucket == "week" else "%Y-%m-%d"
    where = "WHERE at >= ?" if since else ""
    return _agg(
        f"SELECT strftime('{fmt}', at) AS bucket, COUNT(*) AS requests, "          # noqa: S608
        f"SUM(llm_calls) AS calls, "
        f"SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion, "
        f"SUM(billed_tokens) AS billed, "
        f"COUNT(DISTINCT owner_id) AS users "
        f"FROM usage_events {where} GROUP BY bucket ORDER BY bucket",
        ((since,) if since else ()))


def count_accounts() -> dict[str, Any]:
    """How many accounts exist in total, and by plan — registered accounts, not just ones that have
    generated anything (that's usage_health()'s 'users', a different, usage-based count)."""
    rows = _agg("SELECT plan, COUNT(*) AS n FROM accounts GROUP BY plan")
    return {"total": sum(r["n"] for r in rows), "by_plan": {r["plan"]: r["n"] for r in rows}}


def revenue_summary(since: str | None = None) -> dict[str, Any]:
    """Billed amounts from billing_ledger, grouped by plan and currency, plus a grand total per
    currency. No owner_id here (the table doesn't have one, by design — see its schema comment), so
    this is inherently account-agnostic. Refunds are already negative-amount rows in the same table,
    so they net out of the totals rather than needing separate handling."""
    where = "WHERE charged_at >= ?" if since else ""
    by_plan = _agg(
        f"SELECT plan, currency, SUM(amount) AS total, COUNT(*) AS charges "   # noqa: S608
        f"FROM billing_ledger {where} GROUP BY plan, currency ORDER BY total DESC",
        ((since,) if since else ()))
    totals = _agg(
        f"SELECT currency, SUM(amount) AS total FROM billing_ledger "          # noqa: S608
        f"{where} GROUP BY currency",
        ((since,) if since else ()))
    return {"by_plan": by_plan, "totals": {r["currency"]: r["total"] for r in totals}}


def delete_sessions_older_than(cutoff_iso: str) -> int:
    """Delete chats untouched since `cutoff_iso`. Messages cascade. Returns how many went.

    Retention, not cleanup: a conversation is kept for a bounded window and then goes, rather than
    forever by default. Keyed on `updated_at` (falling back to `created_at` for rows that predate
    it), so an old chat someone still returns to is not taken out from under them.

    Saved lessons are deliberately NOT swept — they are a teacher's work product, and quietly
    deleting one would be taking away something they made rather than tidying a transcript.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        cur = conn.execute(
            "DELETE FROM sessions WHERE COALESCE(updated_at, created_at) < ?", (cutoff_iso,))
        return cur.rowcount


def count_sessions_older_than(cutoff_iso: str) -> int:
    """How many chats a sweep would remove — for a dry run before turning retention on."""
    with _LOCK:
        row = get_conn().execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE COALESCE(updated_at, created_at) < ?",
            (cutoff_iso,)).fetchone()
    return int(row["n"])


def record_charge(*, charged_at: str, amount: float, currency: str = "ILS", plan: str | None = None,
                  cycle: str | None = None, provider: str | None = None,
                  provider_ref: str | None = None, invoice_ref: str | None = None,
                  note: str = "", txn_uid: str | None = None) -> int:
    """Append a charge to the accounting ledger. Returns the row id.

    Append-only and deliberately anonymous — see the table comment. Called on every successful
    payment, INCLUDING renewals, so the ledger is a complete record of revenue rather than a list of
    subscriptions that happen to still exist.

    A refund is appended the same way with a NEGATIVE amount and note='refund', never by editing or
    deleting the charge it reverses: the books have to show that money came in and then went back
    out, which is a different fact from the money never having arrived.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        cur = conn.execute(
            "INSERT INTO billing_ledger (charged_at, amount, currency, plan, cycle, provider, "
            "provider_ref, invoice_ref, note, txn_uid) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (charged_at, float(amount), currency, plan, cycle, provider, provider_ref,
             invoice_ref, note, txn_uid))
        return int(cur.lastrowid)


def get_charge(charge_id: int) -> dict[str, Any] | None:
    """One ledger row by id — what an operator names when issuing a refund."""
    with _LOCK:
        row = get_conn().execute("SELECT * FROM billing_ledger WHERE id = ?", (charge_id,)).fetchone()
    return dict(row) if row else None


def refunded_total(txn_uid: str) -> float:
    """How much of a payment has ALREADY been given back, as a positive number.

    The guard against refunding the same charge twice. Refunds are appended as negative rows rather
    than by marking the charge, so "has this been refunded" is a sum over the ledger and not a flag
    that a second operator could miss.
    """
    if not txn_uid:
        return 0.0
    with _LOCK:
        row = get_conn().execute(
            "SELECT COALESCE(SUM(amount), 0) FROM billing_ledger WHERE txn_uid = ? AND amount < 0",
            (txn_uid,)).fetchone()
    return round(-float(row[0] or 0.0), 2)


def list_charges(since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
    """The ledger, newest first — for reconciliation and for handing an accountant a period."""
    sql = "SELECT * FROM billing_ledger"
    args: list[Any] = []
    where = []
    if since:
        where.append("charged_at >= ?")
        args.append(since)
    if until:
        where.append("charged_at <= ?")
        args.append(until)
    if where:
        sql += " WHERE " + " AND ".join(where)
    with _LOCK:
        rows = get_conn().execute(sql + " ORDER BY charged_at DESC", args).fetchall()
    return [dict(r) for r in rows]


# ── Guard findings (what the watching checks caught) ──────────────────────────
def record_guard_finding(kind: str, intent: str, detail: dict[str, Any],
                         at: str | None = None) -> None:
    """Store one finding. Never raises: this is called from the answer path, and a diagnostic that
    can break a user's answer is worse than a diagnostic nobody has."""
    try:
        with _tx(get_conn()) as conn:
            conn.execute(
                "INSERT INTO guard_findings (at, kind, intent, detail) VALUES (?,?,?,?)",
                (at or _now(), kind, intent or None, json.dumps(detail, ensure_ascii=False)))
    except Exception:                       # noqa: BLE001
        # `_telemetry_log`, not `_log`: this module has never had a bare `_log`, and writing one here
        # meant the only line in the except branch was itself a NameError. The tests passed because
        # the branch only runs when the insert fails — a handler that breaks exactly when it is
        # needed, which is the same shape as the misattribution NameError earlier today.
        _telemetry_log.exception("failed to record guard finding (%s)", kind)


def list_guard_findings(since: str | None = None, kind: str = "",
                        limit: int = 100) -> list[dict[str, Any]]:
    """Newest first. `detail` comes back PARSED — a caller that has to json.loads every row is a
    caller that will eventually forget to, and render a JSON blob at the operator."""
    sql = "SELECT id, at, kind, intent, detail FROM guard_findings"
    where, args = [], []
    if since:
        where.append("at >= ?")
        args.append(since)
    if kind:
        where.append("kind = ?")
        args.append(kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    with _LOCK:
        rows = get_conn().execute(sql + " ORDER BY at DESC LIMIT ?",
                                  [*args, max(1, int(limit))]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d["detail"])
        except (TypeError, ValueError):
            d["detail"] = {"raw": d["detail"]}   # never lose the row over a bad parse
        out.append(d)
    return out


def guard_finding_counts(since: str | None = None) -> dict[str, int]:
    """How many of each kind — the number that says whether a guard is worth showing to users yet."""
    sql = "SELECT kind, COUNT(*) n FROM guard_findings"
    args: list[Any] = []
    if since:
        sql += " WHERE at >= ?"
        args.append(since)
    with _LOCK:
        rows = get_conn().execute(sql + " GROUP BY kind", args).fetchall()
    return {r["kind"]: r["n"] for r in rows}


def revenue_total(since: str | None = None, until: str | None = None) -> float:
    return round(sum(float(r["amount"]) for r in list_charges(since, until)), 2)


def link_lesson_message(lesson_id: str, message_id: int) -> None:
    """Record which chat turn holds this lesson's second copy of the documents. Called once the
    message exists — its id is only assigned at insert."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute("UPDATE saved_lessons SET message_id=? WHERE id=?", (message_id, lesson_id))


def delete_lesson(lesson_id: str, owner_id: str = "local") -> bool:
    """Delete a lesson from the library AND strip its documents from the chat turn that duplicates
    them, so "delete" means deleted rather than "hidden from one of the two places it is kept".

    The conversation itself is left intact — the message keeps its text, and only the downloads go.
    Removing the whole chat because a library entry was tidied away would be the more destructive
    surprise. Rows saved before the link existed have no message_id; those clear the library only.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute(
            "SELECT message_id FROM saved_lessons WHERE id=? AND owner_id=?",
            (lesson_id, owner_id)).fetchone()
        if row is None:
            return False
        if row["message_id"] is not None:
            # Scoped through the session's owner as well, so a lesson row can never be used to reach
            # into another account's message.
            conn.execute(
                "UPDATE messages SET files='[]' WHERE id=? AND session_id IN "
                "(SELECT id FROM sessions WHERE owner_id=?)", (row["message_id"], owner_id))
        cur = conn.execute(
            "DELETE FROM saved_lessons WHERE id=? AND owner_id=?", (lesson_id, owner_id))
    return cur.rowcount > 0


def _now() -> str:
    return datetime.now(UTC).isoformat()


# The product is Israeli, and "resets at midnight" / "resets Sunday" means ISRAEL midnight/Sunday to
# a user — not UTC's, which lags Israel by 2-3h (winter/DST). Using UTC dates for the daily/weekly
# quota bucket meant the reset actually landed a few hours into the Israeli morning instead of at
# local midnight (reported live, 2026-08-03).
_IL_TZ = ZoneInfo("Asia/Jerusalem")


def today_il() -> str:
    """The current Israel-local date as YYYY-MM-DD — the bucket a daily quota counts against."""
    return datetime.now(_IL_TZ).strftime("%Y-%m-%d")


def week_days(day: str | None = None) -> list[str]:
    """The seven YYYY-MM-DD dates of `day`'s week, Sunday first.

    Sunday-start because the product is Israeli and that is the week a user here means. A calendar
    week (rather than a rolling 7 days) is what the UI can state plainly — "resets Sunday" — and a
    predictable reset matters more here than closing the small boundary burst, which the daily cap
    bounds anyway.
    """
    d = datetime.strptime(day or today_il(), "%Y-%m-%d").replace(tzinfo=_IL_TZ)
    sunday = d - timedelta(days=(d.weekday() + 1) % 7)      # Python: Monday==0, so Sunday==6
    return [(sunday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


TOKENS, LESSON = "tokens", "lesson"
# BYOK (bring-your-own-key): a second allowance of the SAME size as the plan's own, spent only when
# the plan quota is exhausted AND the caller supplied their own provider API key for that request
# (never persisted — see app/api.py::_byok_llm). Own meters so the two pools never mix: the plan
# quota still resets/reports exactly as it did before this existed.
BYOK_TOKENS, BYOK_LESSON = "byok_tokens", "byok_lesson"


def _counts(conn, owner_id: str, day: str, meter: str) -> tuple[int, int]:
    """(day total, week total) for one meter. Caller must already hold the lock."""
    row = conn.execute(
        "SELECT count FROM usage_counters WHERE owner_id=? AND day=? AND meter=?",
        (owner_id, day, meter)).fetchone()
    days = week_days(day)
    wrow = conn.execute(
        f"SELECT COALESCE(SUM(count), 0) AS c FROM usage_counters "   # noqa: S608 — placeholders below
        f"WHERE owner_id=? AND meter=? AND day IN ({','.join('?' * len(days))})",
        (owner_id, meter, *days)).fetchone()
    return (int(row["count"]) if row else 0), int(wrow["c"])


def bump_usage(owner_id: str, limit: int, day: str | None = None, *, weekly_limit: int = 0,
               units: int = 1, meter: str = TOKENS) -> tuple[bool, int, int]:
    """Atomically charge `units` to one meter and enforce BOTH its daily and weekly cap.

    Returns (allowed, day_total, week_total) — the totals AFTER a successful charge, or the current
    ones when refused. A limit <= 0 disables that cap (usage is still counted, so it stays
    observable).

    Check and increment happen in ONE transaction under the shared lock, so concurrent requests
    cannot each see room and both proceed. Week totals are summed from the daily rows rather than
    kept in a counter of their own: one source of truth, so the two can never disagree.
    """
    day = day or today_il()
    units = max(0, int(units))
    conn = get_conn()
    with _LOCK, _tx(conn):
        day_count, week_count = _counts(conn, owner_id, day, meter)
        if limit > 0 and day_count + units > limit:
            return False, day_count, week_count
        if weekly_limit > 0 and week_count + units > weekly_limit:
            return False, day_count, week_count
        if units:
            conn.execute(
                "INSERT INTO usage_counters (owner_id, day, meter, count) VALUES (?,?,?,?) "
                "ON CONFLICT(owner_id, day, meter) DO UPDATE SET count = count + excluded.count",
                (owner_id, day, meter, units))
        return True, day_count + units, week_count + units


class PoolCharge(NamedTuple):
    """The outcome of a pooled charge. A NamedTuple so the existing 3-tuple unpacking still works
    while `refused` gives callers the reason they need to write an honest refusal message."""

    allowed: bool
    pool_day: int
    pool_week: int
    refused: str = ""      # "" | blocked | member_cap | day | week


def bump_pooled(member_id: str, pool_id: str, *, member_cap: int, pool_daily: int, pool_weekly: int,
                member_weekly: int = 0, units: int = 1, meter: str = TOKENS,
                day: str | None = None) -> PoolCharge:
    """Charge one turn to BOTH a member's own counter and their organisation's shared pool.

    Returns (allowed, pool_day_total, pool_week_total, refused).

    This exists because calling `bump_usage` twice is not equivalent, in two ways that both cost
    money. First, they are separate transactions, so another request interleaves between them and the
    atomicity that makes the single-row version correct is gone. Second, if the pool refuses after
    the member row was already charged, the compensation is not exact — `settle_usage` floors each
    counter at zero, so a refund can be silently swallowed and the member's counter drifts upward
    against them forever.

    Both rows are therefore checked and written under one lock and one transaction: either the turn
    is admitted and both counters move, or nothing moves at all.

    `member_cap` bounds one person's share of a shared pool — without it a single student can spend
    a school's entire day in an hour. 0 disables it (usage is still counted, so it stays visible);
    a NEGATIVE cap blocks the member outright, which is the one thing an admin most wants to express
    and could not (see orgs.CAP_BLOCKED).

    `refused` names which of the three ceilings said no. The caller needs it to tell the user the
    truth: a school that has exhausted its WEEK was being told its limit "resets tomorrow", and a
    member stopped by their own admin-set cap got a message identical to a school-wide outage.
    """
    day = day or today_il()
    units = max(0, int(units))
    conn = get_conn()
    with _LOCK, _tx(conn):
        m_day, m_week = _counts(conn, member_id, day, meter)
        p_day, p_week = _counts(conn, pool_id, day, meter)
        if member_cap < 0:
            return PoolCharge(False, p_day, p_week, "blocked")
        if member_cap > 0 and m_day + units > member_cap:
            return PoolCharge(False, p_day, p_week, "member_cap")
        # A member's share of a WEEKLY pool. The lesson pool is weekly-only, so a daily ceiling says
        # nothing about it — and without this one member could take every lesson a school gets in a
        # week, at zero cost to any per-member control, which is exactly what happened.
        if member_weekly > 0 and m_week + units > member_weekly:
            return PoolCharge(False, p_day, p_week, "member_weekly")
        if pool_daily > 0 and p_day + units > pool_daily:
            return PoolCharge(False, p_day, p_week, "day")
        if pool_weekly > 0 and p_week + units > pool_weekly:
            return PoolCharge(False, p_day, p_week, "week")
        if units:
            for who in (member_id, pool_id):
                conn.execute(
                    "INSERT INTO usage_counters (owner_id, day, meter, count) VALUES (?,?,?,?) "
                    "ON CONFLICT(owner_id, day, meter) DO UPDATE SET count = count + excluded.count",
                    (who, day, meter, units))
        return PoolCharge(True, p_day + units, p_week + units, "")


def settle_pooled(member_id: str, pool_id: str, reserved: int, actual: int,
                  day: str | None = None, meter: str = TOKENS) -> None:
    """Correct a pooled reservation to what was actually spent, on both counters together.

    The pool identity must be the one resolved at RESERVATION time and carried through — resolving
    it again here would settle against whatever the member's situation is now, and a member removed
    between reserve and settle would leave the school's reservation permanently unreleased. The async
    paths make that window minutes long, not milliseconds.
    """
    delta = int(actual) - int(reserved)
    if not delta:
        return
    day = day or today_il()
    conn = get_conn()
    with _LOCK, _tx(conn):
        for who in (member_id, pool_id):
            row = conn.execute(
                "SELECT count FROM usage_counters WHERE owner_id=? AND day=? AND meter=?",
                (who, day, meter)).fetchone()
            # A MISSING row means there is nothing to settle: bump_pooled always creates both rows,
            # so its absence means something removed them — an account purged, or a school closed,
            # while the turn was still running. Re-creating it would resurrect the deleted person's
            # id inside the counter key, undoing an erasure that had already completed, and would
            # leave a school that no longer exists with counters no route can ever read or delete.
            if row is None:
                continue
            conn.execute(
                "UPDATE usage_counters SET count=? WHERE owner_id=? AND day=? AND meter=?",
                (max(0, int(row["count"]) + delta), who, day, meter))


def settle_usage(owner_id: str, reserved: int, actual: int, day: str | None = None,
                 meter: str = TOKENS) -> int:
    """Replace a reservation with what was actually spent. Returns the day total afterwards.

    A quota is checked before generation but the true cost is only known after, so a turn is admitted
    against an estimate and corrected here. The delta may be negative (the estimate was generous,
    which is the normal case); the counter is floored at zero so a bad estimate can never mint
    allowance out of an earlier charge.
    """
    day = day or today_il()
    delta = int(actual) - int(reserved)
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute(
            "SELECT count FROM usage_counters WHERE owner_id=? AND day=? AND meter=?",
            (owner_id, day, meter)).fetchone()
        current = int(row["count"]) if row else 0
        new = max(0, current + delta)
        conn.execute(
            "INSERT INTO usage_counters (owner_id, day, meter, count) VALUES (?,?,?,?) "
            "ON CONFLICT(owner_id, day, meter) DO UPDATE SET count = excluded.count",
            (owner_id, day, meter, new))
        return new


def usage_today(owner_id: str, day: str | None = None, meter: str = TOKENS) -> int:
    """Today's total for one meter (0 if none) — for the /me readout."""
    day = day or today_il()
    conn = get_conn()
    with _LOCK:
        return _counts(conn, owner_id, day, meter)[0]


def usage_this_week(owner_id: str, day: str | None = None, meter: str = TOKENS) -> int:
    """This week's total for one meter (Sunday-start), summed from the daily rows."""
    conn = get_conn()
    with _LOCK:
        return _counts(conn, owner_id, day or today_il(), meter)[1]


# ── Account deletion (scheduled, with a grace period) ─────────────────────────
def schedule_deletion(owner_id: str, requested_at: str, scheduled_for: str) -> None:
    """Mark an account for deletion at `scheduled_for` (idempotent upsert)."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT INTO accounts (owner_id, deletion_requested_at, deletion_scheduled_for) "
            "VALUES (?,?,?) ON CONFLICT(owner_id) DO UPDATE SET "
            "deletion_requested_at=excluded.deletion_requested_at, "
            "deletion_scheduled_for=excluded.deletion_scheduled_for",
            (owner_id, requested_at, scheduled_for))


def cancel_deletion(owner_id: str) -> None:
    """Undo a pending deletion — the account stays active."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "UPDATE accounts SET deletion_requested_at=NULL, deletion_scheduled_for=NULL "
            "WHERE owner_id=?", (owner_id,))


def get_account(owner_id: str) -> dict[str, Any] | None:
    """The account's lifecycle row, or None if the owner has no account row yet."""
    conn = get_conn()
    with _LOCK:
        row = conn.execute(
            "SELECT owner_id, deletion_requested_at, deletion_scheduled_for, plan FROM accounts "
            "WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


def get_plan(owner_id: str) -> str:
    """The owner's subscription plan ('free' if they have no account row yet)."""
    conn = get_conn()
    with _LOCK:
        row = conn.execute("SELECT plan FROM accounts WHERE owner_id=?", (owner_id,)).fetchone()
    return row["plan"] if row else "free"


def set_plan(owner_id: str, plan: str) -> None:
    """Set the owner's plan — the single write a billing webhook makes on a subscription change.
    Provider-agnostic: whichever processor is chosen, its 'subscription active/cancelled' event maps
    to plan='paid'/'free' here."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT INTO accounts (owner_id, plan) VALUES (?,?) "
            "ON CONFLICT(owner_id) DO UPDATE SET plan=excluded.plan", (owner_id, plan))


# ── Credits ───────────────────────────────────────────────────────────────────
def get_credits(owner_id: str) -> int:
    conn = get_conn()
    with _LOCK:
        row = conn.execute("SELECT credits FROM accounts WHERE owner_id=?", (owner_id,)).fetchone()
    return int(row["credits"]) if row else 0


def add_credits(owner_id: str, amount: int) -> int:
    """Grant credits and return the new balance."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT INTO accounts (owner_id, credits) VALUES (?,?) "
            "ON CONFLICT(owner_id) DO UPDATE SET credits = credits + excluded.credits",
            (owner_id, int(amount)))
        row = conn.execute("SELECT credits FROM accounts WHERE owner_id=?", (owner_id,)).fetchone()
    return int(row["credits"]) if row else 0


def spend_credits(owner_id: str, amount: int) -> tuple[bool, int]:
    """Atomically spend `amount` credits. Returns (spent, balance_after).

    The balance check and the decrement are one transaction under the shared lock, so two concurrent
    generations cannot both pass on the same last credit. A caller that gets False must not generate.
    """
    amount = max(0, int(amount))
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute("SELECT credits FROM accounts WHERE owner_id=?", (owner_id,)).fetchone()
        have = int(row["credits"]) if row else 0
        if amount == 0:
            return True, have
        if have < amount:
            return False, have
        conn.execute("UPDATE accounts SET credits = credits - ? WHERE owner_id=?", (amount, owner_id))
        return True, have - amount


# ── Coupons ───────────────────────────────────────────────────────────────────
def create_coupon(code: str, *, kind: str, created_at: str, plan: str | None = None,
                  days: int | None = None, credits: int | None = None,
                  max_redemptions: int = 1, expires_at: str | None = None,
                  note: str = "") -> bool:
    """Insert a coupon. Returns False if the code already exists (never silently overwrites one that
    may already have been handed out)."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        exists = conn.execute("SELECT 1 FROM coupons WHERE code=?", (code,)).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO coupons (code, kind, plan, days, credits, max_redemptions, redeemed_count,"
            " expires_at, active, note, created_at) VALUES (?,?,?,?,?,?,0,?,1,?,?)",
            (code, kind, plan, days, credits, int(max_redemptions), expires_at, note, created_at))
        return True


def get_coupon(code: str) -> dict[str, Any] | None:
    conn = get_conn()
    with _LOCK:
        row = conn.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
    return dict(row) if row else None


def list_coupons() -> list[dict[str, Any]]:
    conn = get_conn()
    with _LOCK:
        rows = conn.execute("SELECT * FROM coupons ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def set_coupon_active(code: str, active: bool) -> bool:
    """Revoke (or restore) a code. Returns True if the code exists. Already-granted benefits stay —
    revoking stops future redemptions, it does not claw back."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        cur = conn.execute("UPDATE coupons SET active=? WHERE code=?", (int(active), code))
        return cur.rowcount > 0


def delete_coupon(code: str) -> bool:
    """Drop a coupon row outright. Returns True if a row was removed.

    Only safe for a code with NO redemptions — `coupon_redemptions` records who was granted what and
    references the code, so deleting a used one would leave that history pointing at nothing. The
    caller (admin_delete_coupon) checks redeemed_count and falls back to set_coupon_active(False);
    the guard is repeated here so a future caller can't quietly lose the audit trail.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        used = conn.execute("SELECT 1 FROM coupon_redemptions WHERE code=? LIMIT 1",
                            (code,)).fetchone()
        if used:
            return False
        return conn.execute("DELETE FROM coupons WHERE code=?", (code,)).rowcount > 0


def list_redemptions(code: str | None = None) -> list[dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM coupon_redemptions"
    args: tuple = ()
    if code:
        sql += " WHERE code=?"
        args = (code,)
    with _LOCK:
        rows = conn.execute(sql + " ORDER BY redeemed_at DESC", args).fetchall()
    return [dict(r) for r in rows]


def redeem_coupon(code: str, owner_id: str, now_iso: str, granted: str, *,
                  set_plan_to: str | None = None, period_end: str | None = None,
                  add_credits_amount: int = 0) -> str:
    """Validate a coupon and apply its benefit — all in ONE transaction.

    Returns "ok" | "not_found" | "inactive" | "expired" | "exhausted" | "already_redeemed".

    Eligibility, the redemption row, the counter bump AND the grant commit together or not at all.
    Splitting them would mean a failure between "reserved" and "granted" burns the code and gives the
    user nothing — the one outcome a coupon must never produce. It also makes the last use of a
    single-use code impossible to hand to two concurrent requests.

    The caller decides WHAT to grant (which tier, how long) — see app/coupons.py; this decides
    whether the grant is allowed to happen and writes it.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
        if row is None:
            return "not_found"
        c = dict(row)
        if not c["active"]:
            return "inactive"
        if c["expires_at"] and c["expires_at"] <= now_iso:
            return "expired"
        already = conn.execute(
            "SELECT 1 FROM coupon_redemptions WHERE code=? AND owner_id=?", (code, owner_id)).fetchone()
        if already:
            return "already_redeemed"
        cap = int(c["max_redemptions"] or 0)
        if cap > 0 and int(c["redeemed_count"]) >= cap:
            return "exhausted"

        conn.execute(
            "INSERT INTO coupon_redemptions (code, owner_id, redeemed_at, granted) VALUES (?,?,?,?)",
            (code, owner_id, now_iso, granted))
        conn.execute("UPDATE coupons SET redeemed_count = redeemed_count + 1 WHERE code=?", (code,))

        if add_credits_amount:
            conn.execute(
                "INSERT INTO accounts (owner_id, credits) VALUES (?,?) "
                "ON CONFLICT(owner_id) DO UPDATE SET credits = credits + excluded.credits",
                (owner_id, int(add_credits_amount)))
        if set_plan_to:
            conn.execute(
                "INSERT INTO accounts (owner_id, plan) VALUES (?,?) "
                "ON CONFLICT(owner_id) DO UPDATE SET plan=excluded.plan", (owner_id, set_plan_to))
            # status='canceled' + cancel_at_period_end=1 is how a non-renewing grant is spelled here,
            # and it is exactly what the existing downgrade sweep already looks for — so a coupon
            # plan lapses on its own with no new expiry machinery.
            conn.execute(
                "INSERT INTO subscriptions (owner_id, provider, provider_ref, status, "
                "current_period_end, cancel_at_period_end, updated_at, plan, cycle) "
                "VALUES (?,?,?,?,?,1,?,?,'coupon') "
                "ON CONFLICT(owner_id) DO UPDATE SET provider=excluded.provider, "
                "provider_ref=excluded.provider_ref, status=excluded.status, "
                "current_period_end=excluded.current_period_end, cancel_at_period_end=1, "
                "updated_at=excluded.updated_at, plan=excluded.plan, cycle=excluded.cycle",
                (owner_id, "coupon", code, "canceled", period_end, now_iso, set_plan_to))
        return "ok"


# ── Blocklist ─────────────────────────────────────────────────────────────────
def ban_account(owner_id: str, banned_at: str, banned_until: str | None, reason: str = "") -> None:
    """Block an account. banned_until=None ⇒ permanent; otherwise the ISO ts the block lifts."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT INTO account_bans (owner_id, banned_at, banned_until, reason) VALUES (?,?,?,?) "
            "ON CONFLICT(owner_id) DO UPDATE SET banned_at=excluded.banned_at, "
            "banned_until=excluded.banned_until, reason=excluded.reason",
            (owner_id, banned_at, banned_until, reason))


def unban_account(owner_id: str) -> bool:
    """Lift a block. Returns True if a block existed."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        cur = conn.execute("DELETE FROM account_bans WHERE owner_id=?", (owner_id,))
    return cur.rowcount > 0


def get_ban(owner_id: str) -> dict[str, Any] | None:
    """The raw block row for an owner (regardless of expiry), or None."""
    conn = get_conn()
    with _LOCK:
        row = conn.execute(
            "SELECT owner_id, banned_at, banned_until, reason FROM account_bans WHERE owner_id=?",
            (owner_id,)).fetchone()
    return dict(row) if row else None


def list_bans() -> list[dict[str, Any]]:
    """All block rows (for the admin CLI)."""
    conn = get_conn()
    with _LOCK:
        rows = conn.execute(
            "SELECT owner_id, banned_at, banned_until, reason FROM account_bans "
            "ORDER BY banned_at DESC").fetchall()
    return [dict(r) for r in rows]


# ── Subscriptions (billing) ───────────────────────────────────────────────────
def upsert_subscription(owner_id: str, *, provider: str | None = None, provider_ref: str | None = None,
                        status: str | None = None, current_period_end: str | None = None,
                        cancel_at_period_end: bool | None = None, updated_at: str,
                        plan: str | None = None, cycle: str | None = None) -> None:
    """Create or update an owner's subscription row. A passed field is written; None means "leave as-is"
    (merged over the current row), so a webhook can update just status+period without clobbering the
    stored provider_ref. Read-merge-write under the lock keeps concurrent webhooks consistent.

    The merge MUST cover every column, not just the ones this function takes as parameters. It is an
    INSERT OR REPLACE, and REPLACE deletes the row before inserting — so any column left out of the
    read reverts to its schema default. Three coupon columns were omitted, and the effect was that a
    ₪49 rebate granted to a paying customer was wiped by the very charge it was meant to reduce
    (handle_event upserts BEFORE it reads the balance), and a coupon boost's revert_at was erased so
    the sweep that ends a boost could never select the row again. Money owed and never returned, with
    nothing logged. If you add a column to this table, add it here.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute(
            "SELECT provider, provider_ref, status, current_period_end, cancel_at_period_end, "
            "plan, cycle, coupon_discount_ils, coupon_revert_plan, coupon_revert_at "
            "FROM subscriptions WHERE owner_id=?", (owner_id,)).fetchone()
        cur = dict(row) if row else {
            "provider": None, "provider_ref": None, "status": "none",
            "current_period_end": None, "cancel_at_period_end": 0, "plan": None, "cycle": "monthly",
            "coupon_discount_ils": 0.0, "coupon_revert_plan": None, "coupon_revert_at": None}
        conn.execute(
            "INSERT OR REPLACE INTO subscriptions (owner_id, provider, provider_ref, status, "
            "current_period_end, cancel_at_period_end, updated_at, plan, cycle, "
            "coupon_discount_ils, coupon_revert_plan, coupon_revert_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (owner_id,
             provider if provider is not None else cur["provider"],
             provider_ref if provider_ref is not None else cur["provider_ref"],
             status if status is not None else cur["status"],
             current_period_end if current_period_end is not None else cur["current_period_end"],
             cur["cancel_at_period_end"] if cancel_at_period_end is None else int(cancel_at_period_end),
             updated_at,
             plan if plan is not None else cur["plan"],
             cycle if cycle is not None else (cur["cycle"] or "monthly"),
             cur["coupon_discount_ils"] or 0.0,
             cur["coupon_revert_plan"],
             cur["coupon_revert_at"]))


def get_subscription(owner_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    with _LOCK:
        row = conn.execute(
            "SELECT owner_id, provider, provider_ref, status, current_period_end, "
            "cancel_at_period_end, updated_at, plan, cycle, "
            "coupon_discount_ils, coupon_revert_plan, coupon_revert_at "
            "FROM subscriptions WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


def add_coupon_discount(owner_id: str, amount_ils: float, *, updated_at: str) -> None:
    """Add to the account's rebate balance (existing balance stacks, same spirit as same-tier plan
    coupons stacking elsewhere). Creates the subscriptions row if the account had none."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT INTO subscriptions (owner_id, coupon_discount_ils, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(owner_id) DO UPDATE SET "
            "coupon_discount_ils = coupon_discount_ils + excluded.coupon_discount_ils, "
            "updated_at = excluded.updated_at",
            (owner_id, amount_ils, updated_at))


def set_coupon_discount(owner_id: str, amount_ils: float) -> None:
    """Overwrite the rebate balance to an explicit value (used to shrink it after a rebate)."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute("UPDATE subscriptions SET coupon_discount_ils=? WHERE owner_id=?",
                     (amount_ils, owner_id))


def set_coupon_boost(owner_id: str, *, revert_plan: str, revert_at: str, updated_at: str) -> None:
    """Record what a coupon-boosted account should revert to and when. Does not itself change
    `plan` — the caller flips the account's plan separately via set_plan()."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "INSERT INTO subscriptions (owner_id, coupon_revert_plan, coupon_revert_at, updated_at) "
            "VALUES (?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET "
            "coupon_revert_plan = excluded.coupon_revert_plan, "
            "coupon_revert_at = excluded.coupon_revert_at, updated_at = excluded.updated_at",
            (owner_id, revert_plan, revert_at, updated_at))


def due_coupon_reverts(now_iso: str) -> list[dict[str, Any]]:
    """Accounts whose coupon-driven plan boost has ended — the billing sweep flips their plan back
    to what they actually pay for."""
    conn = get_conn()
    with _LOCK:
        rows = conn.execute(
            "SELECT owner_id, coupon_revert_plan AS revert_plan FROM subscriptions "
            "WHERE coupon_revert_at IS NOT NULL AND coupon_revert_at <= ?", (now_iso,)).fetchall()
    return [dict(r) for r in rows]


def clear_coupon_revert(owner_id: str, *, updated_at: str) -> None:
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute(
            "UPDATE subscriptions SET coupon_revert_plan=NULL, coupon_revert_at=NULL, "
            "updated_at=? WHERE owner_id=?", (updated_at, owner_id))


def due_downgrades(now_iso: str) -> list[str]:
    """Owners whose CANCELLED subscription's paid period has now ended — the billing sweep flips these
    back to the free plan (they keep paid access until the period they already paid for lapses)."""
    conn = get_conn()
    with _LOCK:
        rows = conn.execute(
            "SELECT owner_id FROM subscriptions WHERE status='canceled' "
            "AND current_period_end IS NOT NULL AND current_period_end <= ?", (now_iso,)).fetchall()
    return [r["owner_id"] for r in rows]


def due_deletions(now_iso: str) -> list[str]:
    """Owner ids whose scheduled deletion time has arrived (scheduled_for <= now)."""
    conn = get_conn()
    with _LOCK:
        rows = conn.execute(
            "SELECT owner_id FROM accounts WHERE deletion_scheduled_for IS NOT NULL "
            "AND deletion_scheduled_for <= ?", (now_iso,)).fetchall()
    return [r["owner_id"] for r in rows]


class OwnsOrganisation(Exception):
    """This account owns a live organisation, so it cannot be deleted yet."""


# Stands in for a purged account wherever a NOT NULL column named one. Never a real owner id:
# Supabase ids are UUIDs and the offline single-user id is 'local'.
DELETED_OWNER = "deleted-account"


def _like_literal(value: str) -> str:
    r"""Escape a value that is being spliced into a LIKE PATTERN rather than compared to one.

    Parameter binding stops SQL injection; it does NOT stop `%` and `_` inside the bound value from
    acting as wildcards. Callers pair this with ESCAPE '\'.
    """
    return value.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")


def owns_org(owner_id: str) -> bool:
    """Does this account own (pay for, administer) an organisation?"""
    with _LOCK:
        return get_conn().execute(
            "SELECT 1 FROM orgs WHERE owner_id=? LIMIT 1", (owner_id,)).fetchone() is not None


def purge_owner(owner_id: str) -> None:
    """Irreversibly delete ALL of an owner's data: sessions (messages cascade), saved lessons, usage
    counters, and the account row itself. Used by the deletion sweeper once the grace period lapses.
    Guarded against the shared single-user 'local' id so a misconfigured call can't wipe local dev.

    Raises OwnsOrganisation if the account still owns a school. `orgs.owner_id` is the only link
    between an institution and the person who paid for it, so purging them would leave a live org
    pointing at a dead account: the members keep spending a pool nobody can administer, and nothing
    anywhere would error. The sweeper logs and skips (run_due_purges catches per row), and
    /account/delete refuses up front so the user hears about it instead of the deletion silently
    never happening.
    """
    if owner_id == "local":
        return
    conn = get_conn()
    if owns_org(owner_id):
        raise OwnsOrganisation(owner_id)
    with _LOCK, _tx(conn):
        conn.execute("DELETE FROM sessions WHERE owner_id=?", (owner_id,))         # messages cascade
        conn.execute("DELETE FROM saved_lessons WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM usage_counters WHERE owner_id=?", (owner_id,))
        # A member's school spending is counted under `org:<org_id>:<owner_id>` (orgs.member_meter_id),
        # which an exact-match delete misses — so the account id survived erasure inside a composite
        # key, joined to a per-day record of how much that person studied. Introduced by the very
        # change that separated the two counters; the identifier has to go with the account.
        #
        # ESCAPE, because the id goes into a LIKE PATTERN: `_` and `%` inside it would be wildcards.
        # In API-key mode every owner id begins `u_` (security._owner_from_key), so this is already
        # true today — it happens to be harmless because the rest is a SHA-256 prefix no other
        # account can match. That is a property of the current auth provider, not of the query.
        conn.execute(r"DELETE FROM usage_counters WHERE owner_id LIKE 'org:%:' || ? ESCAPE '\'",
                     (_like_literal(owner_id),))
        conn.execute("DELETE FROM subscriptions WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM accounts WHERE owner_id=?", (owner_id,))
        # Coupon redemptions too. Keeping them would leave a user identifier behind after an account
        # deletion, and it buys nothing: the cap is enforced by coupons.redeemed_count, which is
        # never decremented, so a spent code stays spent whether or not this row survives. (Nor
        # would keeping it stop re-redemption — a re-registered person gets a new owner_id anyway.)
        conn.execute("DELETE FROM coupon_redemptions WHERE owner_id=?", (owner_id,))
        # Things the person WROTE, under their own id. Both were missed while every measurement table
        # around them was handled: feedback holds their free text, and a message_report holds their id
        # against a message that cascade-deletes with the session — so the report was not only kept
        # but became invisible to the operator's own review screen, which inner-joins messages.
        # Retained data that nothing can see is data nothing will ever clean up.
        conn.execute("DELETE FROM feedback WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM message_reports WHERE owner_id=?", (owner_id,))
        # School membership goes with the account. The seat must be freed too — leaving the row would
        # hold a seat for someone who no longer exists, and a 20-seat school would slowly run out of
        # room it is still paying for.
        conn.execute("DELETE FROM org_members WHERE owner_id=?", (owner_id,))
        # Telemetry is anonymised rather than deleted: the rows carry no content, only measurements,
        # and dropping them would silently rewrite history for every aggregate that has already been
        # reported. Detaching the identity satisfies the deletion request; the counts stay true.
        conn.execute("UPDATE usage_events SET owner_id=NULL WHERE owner_id=?", (owner_id,))
        # Same treatment for the org audit trail and invite provenance: both name a person but carry
        # no content of theirs. Deleting the log outright would let a departing administrator erase
        # the record of what they looked at, which is the one thing that trail exists to prevent.
        # A sentinel rather than NULL — those columns are NOT NULL, and "the account was deleted"
        # is a truer reading of the row than "unknown".
        conn.execute("UPDATE org_access_log SET actor_owner_id=? WHERE actor_owner_id=?",
                     (DELETED_OWNER, owner_id))
        conn.execute("UPDATE org_access_log SET target_owner_id=? WHERE target_owner_id=?",
                     (DELETED_OWNER, owner_id))
        # Their live codes die with the account, as they would on removal — otherwise a teacher who
        # deletes their account leaves multi-use class codes behind, attributed to nobody, for as
        # long as the expiry allows.
        conn.execute("UPDATE org_invites SET revoked_at=?, created_by=? WHERE created_by=? "
                     "AND revoked_at IS NULL", (_now(), DELETED_OWNER, owner_id))
        conn.execute("UPDATE org_invites SET created_by=? WHERE created_by=?",
                     (DELETED_OWNER, owner_id))
        # invited_by is the same kind of residue one statement up: a teacher who deletes their
        # account was still named on the row of every student they ever admitted.
        conn.execute("UPDATE org_members SET invited_by=? WHERE invited_by=?",
                     (DELETED_OWNER, owner_id))
        # Dev-helper enrolment and the notices sent to them. Unlike guard_findings — which carries no
        # owner_id precisely so it needs nothing here — both of these are ABOUT a person: one records
        # that they agreed to test, the other holds messages addressed to them. Deleted outright, not
        # anonymised: there is no aggregate anyone reports from them that de-identifying would keep
        # true, so keeping the rows would buy nothing and retain an identifier.
        conn.execute("DELETE FROM dev_helpers WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM helper_messages WHERE owner_id=?", (owner_id,))
        # …and the operator's own trace on notices they sent, if it is the OPERATOR being deleted.
        conn.execute("UPDATE helper_messages SET sent_by=? WHERE sent_by=?",
                     (DELETED_OWNER, owner_id))
        conn.execute("UPDATE dev_helpers SET added_by=? WHERE added_by=?",
                     (DELETED_OWNER, owner_id))


# ── Calendar cache (Parshat HaShavua / Daf Yomi) ───────────────────────────────
# Sefaria's /api/calendars is resolved lazily (on first request of the day/week, not a scheduled
# job) and cached here so it's called at most once per bucket, not once per request. Not owner-
# scoped — the parsha/daf is the same for everyone, so one row serves every account.

def get_calendar_cache(kind: str, date_key: str) -> str | None:
    with _LOCK:
        r = get_conn().execute(
            "SELECT payload FROM calendar_cache WHERE kind=? AND date_key=?",
            (kind, date_key)).fetchone()
    return r["payload"] if r else None


def set_calendar_cache(kind: str, date_key: str, payload: str) -> None:
    with _tx(get_conn()) as conn:
        conn.execute(
            "INSERT INTO calendar_cache (kind, date_key, payload, resolved_at) VALUES (?,?,?,?) "
            "ON CONFLICT(kind, date_key) DO UPDATE SET payload=excluded.payload, "
            "resolved_at=excluded.resolved_at",
            (kind, date_key, payload, _now()))
