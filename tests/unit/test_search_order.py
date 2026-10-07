"""Content search is ordered the way a learner meets the sources: Tanakh, Chazal, then commentators by
their own era (a Rishon with the Rishonim, an Acharon with the Acharonim) — not alphabetically."""
import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RANKS = json.loads((ROOT / "src" / "chavruta" / "corpus" / "data" / "layer_rank.json").read_text(encoding="utf-8"))

# (book, category_path) inserted in a deliberately scrambled order; every row contains the same word.
ROWS = [
    ("Malbim", "Tanakh / Acharonim on Tanakh / Malbim / Torah"),
    ("Rashi on Genesis", "Tanakh / Rishonim on Tanakh / Rashi / Torah"),
    ("Shulchan Arukh", "Halakhah / Shulchan Arukh"),
    ("Berakhot", "Talmud / Bavli / Seder Zeraim"),
    ("Isaiah", "Tanakh / Prophets"),
    ("Mishnah Berakhot", "Mishnah / Seder Zeraim"),
    ("Genesis", "Tanakh / Torah"),
    ("Psalms", "Tanakh / Writings"),
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
    for i, (book, path) in enumerate(ROWS, 1):
        con.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (i, f"{book}.1.1_x", f"{book} 1:1", book, "", "x", path, "ברא", None, "", None, "", None, 0, book))
        con.execute("INSERT INTO search_fts(rowid, search_he, search_en) VALUES (?,?,?)", (i, "ברא", ""))
    con.commit()
    con.close()
    monkeypatch.setenv("SEARCH_DB_PATH", str(db))
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module("app.search_service")
    mod._db_connection = None
    from fastapi.testclient import TestClient
    return TestClient(mod.app)


def test_every_row_path_is_ranked():
    for _, path in ROWS:
        assert path in RANKS, path


def test_learning_order(client):
    hits = client.get("/search/query", params={"q": "ברא"}).json()["hits"]
    assert [h["book"] for h in hits] == [
        "Genesis", "Isaiah", "Psalms",            # Torah, Prophets, Writings
        "Mishnah Berakhot", "Berakhot",           # then the Oral Torah
        "Rashi on Genesis",                       # a Rishon — after the Gemara, with the Rishonim
        "Malbim",                                 # an Acharon — with the Acharonim, after the Rishonim
        "Shulchan Arukh",
    ]


def test_a_rishon_commentary_precedes_an_acharon_one_whatever_they_comment_on():
    assert RANKS["Tanakh / Rishonim on Tanakh / Rashi / Torah"] < RANKS["Tanakh / Acharonim on Tanakh / Malbim / Torah"]
    assert RANKS["Mishnah / Seder Zeraim"] < RANKS["Tanakh / Rishonim on Tanakh / Rashi / Torah"]
