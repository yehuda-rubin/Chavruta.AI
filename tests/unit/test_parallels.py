"""Corpus-derived parallels for the reader's 'קשרים ומקבילות' tab."""
import sqlite3

import pytest

import app.search_service as svc


@pytest.fixture()
def db(monkeypatch):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE chunks (rowid INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE, ref TEXT, book TEXT, author_he TEXT,
            work_id TEXT, category_path TEXT, search_he TEXT, text_he TEXT, text_en TEXT);
        CREATE VIRTUAL TABLE search_fts USING fts5(search_he, search_en, content='', tokenize='unicode61');
        """
    )
    text = "המוציא שני נימין מזנב הסוס ומזנב הפרה הרי זה חייב מפני שמתקינין לכשפים"
    rows = [
        ("Tosefta_Shabbat.10.1_t", "Tosefta Shabbat 10:1", "Tosefta Shabbat", "Tosefta / Vilna Edition / Seder Moed", text),
        ("Shabbat.11.1_b", "Shabbat 11:1", "Shabbat", "Talmud / Bavli / Seder Moed", text + " ועוד דברים"),
        ("Rashi_on_Shabbat.11.1.1_r", "Rashi on Shabbat 11:1:1", "Rashi on Shabbat", "Talmud / Bavli / Rishonim on Talmud / Rashi", text),
        ("Genesis.1.1_g", "Genesis 1:1", "Genesis", "Tanakh / Torah", text),
        ("Other.1.1_o", "Other 1:1", "Other", "Midrash / Aggadah", "דבר אחר לגמרי שאין בו שום דבר משותף עם הקטע"),
    ]
    for i, (cid, ref, book, cp, t) in enumerate(rows, 1):
        c.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?)", (i, cid, ref, book, "", "w", cp, t, t, None))
        c.execute("INSERT INTO search_fts(rowid, search_he, search_en) VALUES (?,?,?)", (i, t, ""))
    monkeypatch.setattr(svc, "get_db", lambda: c)
    svc._parallels_cache.clear()
    return c


def test_parallel_is_found_across_works(db):
    got = svc._parallels("Tosefta Shabbat 10:1")
    assert [g.ref for g in got] == ["Shabbat 11:1"]


def test_commentary_tanakh_and_unrelated_are_excluded(db):
    refs = {g.ref for g in svc._parallels("Tosefta Shabbat 10:1")}
    assert not refs & {"Rashi on Shabbat 11:1:1", "Genesis 1:1", "Other 1:1"}


def test_tanakh_base_gets_no_parallels(db):
    assert svc._parallels("Genesis 1:1") == []
