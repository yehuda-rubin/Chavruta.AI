"""Chavruta.AI — SQLite persistence for chat sessions and messages."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Location of the chat-history store. Configurable via CHAVRUTA_DB_PATH so the
# container can point it at a mounted volume (persists all conversations across
# restarts); defaults to the repo root for local dev.
DB_PATH = Path(
    os.environ.get("CHAVRUTA_DB_PATH", Path(__file__).resolve().parent.parent / "chavruta.db")
)


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
SCHEMA_VERSION = 10


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
            owner_id     TEXT NOT NULL DEFAULT 'local'  -- who this belongs to; 'local' = single-user
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
            created_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, id);

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
            owner_id    TEXT NOT NULL DEFAULT 'local'  -- who this belongs to; 'local' = single-user
        );
        CREATE INDEX IF NOT EXISTS idx_saved_lessons_time ON saved_lessons(created_at DESC);

        -- Per-owner daily usage counter — the free-tier quota (public hosting). One row per
        -- (owner, UTC day); the generation endpoints bump it and reject over the configured limit.
        -- Persisted (not in-memory) so a restart can't reset a user's daily allowance.
        CREATE TABLE IF NOT EXISTS usage_counters (
            owner_id  TEXT NOT NULL,
            day       TEXT NOT NULL,          -- UTC date, YYYY-MM-DD
            count     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (owner_id, day)
        );

        -- Account lifecycle — currently just scheduled deletion. A user can request deletion; it's
        -- carried out after a grace period (during which they can cancel), so an accidental or
        -- coerced click is recoverable. NULL scheduled_for = no pending deletion.
        CREATE TABLE IF NOT EXISTS accounts (
            owner_id               TEXT PRIMARY KEY,
            deletion_requested_at  TEXT,      -- ISO ts when the user asked to delete (NULL = not asked)
            deletion_scheduled_for TEXT,      -- ISO ts when the purge runs (NULL = nothing scheduled)
            plan                   TEXT NOT NULL DEFAULT 'free'   -- 'free' | 'paid'; flipped by billing
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
        # Only this owner's sessions. Order by last activity so a conversation you return to bubbles
        # to the top; fall back to created_at for rows that predate updated_at.
        rows = get_conn().execute(
            """SELECT id, first_q, created_at, updated_at, mode
               FROM sessions
               WHERE owner_id=?
               ORDER BY COALESCE(updated_at, created_at) DESC
               LIMIT 100""",
            (owner_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(sid: str, owner_id: str = "local") -> bool:
    with _tx(get_conn()) as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id=? AND owner_id=?", (sid, owner_id))
    return cur.rowcount > 0


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
) -> int:
    now = _now()
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            """INSERT INTO messages
               (session_id, role, text, intent, citations, caveats, grounded, files, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                role,
                text,
                intent,
                json.dumps(citations, ensure_ascii=False) if citations is not None else None,
                json.dumps(caveats, ensure_ascii=False) if caveats is not None else None,
                int(grounded) if grounded is not None else None,
                json.dumps(files, ensure_ascii=False) if files else None,
                now,
            ),
        )
        # Touch the parent session so it sorts to the top of the chat list.
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
    return cur.lastrowid


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
        out.append(d)
    return out


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


def delete_lesson(lesson_id: str, owner_id: str = "local") -> bool:
    conn = get_conn()
    with _LOCK, _tx(conn):
        cur = conn.execute(
            "DELETE FROM saved_lessons WHERE id=? AND owner_id=?", (lesson_id, owner_id))
    return cur.rowcount > 0


def _now() -> str:
    return datetime.now(UTC).isoformat()


def today_utc() -> str:
    """The current UTC date as YYYY-MM-DD — the bucket a daily quota counts against."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def bump_usage(owner_id: str, limit: int, day: str | None = None) -> tuple[bool, int]:
    """Atomically account one generation for `owner_id` today and enforce the free-tier quota.

    Returns (allowed, count). With limit <= 0 the quota is OFF: always allowed, still counted (so
    usage is observable). With limit > 0, if the day's count already reached the limit we do NOT
    increment and return (False, count) — the caller turns that into a 429. The read-and-increment
    runs under the shared lock in one transaction, so two concurrent requests can't both slip past
    the limit."""
    day = day or today_utc()
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute(
            "SELECT count FROM usage_counters WHERE owner_id=? AND day=?", (owner_id, day)).fetchone()
        current = row["count"] if row else 0
        if limit > 0 and current >= limit:
            return False, current
        conn.execute(
            "INSERT INTO usage_counters (owner_id, day, count) VALUES (?,?,1) "
            "ON CONFLICT(owner_id, day) DO UPDATE SET count = count + 1",
            (owner_id, day))
        return True, current + 1


def usage_today(owner_id: str, day: str | None = None) -> int:
    """Today's generation count for `owner_id` (0 if none) — for the /me quota readout."""
    day = day or today_utc()
    conn = get_conn()
    with _LOCK:
        row = conn.execute(
            "SELECT count FROM usage_counters WHERE owner_id=? AND day=?", (owner_id, day)).fetchone()
    return row["count"] if row else 0


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


def due_deletions(now_iso: str) -> list[str]:
    """Owner ids whose scheduled deletion time has arrived (scheduled_for <= now)."""
    conn = get_conn()
    with _LOCK:
        rows = conn.execute(
            "SELECT owner_id FROM accounts WHERE deletion_scheduled_for IS NOT NULL "
            "AND deletion_scheduled_for <= ?", (now_iso,)).fetchall()
    return [r["owner_id"] for r in rows]


def purge_owner(owner_id: str) -> None:
    """Irreversibly delete ALL of an owner's data: sessions (messages cascade), saved lessons, usage
    counters, and the account row itself. Used by the deletion sweeper once the grace period lapses.
    Guarded against the shared single-user 'local' id so a misconfigured call can't wipe local dev."""
    if owner_id == "local":
        return
    conn = get_conn()
    with _LOCK, _tx(conn):
        conn.execute("DELETE FROM sessions WHERE owner_id=?", (owner_id,))         # messages cascade
        conn.execute("DELETE FROM saved_lessons WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM usage_counters WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM accounts WHERE owner_id=?", (owner_id,))
