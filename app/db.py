# -*- coding: utf-8 -*-
"""Chavruta.AI — SQLite persistence for chat sessions and messages."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
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
SCHEMA_VERSION = 3


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
            updated_at   TEXT
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

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

    # The store starts empty by default — no demo content in the database. Set
    # CHAVRUTA_SEED_DEMO=1 to seed the showcase conversations into a brand-new DB
    # (used only for screenshots/demos); they are still seeded at most once.
    if fresh_db and os.environ.get("CHAVRUTA_SEED_DEMO", "0") == "1":
        _seed_demo(conn)


def _seed_demo(conn: sqlite3.Connection) -> None:
    """Insert demo conversations into a brand-new database (called once, ever)."""
    now_dt = datetime.now(timezone.utc)

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

def create_session(first_q: str) -> str:
    sid = str(uuid.uuid4())
    now = _now()
    with _tx(get_conn()) as conn:
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at, updated_at) VALUES (?,?,?,?)",
            (sid, first_q, now, now),
        )
    return sid


def list_sessions() -> list[dict[str, Any]]:
    with _LOCK:
        # Order by last activity so a conversation you return to bubbles to the
        # top; fall back to created_at for rows that predate updated_at.
        rows = get_conn().execute(
            """SELECT id, first_q, created_at, updated_at
               FROM sessions
               ORDER BY COALESCE(updated_at, created_at) DESC
               LIMIT 100"""
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(sid: str) -> bool:
    with _tx(get_conn()) as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
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


def get_messages(session_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
