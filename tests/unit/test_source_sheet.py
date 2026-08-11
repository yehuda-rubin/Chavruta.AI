"""The lesson source sheet — what actually gets printed and handed to a class.

Both bugs here were reported from a real sheet (2026-08-11): every source appeared twice, once in
Hebrew and once in English, and no source said what licence it carried.
"""

from __future__ import annotations

from app.api import _license_table, _source_sheet_entry
from app.api import CitationOut


def _cit(**kw) -> CitationOut:
    base = dict(ref="Bava_Metzia.3.1", ref_he="בבא מציעא 2.", text_he="מתני׳ שנים אוחזין בטלית",
                text_en="Two men are holding onto a garment.", commentator="", deep_link="",
                license="Public Domain", version_title="Vilna Edition")
    return CitationOut(**{**base, **kw})


def test_hebrew_sheet_does_not_print_the_english_translation():
    """`text` in the corpus is the indexed blob — header line + Hebrew + English concatenated.
    Building the sheet from it printed each source in both languages."""
    entry = _source_sheet_entry(1, _cit())
    assert "מתני׳ שנים אוחזין בטלית" in entry
    assert "Two men are holding" not in entry


def test_english_is_used_when_the_source_has_no_hebrew():
    """Several responsa exist in the corpus only as English translations — those must still show."""
    entry = _source_sheet_entry(1, _cit(text_he="", text_en="Only an English translation exists."))
    assert "Only an English translation exists." in entry


def test_license_table_lists_every_source_not_only_the_ones_demanding_credit():
    """The per-source credit line fires only where a licence legally requires attribution, which is
    almost never — Public Domain and CC0 dominate the corpus. Without this table a reader has no way
    to tell what any of the text is or whether they may reproduce it."""
    used = [_cit(), _cit(ref="X.1.1", ref_he="מקור ב", license="CC-BY-SA", version_title="Wikisource")]
    table = _license_table(used, he=True)
    assert "בבא מציעא 2." in table and "מקור ב" in table
    assert "נחלת הכלל" in table          # Public Domain, rendered for a reader
    assert "CC-BY-SA" in table
    assert "Vilna Edition" in table and "Wikisource" in table


def test_license_table_is_numbered_to_match_the_sheet():
    used = [_cit(ref_he="ראשון"), _cit(ref_he="שני"), _cit(ref_he="שלישי")]
    lines = _license_table(used, he=True).splitlines()[1:]
    assert [ln.split(".")[0] for ln in lines] == ["1", "2", "3"]


def test_unknown_license_is_named_rather_than_left_blank():
    table = _license_table([_cit(license="", version_title="")], he=True)
    assert "רישיון לא ידוע" in table


def test_empty_selection_yields_no_table():
    assert _license_table([], he=True) == ""
