"""LinkStore's on-disk SQLite path -> file: URI construction (corpus/links.py).

The DB path can come from anywhere the deployment happens to be checked out or mounted, including
a directory with a space (e.g. "C:\\Users\\John Smith\\...", a real Windows default) or (rarer) a
character that's reserved in a URI (#, ?, %). A raw f-string paste after `file:` tolerates the
common cases by accident (SQLite's URI parser is lenient about bare Windows paths), but silently
mis-resolves a path containing a URI-reserved character instead of raising — a `#` in the path was
measured connecting "successfully" to the wrong, nonexistent location, so every query against it
came back empty rather than failing loudly. `Path.as_uri()` percent-encodes properly.
"""
from __future__ import annotations

import sqlite3

from chavruta.corpus.links import LinkStore


def _make_edges_db(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE edges (from_canon TEXT, to_canon TEXT)")
    conn.execute("CREATE INDEX idx_from ON edges(from_canon)")
    conn.execute("INSERT INTO edges VALUES ('Genesis.1.1', 'Rashi_on_Genesis.1.1.1')")
    conn.commit()
    conn.close()


def test_link_store_opens_and_queries_a_plain_path(tmp_path):
    db_path = tmp_path / "links.db"
    _make_edges_db(db_path)
    store = LinkStore(db_path)
    assert store.neighbours("Genesis.1.1") == ["Rashi_on_Genesis.1.1.1"]


def test_link_store_opens_a_path_containing_a_space(tmp_path):
    """A real Windows default (`C:\\Users\\John Smith\\...`), not an exotic edge case."""
    d = tmp_path / "dir with a space"
    d.mkdir()
    db_path = d / "links.db"
    _make_edges_db(db_path)
    store = LinkStore(db_path)
    assert store.neighbours("Genesis.1.1") == ["Rashi_on_Genesis.1.1.1"]


def test_link_store_opens_a_path_containing_a_uri_reserved_character(tmp_path):
    """Regression: a raw f-string `file:{path}` URI silently mis-resolved a path containing '#' —
    it "opened" without error but against the wrong (nonexistent) location, so every real query
    against it came back empty instead of the connection failing loudly at construction time."""
    d = tmp_path / "dir#with#hash"
    d.mkdir()
    db_path = d / "links.db"
    _make_edges_db(db_path)
    store = LinkStore(db_path)
    assert store.neighbours("Genesis.1.1") == ["Rashi_on_Genesis.1.1.1"]
