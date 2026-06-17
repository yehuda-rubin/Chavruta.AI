# -*- coding: utf-8 -*-
"""Chavruta.AI — SQLite persistence for chat sessions and messages."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "chavruta.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def _tx(conn: sqlite3.Connection):
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
