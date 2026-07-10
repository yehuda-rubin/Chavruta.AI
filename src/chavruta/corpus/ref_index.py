"""RefIndex — on-disk (SQLite) resolver from a canonical ref to the ORIGINAL corpus chunk refs.

Built by scripts/build_link_index.py (table ``refidx(canon, chunk_ref, is_anchor)``). The link
graph is keyed by canonical refs (corpus.refs.canonical_ref); to fetch the actual chunks a neighbour
denotes, LinkExpander maps each canonical neighbour back to the original ref strings stored in the
vector store's payloads. Read-only, thread-safe for concurrent FastAPI request threads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class RefIndex:
    def __init__(self, db_path: str | Path) -> None:
        self._db = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, check_same_thread=False)

    def originals(self, canon: str, limit: int = 8) -> list[str]:
        """The original chunk-ref strings whose canonical form is `canon` (bounded)."""
        cur = self._db.execute(
            "SELECT DISTINCT chunk_ref FROM refidx WHERE canon=? LIMIT ?", (canon, limit))
        return [r[0] for r in cur.fetchall()]

    def __len__(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM refidx").fetchone()[0]
