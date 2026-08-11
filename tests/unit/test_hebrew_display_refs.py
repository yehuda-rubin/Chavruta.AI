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
