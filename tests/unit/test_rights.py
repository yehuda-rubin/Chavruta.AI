"""Rights classification — the gate that decides what a PAID tier may reproduce.

The values here are REAL, read live from sefaria.org's API on 2026-07-17 for texts this system
actually cited. They are not illustrative: `Berakhot` really does default to the CC-BY-NC William
Davidson Edition, and `Steinsaltz on Mishneh Torah` really is bare copyright.

This module fails CLOSED, so the tests care most about the negative cases: anything not positively
granted must come back False.
"""

from __future__ import annotations

import pytest

from chavruta.corpus.rights import (
    allows_commercial_use,
    attribution_line,
    commercial_filter_values,
    is_copyrighted,
    is_noncommercial,
    is_unknown,
    requires_attribution,
)


# ── Real licence strings observed on Sefaria ──────────────────────────────────
@pytest.mark.parametrize("lic", [
    "Public Domain",       # Tractate Berakot by A. Cohen, Cambridge Univ
    "CC0",                 # Sefaria Community Translation (Peninei Halakhah, English)
    "CC-BY",               # Guggenheimer edition of the Yerushalmi
    "CC-BY-SA",            # Wikisource-derived editions
])
def test_commercial_use_allowed_for_granting_licenses(lic):
    assert allows_commercial_use(lic) is True


@pytest.mark.parametrize("lic,why", [
    ("CC-BY-NC", "William Davidson Talmud + Mishnah; Peninei Halakhah Hebrew — NC bars paid use"),
    ("Copyright: Steinsaltz Center", "Steinsaltz on Mishneh Torah — no grant at all"),
    ("unknown", "Sefaria never verified it; unknown is not permission"),
    ("", "missing field — same as unknown"),
    (None, "absent entirely"),
])
def test_commercial_use_refused_without_a_grant(lic, why):
    assert allows_commercial_use(lic) is False, why


def test_unrecognised_license_fails_closed():
    """A licence string nobody anticipated must NOT be read as permission."""
    assert allows_commercial_use("Some New License 2.0") is False


@pytest.mark.parametrize("lic", ["CC-BY-NC", "cc-by-nc", "CC BY-NC 4.0", "  CC-BY-NC  "])
def test_noncommercial_detected_across_spellings(lic):
    assert is_noncommercial(lic) is True
    assert allows_commercial_use(lic) is False


def test_copyright_holder_string_detected():
    assert is_copyrighted("Copyright: Steinsaltz Center") is True
    assert is_copyrighted("CC-BY") is False


@pytest.mark.parametrize("lic", ["", None, "unknown", "UNKNOWN"])
def test_unknown_detected(lic):
    assert is_unknown(lic) is True


def test_public_domain_is_not_unknown():
    assert is_unknown("Public Domain") is False


# ── Attribution (TASL) ────────────────────────────────────────────────────────
@pytest.mark.parametrize("lic", ["CC-BY", "CC-BY-SA", "CC-BY-NC"])
def test_attribution_required_for_by_licenses(lic):
    assert requires_attribution(lic) is True


@pytest.mark.parametrize("lic", ["Public Domain", "CC0"])
def test_attribution_not_required_for_pd_and_cc0(lic):
    assert requires_attribution(lic) is False


def test_attribution_line_carries_edition_and_license():
    """Generic 'Sefaria' is not TASL — the specific edition and licence must appear."""
    line = attribution_line(
        ref="Berakhot 2a",
        version_title="William Davidson Edition - English",
        license_str="CC-BY-NC",
        deep_link="https://www.sefaria.org/Berakhot.2a",
    )
    assert "Berakhot 2a" in line
    assert "William Davidson Edition - English" in line     # WHICH edition — the audit trail
    assert "CC-BY-NC" in line
    assert "sefaria.org" in line


# ── The filter a paid tier would actually apply ───────────────────────────────
def test_commercial_filter_keeps_only_granted_licenses():
    present = ["Public Domain", "CC0", "CC-BY", "CC-BY-SA",
               "CC-BY-NC", "Copyright: Steinsaltz Center", "unknown", ""]
    allowed = commercial_filter_values(present)
    assert set(allowed) == {"Public Domain", "CC0", "CC-BY", "CC-BY-SA"}
    assert "CC-BY-NC" not in allowed
    assert "Copyright: Steinsaltz Center" not in allowed
