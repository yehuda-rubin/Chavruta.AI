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
SCHEMA_VERSION = 16


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
            note          TEXT
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
            cycle                TEXT NOT NULL DEFAULT 'monthly' -- monthly | annual
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


def record_charge(*, charged_at: str, amount: float, currency: str = "ILS", plan: str | None = None,
                  cycle: str | None = None, provider: str | None = None,
                  provider_ref: str | None = None, invoice_ref: str | None = None,
                  note: str = "") -> int:
    """Append a charge to the accounting ledger. Returns the row id.

    Append-only and deliberately anonymous — see the table comment. Called on every successful
    payment, INCLUDING renewals, so the ledger is a complete record of revenue rather than a list of
    subscriptions that happen to still exist.
    """
    conn = get_conn()
    with _LOCK, _tx(conn):
        cur = conn.execute(
            "INSERT INTO billing_ledger (charged_at, amount, currency, plan, cycle, provider, "
            "provider_ref, invoice_ref, note) VALUES (?,?,?,?,?,?,?,?,?)",
            (charged_at, float(amount), currency, plan, cycle, provider, provider_ref,
             invoice_ref, note))
        return int(cur.lastrowid)


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


def today_utc() -> str:
    """The current UTC date as YYYY-MM-DD — the bucket a daily quota counts against."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def week_days(day: str | None = None) -> list[str]:
    """The seven YYYY-MM-DD dates of `day`'s week, Sunday first.

    Sunday-start because the product is Israeli and that is the week a user here means. A calendar
    week (rather than a rolling 7 days) is what the UI can state plainly — "resets Sunday" — and a
    predictable reset matters more here than closing the small boundary burst, which the daily cap
    bounds anyway.
    """
    d = datetime.strptime(day or today_utc(), "%Y-%m-%d").replace(tzinfo=UTC)
    sunday = d - timedelta(days=(d.weekday() + 1) % 7)      # Python: Monday==0, so Sunday==6
    return [(sunday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


TOKENS, LESSON = "tokens", "lesson"


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
    day = day or today_utc()
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


def settle_usage(owner_id: str, reserved: int, actual: int, day: str | None = None,
                 meter: str = TOKENS) -> int:
    """Replace a reservation with what was actually spent. Returns the day total afterwards.

    A quota is checked before generation but the true cost is only known after, so a turn is admitted
    against an estimate and corrected here. The delta may be negative (the estimate was generous,
    which is the normal case); the counter is floored at zero so a bad estimate can never mint
    allowance out of an earlier charge.
    """
    day = day or today_utc()
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
    day = day or today_utc()
    conn = get_conn()
    with _LOCK:
        return _counts(conn, owner_id, day, meter)[0]


def usage_this_week(owner_id: str, day: str | None = None, meter: str = TOKENS) -> int:
    """This week's total for one meter (Sunday-start), summed from the daily rows."""
    conn = get_conn()
    with _LOCK:
        return _counts(conn, owner_id, day or today_utc(), meter)[1]


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
    stored provider_ref. Read-merge-write under the lock keeps concurrent webhooks consistent."""
    conn = get_conn()
    with _LOCK, _tx(conn):
        row = conn.execute(
            "SELECT provider, provider_ref, status, current_period_end, cancel_at_period_end, "
            "plan, cycle FROM subscriptions WHERE owner_id=?", (owner_id,)).fetchone()
        cur = dict(row) if row else {
            "provider": None, "provider_ref": None, "status": "none",
            "current_period_end": None, "cancel_at_period_end": 0, "plan": None, "cycle": "monthly"}
        conn.execute(
            "INSERT OR REPLACE INTO subscriptions (owner_id, provider, provider_ref, status, "
            "current_period_end, cancel_at_period_end, updated_at, plan, cycle) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (owner_id,
             provider if provider is not None else cur["provider"],
             provider_ref if provider_ref is not None else cur["provider_ref"],
             status if status is not None else cur["status"],
             current_period_end if current_period_end is not None else cur["current_period_end"],
             cur["cancel_at_period_end"] if cancel_at_period_end is None else int(cancel_at_period_end),
             updated_at,
             plan if plan is not None else cur["plan"],
             cycle if cycle is not None else (cur["cycle"] or "monthly")))


def get_subscription(owner_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    with _LOCK:
        row = conn.execute(
            "SELECT owner_id, provider, provider_ref, status, current_period_end, "
            "cancel_at_period_end, updated_at, plan, cycle "
            "FROM subscriptions WHERE owner_id=?", (owner_id,)).fetchone()
    return dict(row) if row else None


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
        conn.execute("DELETE FROM subscriptions WHERE owner_id=?", (owner_id,))
        conn.execute("DELETE FROM accounts WHERE owner_id=?", (owner_id,))
        # Coupon redemptions too. Keeping them would leave a user identifier behind after an account
        # deletion, and it buys nothing: the cap is enforced by coupons.redeemed_count, which is
        # never decremented, so a spent code stays spent whether or not this row survives. (Nor
        # would keeping it stop re-redemption — a re-registered person gets a new owner_id anyway.)
        conn.execute("DELETE FROM coupon_redemptions WHERE owner_id=?", (owner_id,))
