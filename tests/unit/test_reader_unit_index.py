"""The reader's unit lookup must use an index (2026-10-26: a LIKE-based OR scanned all 5.9 GB of
`chunks` on every page and timed out) and must select exactly the rows the LIKE form did."""

import sqlite3

import app.search_service as s

_REFS = [
    "Genesis 1:1", "Genesis 1:2", "Genesis 10:1", "Genesis 11:3", "Genesis 2:1",
    "Genesis.1.1", "Genesis_1_1", "Bava_Metzia.3.1", "Bava Metzia 2a:1", "Bava Metzia 2b:4",
    "Rashi_on_Genesis.1.1.1", "Shulchan_Arukh,_Orach_Chayim.263.1", "Exodus 1:1",
]


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE chunks (rowid INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE NOT NULL, "
               "ref TEXT NOT NULL)")
    db.execute("CREATE INDEX idx_ref ON chunks(ref)")
    db.executemany("INSERT INTO chunks (chunk_id, ref) VALUES (?, ?)",
                   [(f"c{i}:{r}", r) for i, r in enumerate(_REFS)])
    return db


def _like_where(clean_ref: str):
    """The pre-2026-10-26 form, kept here only as the reference result."""
    clauses, params = [], []
    for p in s.get_unit_query_prefixes(clean_ref):
        pattern = f"{s.like_escape(p)}%"
        clauses += ["ref LIKE ? ESCAPE '\\'", "chunk_id LIKE ? ESCAPE '\\'"]
        params += [pattern, pattern]
    clauses += ["ref = ?", "chunk_id = ?"]
    params += [clean_ref, clean_ref]
    return " OR ".join(clauses), params


def _rows(db, where, params):
    return [r[0] for r in db.execute(f"SELECT ref FROM chunks WHERE {where} ORDER BY rowid", params)]


def test_range_form_selects_the_same_rows_as_like():
    db = _db()
    for unit in ["Genesis 1", "Genesis.1", "Genesis 10", "Bava Metzia 2a", "Bava_Metzia 3",
                 "Shulchan_Arukh,_Orach_Chayim 263", "Genesis 1:1", "Exodus 1"]:
        assert _rows(db, *s._unit_where(unit)) == _rows(db, *_like_where(unit)), unit


def test_unit_lookup_does_not_scan_the_table():
    db = _db()
    where, params = s._unit_where("Genesis 1")
    plan = " ".join(r[3] for r in db.execute(
        f"EXPLAIN QUERY PLAN SELECT rowid FROM chunks WHERE {where} ORDER BY rowid LIMIT 500", params))
    assert "SCAN chunks" not in plan, plan
    assert "idx_ref" in plan


def test_prefix_upper_bound():
    assert s._prefix_upper_bound("Genesis 1:") == "Genesis 1;"
    assert "Genesis 1:9" < s._prefix_upper_bound("Genesis 1:")
    assert not ("Genesis 1:" <= "Genesis 10:1" < s._prefix_upper_bound("Genesis 1:"))
