"""Tests for Hebrew display ref rendering (corpus/refs.py::hebrew_display_ref)."""

from __future__ import annotations

import pytest

from chavruta.corpus.refs import hebrew_display_ref


# ── Regression locks: existing curated cases must remain unchanged ────────────────

@pytest.mark.parametrize("ref,expected", [
    ("Genesis.1.1", "בראשית 1:1"),
    ("Bava_Metzia.3.1", "בבא מציעא 2."),  # daf 2a — amud-linear N converted back
    ("Rashi_on_Genesis.1.1.1", "רש\"י על בראשית 1:1"),
    ("Bartenura_on_Mishnah_Bava_Metzia.1.1.1", "ברטנורא על משנה בבא מציעא 1:1"),
])
def test_regression_curated_cases(ref, expected):
    """Existing curated table cases must return exactly what they returned before."""
    assert hebrew_display_ref(ref) == expected


# ── New functionality: previously-untranslated refs now get Hebrew ───────────────

@pytest.mark.parametrize("ref", [
    "Shulchan_Arukh,_Orach_Chayim.310.1",
    "Mishneh_Torah,_Sabbath.6.1",
    "B'Mareh_HaBazak_Volume_V.49.6",
])
def test_previously_untranslated_now_hebrew(ref):
    """A ref that previously fell back to English now returns a Hebrew string."""
    result = hebrew_display_ref(ref)
    assert result is not None
    # The result must contain no Latin letters (only Hebrew, digits, and punctuation)
    assert not any("a" <= c.lower() <= "z" for c in result if c.isalpha())


# ── Unknown titles still return None ─────────────────────────────────────────────

@pytest.mark.parametrize("ref", [
    "Totally_Made_Up_Book.1.1",
    "Nonexistent_Work.5.3",
])
def test_unknown_title_returns_none(ref):
    """A genuinely unknown title still returns None."""
    assert hebrew_display_ref(ref) is None


# ── Edge cases: None/empty input ─────────────────────────────────────────────────

@pytest.mark.parametrize("ref", [None, "", "   "])
def test_none_empty_input(ref):
    """hebrew_display_ref returns None for None/empty input."""
    assert hebrew_display_ref(ref) is None


# ── JSON-map path must NOT apply daf math ───────────────────────────────────────

def test_json_map_no_daf_math():
    """When a title is resolved via the JSON map, numeric segments pass through unchanged.
    Shulchan Arukh.310.1 should display as '310:1', NOT converted via daf math."""
    result = hebrew_display_ref("Shulchan_Arukh,_Orach_Chayim.310.1")
    assert result is not None
    # The numbers should appear as-is (310:1), not daf-converted
    assert "310:1" in result


# ── Commentaries the curated table never covered ─────────────────────────────────
# These are the refs real halacha answers cite constantly (Shulchan Arukh's own meforshim). Every
# one of them rendered in English before the Sefaria title map was wired in.

@pytest.mark.parametrize("ref,expected", [
    ("Turei_Zahav_on_Shulchan_Arukh,_Orach_Chayim.310.1", "טורי זהב על שולחן ערוך אורח חיים 310:1"),
    ("Kaf_HaChayim_on_Shulchan_Arukh,_Orach_Chayim.308.45.1", "כף החיים על שולחן ערוך אורח חיים 308:45:1"),
    ("Beur_HaGra_on_Shulchan_Arukh,_Orach_Chayim.308.45.1", "ביאור הגר\"א על שולחן ערוך אורח חיים 308:45:1"),
])
def test_shulchan_arukh_commentaries_render_in_hebrew(ref, expected):
    assert hebrew_display_ref(ref) == expected


# ── Talmud safety: the generic title path must never render a daf ────────────────
# The corpus stores Bavli amud-linearly, so only `_split_book`'s conversion produces a correct daf.
# A Talmud commentary by a commentator missing from COMMENTATOR_HE must therefore still go through
# the curated path (its Hebrew name derived from Sefaria's own commentary titles) — never through
# the generic path, which would print the raw amud-linear N as if it were a daf number.

