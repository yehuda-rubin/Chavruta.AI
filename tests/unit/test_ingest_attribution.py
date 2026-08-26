"""payload_from_legacy_meta silently dropped license/version/deep_link/anchor_ref (found 2026-08-21).

Real production bug: 85 CC-BY-SA sources (115,519 chunks — 77% of them all of Talmud Bavli) were
already live with license="" because this function never read license_he/version_he from the
metadata at all, even though every fetch notebook (Sefaria and Wikisource alike) populated them.
Chunk defaulted to "", so SourcesPanel.tsx's Attribution component had nothing to render and
rights.requires_attribution("") silently read as "no attribution owed" — a real ShareAlike
violation sitting in production. Same bug also built deep_link as a Sefaria URL unconditionally
(a dead link for any non-Sefaria source) and derived anchor_ref self-referentially even when the
metadata already carried a real one (e.g. a Wikisource commentary anchored to Shulchan Arukh).

See docs/CORPUS_SOURCES_CANDIDATES.md §9 for the full writeup.
"""
from __future__ import annotations

from chavruta.corpus.ingest import payload_from_legacy_meta


def _meta(**md) -> dict:
    return {"id": "x1", "document": "טקסט לדוגמה", "metadata": md}


def test_a_legacy_record_with_no_new_fields_behaves_exactly_as_before():
    """No license_he/version_he/deep_link/anchor_ref at all — every existing tier's shape."""
    p = payload_from_legacy_meta(_meta(verse_id="Genesis.1.1"))
    assert p["license"] == ""
    assert p["version_title"] == ""
    assert p["deep_link"] == "https://www.sefaria.org/Genesis.1.1"
    assert p["anchor_ref"] is None


def test_license_and_version_are_read_from_metadata_when_present():
    p = payload_from_legacy_meta(_meta(verse_id="Genesis.1.1",
                                       license_he="CC-BY-SA", version_he="ויקיטקסט"))
    assert p["license"] == "CC-BY-SA"
    assert p["version_title"] == "ויקיטקסט"


def test_english_license_and_version_are_a_fallback_behind_the_hebrew_ones():
    p = payload_from_legacy_meta(_meta(verse_id="Genesis.1.1",
                                       license_en="CC0", version_en="Wikisource"))
    assert p["license"] == "CC0"
    assert p["version_title"] == "Wikisource"


def test_an_explicit_deep_link_wins_over_the_derived_sefaria_url():
    """The bug: a Wikisource ref got turned into a dead sefaria.org/<ref> link unconditionally."""
    p = payload_from_legacy_meta(_meta(
        verse_id="Wikisource_wikisource_kook:אורות התשובה א#0.0",
        deep_link="https://he.wikisource.org/wiki/%D7%90%D7%95%D7%A8%D7%95%D7%AA",
    ))
    assert p["deep_link"] == "https://he.wikisource.org/wiki/%D7%90%D7%95%D7%A8%D7%95%D7%AA"


def test_no_deep_link_in_metadata_still_falls_back_to_the_derived_sefaria_url():
    p = payload_from_legacy_meta(_meta(verse_id="Genesis.1.1"))
    assert p["deep_link"] == "https://www.sefaria.org/Genesis.1.1"


def test_an_explicit_anchor_ref_wins_over_the_derived_self_reference():
    """The Mishnah Berurah case: a real commentary anchored to the Shulchan Arukh it explains,
    not to itself."""
    p = payload_from_legacy_meta(_meta(
        verse_id="Mishnah_Berurah.448.1", commentator="Mishnah Berurah",
        anchor_ref="Shulchan Arukh, Orach Chayim.448",
    ))
    assert p["anchor_ref"] == "Shulchan Arukh, Orach Chayim.448"
    assert p["anchor_kind"] == "source"


def test_commentary_with_no_explicit_anchor_ref_still_derives_the_old_self_reference():
    """Existing tiers never carry anchor_ref in metadata — must fall through unchanged."""
    p = payload_from_legacy_meta(_meta(verse_id="Genesis.1.1", commentator="Rashi"))
    assert p["anchor_ref"] == "Genesis.1.1"
