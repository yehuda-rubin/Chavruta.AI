"""backfill_commercial_rights.py's title resolution (found 2026-08-23 against the real manifest).

The 15 tiers' licenses.json is inconsistently granular: a multi-volume/sectioned work is
sometimes recorded per volume already ("Mishneh Torah, Positive Mitzvot") but more often only at
the top work level ("Arukh HaShulchan", "Beit Yosef", "Torah Temimah on Torah"), while the live
collection's per-chunk title correctly keeps Sefaria's own sub-index ("Arukh HaShulchan, Yoreh
De'ah", "Torah Temimah on Torah, Leviticus"). A first dry-run against the real production
collection (2026-08-23) left 8,528 titles / 650,410 chunks unresolved before this fix; every
sampled one turned out to be exactly this pattern, not a genuine manifest gap.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "backfill_commercial_rights", ROOT / "scripts" / "backfill_commercial_rights.py"
)
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)
resolve_rights = _m.resolve_rights


def test_an_exact_title_match_is_used_first():
    manifest = {"Yoma": ("CC-BY-SA", "Wikisource")}
    assert resolve_rights("Yoma", manifest) == ("CC-BY-SA", "Wikisource")


def test_falls_back_to_the_top_level_work_when_the_volume_is_not_separately_recorded():
    """The real case found live: Arukh HaShulchan's licences.json entry has no volume suffix at
    all, but every chunk's title carries one."""
    manifest = {"Arukh HaShulchan": ("Public Domain", "Vilna 1884")}
    assert resolve_rights("Arukh HaShulchan, Yoreh De'ah", manifest) == ("Public Domain", "Vilna 1884")
    assert resolve_rights("Arukh HaShulchan, Even HaEzer", manifest) == ("Public Domain", "Vilna 1884")


def test_strips_only_one_trailing_segment_at_a_time_not_straight_to_the_first_comma():
    """An already volume-qualified manifest entry ('Shem HaGedolim, Maarekhet Sefarim') must not
    lose that qualifier by jumping straight to the bare 'Shem HaGedolim' — only the FURTHER
    trailing part ('Part 2') should be stripped."""
    manifest = {
        "Shem HaGedolim": ("CC0", "wrong — would only match if over-stripped"),
        "Shem HaGedolim, Maarekhet Sefarim": ("CC-BY-SA", "correct"),
    }
    assert resolve_rights("Shem HaGedolim, Maarekhet Sefarim, Part 2", manifest) == ("CC-BY-SA", "correct")


def test_a_title_absent_at_every_level_is_left_unresolved_not_guessed():
    manifest = {"Arukh HaShulchan": ("Public Domain", "Vilna 1884")}
    assert resolve_rights("Some Other Work, Volume 3", manifest) is None


def test_torah_temimah_real_case():
    manifest = {"Torah Temimah on Torah": ("Public Domain", "1904")}
    assert resolve_rights("Torah Temimah on Torah, Leviticus", manifest) == ("Public Domain", "1904")
