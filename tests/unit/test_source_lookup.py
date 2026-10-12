"""Library source search: typed citations → reader refs (no database)."""
import json
from pathlib import Path

import pytest

from chavruta.corpus.source_lookup import SourceIndex, fold, parse

_CAT = json.loads((Path(__file__).resolve().parents[2] / "src" / "chavruta" / "corpus" / "data"
                   / "catalog.json").read_text(encoding="utf-8"))
IDX = SourceIndex(_CAT["books"])


def one(q):
    r = parse(q, IDX)
    assert len(r) == 1, (q, r)
    return r[0]


@pytest.mark.parametrize("q,unit,target", [
    ("בראשית א א", "Genesis.1", "Genesis 1:1"),
    ("בראשית פרק א", "Genesis.1", ""),
    ("בראשית פרק א פסוק ג", "Genesis.1", "Genesis 1:3"),
    ("בראשית א:ג", "Genesis.1", "Genesis 1:3"),
    ("בראשית 1 3", "Genesis.1", "Genesis 1:3"),
    ("שמות כ ב", "Exodus.20", "Exodus 20:2"),
    ("ויקרא י\"ח ו", "Leviticus.18", "Leviticus 18:6"),
    ("תהילים קיט", "Psalms.119", ""),
    ("תהלים קיט קעו", "Psalms.119", "Psalms 119:176"),
    ("שמואל א ב ג", "I_Samuel.2", "I Samuel 2:3"),
    ("משנה ברכות ב ג", "Mishnah_Berakhot.2", "Mishnah Berakhot 2:3"),
])
def test_chapter_and_verse_citations(q, unit, target):
    s = one(q)
    assert (s.ref, s.target) == (unit, target)


@pytest.mark.parametrize("q,unit", [
    ("ברכות ב ע\"א", "Berakhot.2a"),
    ("ברכות דף ב עמוד ב", "Berakhot.2b"),
    ("ברכות ב ע״ב", "Berakhot.2b"),
    ("ברכות ב", "Berakhot.2a"),
    ("בבא מציעא ב ע\"א", "Bava_Metzia.2a"),
    ("בבא מציעא קי״ד ע״ב", "Bava_Metzia.114b"),
])
def test_talmud_daf_and_amud(q, unit):
    assert one(q).ref == unit


@pytest.mark.parametrize("q", ["", "בראשית", "שלום עולם", "בראשית ברא אלהים", "xyz 1 2"])
def test_not_a_citation(q):
    assert parse(q, IDX) == []


def test_niqqud_and_final_letters_do_not_matter():
    assert one("בְּרֵאשִׁית א א").ref == "Genesis.1"
    assert fold("מלכים") == fold("מלכימ")
