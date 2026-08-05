"""expand_range() — a Sefaria range ref ('Genesis 1:1-6:8', or a Haftarah's 'Isaiah 54:11-55:5')
to the flat list of verse refs fetch_by_refs needs, since it has no native range support."""

from __future__ import annotations

import chavruta.corpus.refs as refs
import pytest
import requests
from chavruta.corpus.refs import expand_range


@pytest.fixture(autouse=True)
def _clear_shape_cache():
    refs._SHAPE_CACHE.clear()
    yield
    refs._SHAPE_CACHE.clear()


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


def test_malformed_range_returns_empty():
    assert expand_range("not a range") == []
    assert expand_range("") == []
    assert expand_range("Genesis 1:1") == []          # no end chapter:verse


def test_chapter_out_of_bounds_returns_empty():
    assert expand_range("Genesis 1:1-51:1") == []      # Genesis only has 50 chapters


# A Haftarah is a range in Nevi'im (Isaiah, Jeremiah, one of the 12 minor prophets, ...) — not one
# of the 5 Chumash books the static table covers. expand_range falls back to Sefaria's /api/shape,
# fetched once per book and cached in-memory for the rest of the process.
def test_haftarah_book_resolved_via_sefaria_shape_fallback(monkeypatch):
    calls = []

    def _fake_get(url, *a, **k):
        calls.append(url)
        r = requests_mock_response([{"chapters": [11, 26, 15, 24, 6]}])   # toy 5-chapter "book"
        return r

    monkeypatch.setattr(requests, "get", _fake_get)
    out = expand_range("Isaiah 1:1-1:3")
    assert out == ["Isaiah.1.1", "Isaiah.1.2", "Isaiah.1.3"]
    assert len(calls) == 1
    assert "Isaiah" in calls[0]


def test_haftarah_shape_fallback_is_cached_after_first_fetch(monkeypatch):
    calls = []

    def _fake_get(url, *a, **k):
        calls.append(url)
        return requests_mock_response([{"chapters": [11, 26, 15, 24, 6]}])

    monkeypatch.setattr(requests, "get", _fake_get)
    expand_range("Isaiah 1:1-1:3")
    expand_range("Isaiah 2:1-2:2")
    assert len(calls) == 1   # second call reused the cached chapter lengths, no second fetch


def test_unknown_book_returns_empty_when_the_sefaria_fallback_also_fails(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    assert expand_range("NotARealBook 1:1-1:5") == []


def requests_mock_response(json_body):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return json_body

    return _Resp()
