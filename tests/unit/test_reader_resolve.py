"""/reader/resolve against a tiny reader database: only citations that exist come back."""
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "search_index.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE chunks (rowid INTEGER PRIMARY KEY, chunk_id TEXT, ref TEXT, book TEXT,
                   author_he TEXT, work_id TEXT, category_path TEXT, text_he TEXT, text_en TEXT,
                   license_he TEXT, license_en TEXT, version_he TEXT, version_en TEXT)""")
    rows = [("Genesis.1.1_tanakh", "Genesis 1:1"), ("Genesis.1.3_tanakh", "Genesis 1:3"),
            ("Berakhot.3.1_gemara", "Berakhot 2a:1")]
    for i, (cid, ref) in enumerate(rows, 1):
        con.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (i, cid, ref, ref.split()[0], "", "x", "", "טקסט", None, "", None, "", None))
    con.commit()
    con.close()
    monkeypatch.setenv("SEARCH_DB_PATH", str(db))
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module("app.search_service")
    mod._db_connection = None
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


def refs(client, q):
    r = client.get("/reader/resolve", params={"q": q})
    assert r.status_code == 200
    return [m["ref"] for m in r.json()["matches"]]


def test_verse_opens_the_chapter_at_the_verse(client):
    assert refs(client, "בראשית א ג") == ["Genesis 1:3"]


def test_chapter_only(client):
    assert refs(client, "בראשית פרק א") == ["Genesis.1"]


def test_missing_verse_falls_back_to_the_chapter(client):
    assert refs(client, "בראשית א ט") == ["Genesis.1"]


def test_unknown_chapter_is_dropped(client):
    assert refs(client, "בראשית ס") == []


def test_not_a_citation(client):
    assert refs(client, "בראשית") == []
    assert refs(client, "שלום עולם") == []


def test_reader_unit_still_works_after_the_refactor(client):
    r = client.get("/reader/unit", params={"ref": "Genesis.1"})
    assert r.status_code == 200 and len(r.json()["segments"]) >= 2