@pytest.mark.parametrize("ref,expected", [
    ("Rashash_on_Gittin.61.3", "רש\"ש על גיטין 31."),      # N=61 → daf 31a, NOT '61:3'
    ("Ritva_on_Avodah_Zarah.56.1", "ריטב\"א על עבודה זרה 28:"),
])
def test_talmud_commentary_keeps_daf_conversion(ref, expected):
    assert hebrew_display_ref(ref) == expected


def test_talmud_title_never_falls_through_to_raw_numbers():
    """Whatever a Talmud ref renders as, it must never be the raw amud-linear N joined with ':'."""
    for ref, raw in [("Rashash_on_Gittin.61.3", "61:3"), ("Bava_Metzia.3.1", "3:1")]:
        out = hebrew_display_ref(ref)
        assert out is None or raw not in out


# ── Yerushalmi: same Sefaria category as Bavli, different storage ────────────────
# The amud-linear conversion is a property of Talmud BAVLI in this corpus. Sefaria files the
# Yerushalmi under "Talmud" too, so refusing the whole category left every Jerusalem Talmud source
# rendered in English on the source sheet (reported 2026-08-12 from a real lesson).

@pytest.mark.parametrize("ref,expected", [
    ("Jerusalem_Talmud_Bava_Metzia.1.1.1", "תלמוד ירושלמי בבא מציעא 1:1:1"),
    ("Penei_Moshe_on_Jerusalem_Talmud_Bava_Metzia.1.1.1.1",
     "פני משה על תלמוד ירושלמי בבא מציעא 1:1:1:1"),
])
def test_yerushalmi_renders_in_hebrew_without_daf_math(ref, expected):
    assert hebrew_display_ref(ref) == expected


def test_bavli_still_gets_its_daf_conversion():
    """The guard must stay in place for the corner it was built for."""
    assert hebrew_display_ref("Bava_Metzia.3.1") == "בבא מציעא 2."
    assert hebrew_display_ref("Rashi_on_Bava_Metzia.3.1.1") == 'רש"י על בבא מציעא 2.'


# ── The comma (reported 2026-08-14) ──────────────────────────────────────────
# 758 of 1336 citations in production reached a Hebrew reader as a raw English underscored ref.
# The cause was not missing data: Sefaria keys a work by its own title and then names the book or
# parasha after a comma IN THE REF, so looking the whole string up found nothing — while the title
# sat in the map all along. None of the affected works are obscure; Chizkuni is printed in every
# chumash.
@pytest.mark.parametrize("ref,expected", [
    ("Chizkuni,_Genesis.17.5.2", "חזקוני, בראשית 17:5:2"),
    ("Siftei_Chakhamim,_Numbers.27.14.1", "שפתי חכמים, במדבר 27:14:1"),
    ("Birkat_Asher_on_Torah,_Deuteronomy.18.11.2", "ברכת אשר על התורה, דברים 18:11:2"),
])
def test_a_work_named_before_a_comma_still_resolves(ref, expected):
    assert hebrew_display_ref(ref) == expected


@pytest.mark.parametrize("ref,starts", [
    ("Yismach_Moshe,_Vaetchanan.2.3", "ישמח משה"),
    ("Shem_MiShmuel,_Chukat.3.19", "שם משמואל"),
    ("Nishmat_Chayyim,_Second_Treatise.9.2", "נשמת חיים"),
])
def test_a_segment_with_no_hebrew_keeps_its_english_rather_than_losing_the_whole_name(ref, starts):
    """Parasha and structural segments ("Vaetchanan", "Part I") have no entry, book names do. A
    partly-Hebrew label still names the work in the reader's own alphabet, which is the part they
    recognise — refusing the whole thing served nobody."""
    out = hebrew_display_ref(ref)
    assert out and out.startswith(starts)


@pytest.mark.parametrize("ref,expected", [
    ("Malbim_on_I_Chronicles.1.27.1", 'מלבי"ם על דברי הימים א 1:27'),
    ("Rashi_on_Genesis.1.1.1", 'רש"י על בראשית 1:1'),
    ("Bava_Metzia.3.1", "בבא מציעא 2."),          # the amud-linear daf math must be untouched
    ("Shulchan_Arukh,_Orach_Chayim.248.4", "שולחן ערוך, אורח חיים 248:4"),
])
def test_the_refs_that_already_worked_are_unchanged(ref, expected):
    assert hebrew_display_ref(ref) == expected
