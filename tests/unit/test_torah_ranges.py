"""expand_range() — a Sefaria parsha range ('Genesis 1:1-6:8') to the flat list of verse refs
fetch_by_refs needs, since it has no native range support."""

from __future__ import annotations

from chavruta.corpus.refs import expand_range


def test_single_chapter_range():
    assert expand_range("Genesis 1:1-1:5") == [
        "Genesis.1.1", "Genesis.1.2", "Genesis.1.3", "Genesis.1.4", "Genesis.1.5",
    ]


def test_range_crossing_a_chapter_boundary():
    # Genesis 1 has 31 verses — the tail of chapter 1, then the head of chapter 2.
    out = expand_range("Genesis 1:30-2:3")
    assert out == [
        "Genesis.1.30", "Genesis.1.31",
        "Genesis.2.1", "Genesis.2.2", "Genesis.2.3",
    ]


def test_full_parsha_range_bereshit():
    out = expand_range("Genesis 1:1-6:8")
    assert out[0] == "Genesis.1.1"
    assert out[-1] == "Genesis.6.8"
    # Genesis chapters 1-5 in full (31+25+24+26+32) + chapter 6 verses 1-8.
    assert len(out) == 31 + 25 + 24 + 26 + 32 + 8


def test_unknown_book_returns_empty():
    assert expand_range("Joshua 1:1-1:5") == []


def test_malformed_range_returns_empty():
    assert expand_range("not a range") == []
    assert expand_range("") == []
    assert expand_range("Genesis 1:1") == []          # no end chapter:verse


def test_chapter_out_of_bounds_returns_empty():
    assert expand_range("Genesis 1:1-51:1") == []      # Genesis only has 50 chapters
