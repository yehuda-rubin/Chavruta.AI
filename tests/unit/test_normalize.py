"""Hebrew nikud/ktiv normalisation for lexical search (corpus.normalize)."""

from __future__ import annotations

import pytest

from chavruta.corpus.normalize import normalize_he


@pytest.mark.parametrize("vocalised,plain", [
    ("שְׁנַיִם אוֹחֲזִין בְּטַלִּית", "שניים אוחזין בטלית"),   # nikud + ktiv male/haser
    ("בְּרֵאשִׁית", "בראשית"),
    ("מִצְוֹת", "מצוות"),                                       # plene doubling וו→ו
    ("הָאָרֶץ", "הארץ"),
])
def test_vocalised_and_plain_coincide(vocalised, plain):
    assert normalize_he(vocalised) == normalize_he(plain)
    assert normalize_he(vocalised)   # non-empty


def test_strips_nikud_and_cantillation():
    # te'amim (cantillation) are combining marks too — must be removed
    assert normalize_he("בְּרֵאשִׁ֖ית") == normalize_he("בראשית")


def test_folds_final_letters():
    assert normalize_he("שלום") == normalize_he("שלומ")   # ם → מ
    assert "ם" not in normalize_he("שלום")


def test_drops_geresh_gershayim():
    assert normalize_he('רש"י') == normalize_he("רשי")
    assert normalize_he("ב׳") == normalize_he("ב")


def test_empty_and_whitespace():
    assert normalize_he("") == ""
    assert normalize_he("  שנים   אוחזין  ") == normalize_he("שנים אוחזין")
    assert "  " not in normalize_he("  שנים   אוחזין  ")
