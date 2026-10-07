"""/reader/toc (a book's chapters or dapim) and the `book` filter of /search/query, on a tiny reader DB."""
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ROWS = [  # (chunk_id, ref, book, work_id, search_he)
    ("Genesis.1.1_tanakh", "Genesis 1:1", "Genesis", "tanakh", "בראשית ברא"),
    ("Genesis.1.2_tanakh", "Genesis 1:2", "Genesis", "tanakh", "והארץ היתה"),
    ("Genesis.2.1_tanakh", "Genesis 2:1", "Genesis", "tanakh", "ויכלו השמים"),
    ("Genesis_Rabbah.1.1_midrash", "Genesis Rabbah 1:1", "Genesis Rabbah", "midrash", "בראשית ברא"),
    ("Berakhot.3.1_gemara", "Berakhot 3:1", "Berakhot", "gemara", "מאימתי קורין"),
    ("Berakhot.4.1_gemara", "Berakhot 4:1", "Berakhot", "gemara", "תנא היכא"),
    ("Berakhot.5.1_gemara", "Berakhot 5:1", "Berakhot", "gemara", "ברא"),
    ("Chizkuni,_Genesis.1.1.1_tanakh", "Chizkuni, Genesis 1:1:1", "Chizkuni", "tanakh", "בראשית ברא"),
    ("Chizkuni,_Exodus.2.1.1_tanakh", "Chizkuni, Exodus 2:1:1", "Chizkuni", "tanakh", "ויהי"),
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "search_index.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE chunks (rowid INTEGER PRIMARY KEY, chunk_id TEXT, ref TEXT, book TEXT,
                   author_he TEXT, work_id TEXT, category_path TEXT, text_he TEXT, text_en TEXT,
                   license_he TEXT, license_en TEXT, version_he TEXT, version_en TEXT,
                   canon_order INTEGER, sort_title TEXT)""")
    con.execute("CREATE VIRTUAL TABLE search_fts USING fts5(search_he, search_en)")
    for i, (cid, ref, book, wid, he) in enumerate(ROWS, 1):
        con.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (i, cid, ref, book, "", wid, "", he, None, "", None, "", None, 0, book))
        con.execute("INSERT INTO search_fts(rowid, search_he, search_en) VALUES (?,?,?)", (i, he, ""))
    con.commit()
    con.close()
    monkeypatch.setenv("SEARCH_DB_PATH", str(db))
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module("app.search_service")
    mod._db_connection = None
    mod._toc_cache.clear()
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


def units(client, book):
    r = client.get("/reader/toc", params={"book": book})
    assert r.status_code == 200, r.text
    return r.json()


def test_chapters_of_a_book_and_no_bleed_into_a_sibling_title(client):
    d = units(client, "Genesis")
    assert d["kind"] == "chapter"
    assert [(u["ref"], u["count"]) for u in d["units"]] == [("Genesis.1", 2), ("Genesis.2", 1)]


def test_bavli_amud_linear_refs_become_dapim(client):
    d = units(client, "Berakhot")
    assert d["kind"] == "daf"
    assert [u["ref"] for u in d["units"]] == ["Berakhot.2a", "Berakhot.2b", "Berakhot.3a"]


def test_sections_recorded_before_the_number(client):
    d = units(client, "Chizkuni")
    assert [(u["section"], u["ref"]) for u in d["units"]] == [("Exodus", "Chizkuni,_Exodus.2"),
                                                              ("Genesis", "Chizkuni,_Genesis.1")]


def test_unknown_book_is_404(client):
    assert client.get("/reader/toc", params={"book": "Nope"}).status_code == 404


def test_content_search_inside_one_book(client):
    everywhere = client.get("/search/query", params={"q": "בראשית"}).json()
    inside = client.get("/search/query", params={"q": "בראשית", "book": "Genesis"}).json()
    assert everywhere["total"] >= 3
    assert inside["total"] == 1 and inside["hits"][0]["book"] == "Genesis"
    assert set(inside["facets"]) == {"tanakh"}
