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


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           TEXT PRIMARY KEY,
            first_q      TEXT NOT NULL,
            created_at   TEXT NOT NULL
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
            created_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, id);
    """)
    conn.commit()

    # Seed default sessions and messages if database is brand new
    cursor = conn.execute("SELECT COUNT(*) FROM sessions")
    if cursor.fetchone()[0] == 0:
        now_dt = datetime.now(timezone.utc)
        
        # Seed sessions
        sid_1 = "shenayim-ochazin"
        sid_2 = "session-2"
        sid_3 = "session-3"
        sid_4 = "session-4"
        
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at) VALUES (?,?,?)",
            (sid_1, "סוגיית שניים אוחזין", now_dt.isoformat())
        )
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at) VALUES (?,?,?)",
            (sid_2, "דיני שומרים - בבא מציעא", (now_dt - timedelta(minutes=10)).isoformat())
        )
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at) VALUES (?,?,?)",
            (sid_3, 'מצוות תלמוד תורה לרמב"ם', (now_dt - timedelta(minutes=20)).isoformat())
        )
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at) VALUES (?,?,?)",
            (sid_4, "קניין חצר וארבע אמות", (now_dt - timedelta(minutes=30)).isoformat())
        )

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
            "INSERT INTO sessions (id, first_q, created_at) VALUES (?,?,?)",
            (sid, first_q, now),
        )
    return sid


def list_sessions() -> list[dict[str, Any]]:
    with _LOCK:
        rows = get_conn().execute(
            "SELECT id, first_q, created_at FROM sessions ORDER BY created_at DESC LIMIT 100"
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
) -> int:
    with _tx(get_conn()) as conn:
        cur = conn.execute(
            """INSERT INTO messages
               (session_id, role, text, intent, citations, caveats, grounded, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                session_id,
                role,
                text,
                intent,
                json.dumps(citations, ensure_ascii=False) if citations is not None else None,
                json.dumps(caveats, ensure_ascii=False) if caveats is not None else None,
                int(grounded) if grounded is not None else None,
                _now(),
            ),
        )
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
        out.append(d)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
