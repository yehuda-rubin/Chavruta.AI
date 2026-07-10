"""RefIndex — on-disk (SQLite) resolver from a canonical ref to the ORIGINAL corpus chunk refs.

Built by scripts/build_link_index.py (table ``refidx(canon, chunk_ref, is_anchor)``). The link
graph is keyed by canonical refs (corpus.refs.canonical_ref); to fetch the actual chunks a neighbour
denotes, LinkExpander maps each canonical neighbour back to the original ref strings stored in the
vector store's payloads. Read-only, thread-safe for concurrent FastAPI request threads.
"""

from __future__ import annotations

import sqlite3
from collections import OrderedDict
from pathlib import Path


class RefIndex:
    def __init__(self, db_path: str | Path) -> None:
        self._db = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, check_same_thread=False)
        self._has_cache: "OrderedDict[str, bool]" = OrderedDict()
        self._cap = 300_000

    def has(self, canon: str) -> bool:
        """Does any corpus chunk have this canonical ref? (bounded-LRU cached membership test.)"""
        c = self._has_cache
        if canon in c:
            c.move_to_end(canon)
            return c[canon]
        v = self._db.execute("SELECT 1 FROM refidx WHERE canon=? LIMIT 1", (canon,)).fetchone() is not None
        c[canon] = v
        if len(c) > self._cap:            # evict least-recently-used, not the whole hot cache
            c.popitem(last=False)
        return v

    def originals(self, canon: str, limit: int = 8) -> list[str]:
        """The original chunk-ref strings whose canonical form is `canon` (bounded)."""
        cur = self._db.execute(
            "SELECT DISTINCT chunk_ref FROM refidx WHERE canon=? LIMIT ?", (canon, limit))
        return [r[0] for r in cur.fetchall()]

    def __len__(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM refidx").fetchone()[0]
