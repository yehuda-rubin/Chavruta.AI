"""The ref → Sefaria index title heuristic used to backfill rights onto the live corpus.

This carries licensing decisions, so it is pinned. The cases are REAL refs read out of the running
2.93M-point collection on 2026-07-17 — not invented.

History worth keeping: the first version only handled the space form (`Rashi on Chullin 11.3.1`) and
missed the dotted form (`Prisha,_Yoreh_De'ah.335.19.1`), so every dotted ref became its own "title" —
200k chunks produced ~113k titles instead of collapsing. It looked like it worked until it was
measured.
"""

from __future__ import annotations

import pytest
from scripts.backfill_licenses import index_title_of


@pytest.mark.parametrize("ref,expected", [
    # space form, with the Hebrew display label the ingest prepends
    ('רש"י on Rashi on Chullin 11.3.1', "Rashi on Chullin"),
    ("אבן עזרא on Ibn Ezra on Leviticus 26.2.8", "Ibn Ezra on Leviticus"),
    ("תוספות on Tosafot on Berakhot 68.30.1", "Tosafot on Berakhot"),
    ("ברטנורא on Bartenura on Mishnah Zevachim 13.6.1", "Bartenura on Mishnah Zevachim"),
    # dotted form (underscores for spaces) — the shape the first version silently failed on
    ("Prisha,_Yoreh_De'ah.335.19.1", "Prisha, Yoreh De'ah"),
    ("Mishneh_Torah,_Forbidden_Foods.11.18", "Mishneh Torah, Forbidden Foods"),
    ("Sulam_on_Zohar,_Vayechi.482.2", "Sulam on Zohar, Vayechi"),
    ("Zohar,_Addenda,_Volume_II.6.22", "Zohar, Addenda, Volume II"),
    ("Variants_on_Kiddushin.5.2.20", "Variants on Kiddushin"),
    # plain
    ("Berakhot 2a.3", "Berakhot"),
    ("Genesis 1.3", "Genesis"),
    # the two titles whose real licences (CC-BY-NC / bare copyright) triggered this whole workstream
    ("Peninei Halakhah, Berakhot 2.1.5", "Peninei Halakhah, Berakhot"),
    ("Steinsaltz on Mishneh Torah, Foundations of the Torah 6.1.2",
     "Steinsaltz on Mishneh Torah, Foundations of the Torah"),
])
def test_index_title_extracted(ref, expected):
    assert index_title_of(ref) == expected


@pytest.mark.parametrize("ref", ["", "   ", None])
def test_empty_ref_is_empty_not_an_exception(ref):
    assert index_title_of(ref) == ""


def test_dotted_and_space_forms_collapse_to_the_same_title():
    """The corpus stores both shapes; they must not become two different titles — that is exactly
    the bug that made the title count explode."""
    assert index_title_of("Berakhot 2a.3") == index_title_of("Berakhot.2a.3") == "Berakhot"


def test_title_without_a_locator_is_left_alone():
    assert index_title_of("Genesis") == "Genesis"
