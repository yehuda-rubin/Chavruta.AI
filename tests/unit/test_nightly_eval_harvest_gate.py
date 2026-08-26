"""The nightly harvest gate — when a stale pool blocks itself from ever being refreshed.

Measured live 2026-08-14 through 2026-08-16: a 3325-pair harvested pool passed the count gate
(>2000) and the age gate (<14d) while only ~21 of 800 sampled pairs were actually answered
(recall=0.026) — far below what the tuner needs to say anything. Every tick of a 16-hour Saturday
window (32/32) and a full nightly window (8/8) independently re-measured the same pool, re-derived
the same "too thin" verdict, and threw it away — because the gate deciding whether to re-harvest
never looked at answered-rate, only size and age.

`_too_thin_reason` closes that gap by reading the marker `tune_retrieval.py::_mark_thin` leaves
beside the pairs file whenever it hits that verdict. These tests are the reader side; the writer
side (the marker's own shape) is pinned in test_tuning_state.py.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def nightly():
    """nightly_eval.py has no heavy deps (plain stdlib + argparse) — imported directly, no head/tail
    split needed."""
    path = ROOT / "scripts" / "nightly_eval.py"
    spec = importlib.util.spec_from_file_location("nightly_eval_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pairs(tmp_path: Path, body: str = "x") -> Path:
    p = tmp_path / "pairs.jsonl"
    p.write_text(body, encoding="utf-8")
    return p


def _mark(pairs: Path, **fields) -> None:
    stat = pairs.stat()
    marker = pairs.with_suffix(pairs.suffix + ".thin.json")
    marker.write_text(json.dumps({"pool": f"{stat.st_size}:{int(stat.st_mtime)}", **fields}),
                      encoding="utf-8")


def test_a_pool_with_no_thin_mark_is_not_flagged(tmp_path, nightly):
    pairs = _pairs(tmp_path)
    assert nightly._too_thin_reason(pairs) == ""


def test_a_pool_the_tuner_marked_thin_is_flagged_even_though_it_is_big_and_fresh(tmp_path, nightly):
    """The whole point: count and age both pass, and this must still say re-harvest."""
    pairs = _pairs(tmp_path, "x" * 10_000)      # plenty big, just written = plenty fresh
    _mark(pairs, hits=21, sample=800, min_hits=30)

    reason = nightly._too_thin_reason(pairs)
    assert reason and "21" in reason and "800" in reason


def test_a_stale_mark_from_before_a_re_harvest_is_ignored(tmp_path, nightly):
    """The mark is tagged to the pool it was measured against. A harvest replaces the file (new
    size, new mtime) — the old verdict must not silently apply to pairs it never saw."""
    pairs = _pairs(tmp_path, "old pool")
    _mark(pairs, hits=21, sample=800, min_hits=30)

    pairs.write_text("a completely different, freshly harvested pool" * 10, encoding="utf-8")

    assert nightly._too_thin_reason(pairs) == ""


def test_a_missing_or_corrupt_marker_is_not_a_reason_to_re_harvest(tmp_path, nightly):
    """This runs unattended. A crash here costs the whole window."""
    pairs = _pairs(tmp_path)
    assert nightly._too_thin_reason(pairs) == ""          # no marker at all

    marker = pairs.with_suffix(pairs.suffix + ".thin.json")
    marker.write_text("{not json", encoding="utf-8")
    assert nightly._too_thin_reason(pairs) == ""


def test_the_nightly_sample_default_actually_clears_min_hits():
    """800 was sized for a ~5% hit rate; the real pool measured 2.6%-3.5% (2026-08-14 through
    2026-08-16), so every single tick of a 16-hour Saturday window (32/32) and a full nightly window
    (8/8) bailed at TOO THIN without testing one candidate. 1600 was measured live against the same
    pool (--sample 1600, recall=0.035 -> ~56 answered, comfortably above MIN_HITS=30). Pinned as a
    floor rather than an exact value, so raising it further later does not fail this test — only
    dropping it back toward 800 should."""
    src = (ROOT / "scripts" / "nightly_eval.py").read_text(encoding="utf-8")
    m = re.search(r'ap\.add_argument\("--sample", type=int, default=(\d+)\)', src)
    assert m, "the --sample argument's shape changed — update this test's regex"
    assert int(m.group(1)) >= 1600


def test_the_full_harvest_gate_flags_a_big_fresh_but_thin_pool(tmp_path, nightly, monkeypatch):
    """End to end through _harvest_reason: this is what actually runs every night."""
    pairs = _pairs(tmp_path, "x" * 10_000)
    _mark(pairs, hits=21, sample=800, min_hits=30)
    monkeypatch.setattr(nightly, "PAIRS", str(pairs))
    monkeypatch.setattr(nightly, "PAIRS_MIN", 1)            # the count gate must pass to even reach
                                                             # the too-thin check — this fixture pool
                                                             # is one un-split "line", not 3325 real
                                                             # pairs

    reason = nightly._harvest_reason()
    assert "21" in reason
