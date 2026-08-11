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


# ── Sources the agentic loop fetched must render like any other ──────────────────
# They arrive as SourceBlock, not RankedHit. SourceBlock used to carry only marker/ref/
# commentator_id/text, so a self-fetched source fell back to the combined Hebrew+English blob and
# had no licence — and with ~75% of requests reaching a second retrieval round, that was most
# sources on most sheets (reported 2026-08-12).

def test_source_block_carries_the_reader_facing_fields():
    from chavruta.llm.base import SourceBlock

    sb = SourceBlock(marker="S1", ref="Bava_Metzia.3.1", commentator_id=None,
                     text="[header]\nעברית\nEnglish translation",
                     text_he="עברית", text_en="English translation",
                     license="CC-BY-SA", version_title="Wikisource Talmud Bavli",
                     deep_link="https://www.sefaria.org/Bava_Metzia.3.1")
    # The sheet builder reads these off the hit via getattr — the same call path for both types.
    assert getattr(sb, "text_he", "") == "עברית"
    assert getattr(sb, "license", "") == "CC-BY-SA"
    assert getattr(sb, "version_title", "") == "Wikisource Talmud Bavli"


def test_self_fetched_source_renders_hebrew_only_with_its_licence():
    from chavruta.llm.base import SourceBlock

    sb = SourceBlock(marker="S1", ref="Bava_Metzia.3.1", commentator_id=None,
                     text="[בבא מציעא] Bava Metzia 3:1\nמתני׳ שנים אוחזין\nTwo men are holding",
                     text_he="מתני׳ שנים אוחזין", text_en="Two men are holding",
                     license="Public Domain", version_title="Vilna Edition")
    cit = CitationOut(ref=sb.ref, ref_he="בבא מציעא 2.",
                      text_he=sb.text_he, text_en=sb.text_en, commentator="",
                      deep_link=sb.deep_link, license=sb.license, version_title=sb.version_title)
    assert "Two men are holding" not in _source_sheet_entry(1, cit)
    assert "רישיון לא ידוע" not in _license_table([cit], he=True)
    assert "נחלת הכלל" in _license_table([cit], he=True)
