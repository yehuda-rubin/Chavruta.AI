"""Talmud daf-shift correction (corpus.talmud_ref)."""

from __future__ import annotations

import pytest

from chavruta.corpus.talmud_ref import daf_component, shift_daf


@pytest.mark.parametrize("ref,expected", [
    ("Bava Metzia.3a.1", "Bava Metzia.2a.1"),          # the שניים אוחזין mishnah
    ("Bava Metzia.3b.14", "Bava Metzia.2b.14"),        # amud b preserved
    ("Bava Metzia.4a.1", "Bava Metzia.3a.1"),
    ("Bava Metzia.120a.5", "Bava Metzia.119a.5"),      # last daf
    ("Berakhot.3a", "Berakhot.2a"),                    # no segment
    ("Rashi on Bava Metzia.3a.1", "Rashi on Bava Metzia.2a.1"),     # commentary prefix
    ("Tosafot on Berakhot.3b.4", "Tosafot on Berakhot.2b.4"),
])
def test_shift_decrements_daf(ref, expected):
    assert shift_daf(ref, -1) == expected


@pytest.mark.parametrize("ref", [
    "Genesis.1.1",                       # Tanakh — no daf component
    "Mishnah Bava Metzia.1.1",           # Mishnah — chapter.mishnah, not a daf
    "Psalms.119",
    "Rashi on Genesis.1.1",
])
def test_non_talmud_refs_unchanged(ref):
    assert shift_daf(ref, -1) == ref
    assert daf_component(ref) is None


def test_refuses_to_go_below_daf_2():
    # daf 2 would become daf 1 (which does not exist) — left unchanged
    assert shift_daf("Berakhot.2a.1", -1) == "Berakhot.2a.1"


def test_daf_component_index():
    assert daf_component("Bava Metzia.3a.1") == 1
    assert daf_component("Rashi on Bava Metzia.3a.1") == 1
