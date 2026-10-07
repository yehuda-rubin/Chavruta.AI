"""The library catalogue (src/chavruta/corpus/data/catalog.json): Hebrew-first and commercial-only."""
import json
import re
from collections import Counter
from pathlib import Path

from chavruta.corpus import rights

_DATA = Path(__file__).resolve().parents[2] / "src" / "chavruta" / "corpus" / "data"
_HEB = re.compile(r"[֐-׿]")
_CAT = json.loads((_DATA / "catalog.json").read_text(encoding="utf-8"))


def test_every_book_has_a_hebrew_title_without_latin_letters():
    bad = [b["title_en"] for b in _CAT["books"]
           if not _HEB.search(b["title_he"]) or re.search("[A-Za-z]", b["title_he"])]
    assert not bad, bad[:10]


def test_hebrew_titles_are_unique():
    dups = [t for t, n in Counter(b["title_he"] for b in _CAT["books"]).items() if n > 1]
    assert not dups, dups[:10]


def test_every_book_is_commercially_licensed_and_has_an_entry_ref():
    for b in _CAT["books"]:
        assert rights.allows_commercial_use(b["license"]), b["title_en"]
        assert b["first_ref"] and " " not in b["first_ref"], b["title_en"]


def test_every_category_on_a_books_path_has_a_hebrew_name():
    for b in _CAT["books"]:
        parts = b["path"].split("/")
        for i in range(1, len(parts) + 1):
            cat = _CAT["categories"].get("/".join(parts[:i]))
            assert cat and _HEB.search(cat["he"]), (b["title_en"], "/".join(parts[:i]))
