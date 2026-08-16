"""The tuner's cross-night state — the part that decides whether a sweep can ever finish.

Before this existed the nightly run restarted from hybrid.py's constants every night, swept partway,
and was killed at 05:00. The log claimed the abandoned step would be "picked up the next run", and
nothing carried over; two consecutive nights ended rc=124 having accepted a value that was never
confirmed and never written down. Since one candidate costs ~22 minutes at a pool size worth
measuring on, a five-knob descent needs 7-9 hours against a 5-hour window — so it could not have
finished no matter how many nights it ran.

These tests pin the two things that make resuming safe rather than merely possible: progress is kept
across runs, and it is thrown away the moment it stops applying to what is being measured.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tune():
    """Import the script without its heavy tail (torch, qdrant, the pipeline).

    The module imports torch at module scope on purpose — the Windows DLL ordering bug in
    CLAUDE.md — so importing it here would drag the whole retrieval stack into a unit test. Only the
    state helpers are under test, and they are pure.
    """
    path = ROOT / "scripts" / "tune_retrieval.py"
    src = path.read_text(encoding="utf-8")
    head = src.split("import torch")[0]
    spec = importlib.util.spec_from_loader("tune_state_only", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__dict__["__file__"] = str(path)          # the head resolves ROOT from it
    exec(compile(head, "tune_retrieval.py", "exec"), mod.__dict__)          # noqa: S102
    # KNOBS and the state helpers live below the torch import, so pull that span across on its own.
    # The defs in it that touch `hybrid` only do so when called, and nothing here calls them.
    tail = src[src.index("KNOBS: dict[str, list]"):src.index("def main(")]
    exec(compile(tail, "tune_retrieval.py", "exec"), mod.__dict__)          # noqa: S102
    return mod


BASE = {"_TRACTATE_BOOST": 0.05, "_TRACTATE_TOP_K": 6, "_FOUNDATIONAL_BOOST": 0.05,
        "_FOUNDATIONAL_TOP_K": 6, "_BASE_SLOTS": 2}


def _pairs(tmp_path: Path, body: str = "x") -> Path:
    p = tmp_path / "pairs.jsonl"
    p.write_text(body, encoding="utf-8")
    return p


def test_a_night_starts_from_what_the_last_night_accepted(tmp_path, tune):
    """The whole point. Without this each night re-measured the same first knob forever."""
    pairs, state_file = _pairs(tmp_path), tmp_path / "state.json"
    fp = tune._fingerprint(pairs, BASE)

    first = tune._load_state(state_file, fp)
    assert first["best"] is None and first["done"] == []

    first["best"] = dict(BASE, _TRACTATE_BOOST=0.2)
    first["done"] = ["_TRACTATE_BOOST"]
    tune._save_state(state_file, first)

    second = tune._load_state(state_file, fp)
    assert second["done"] == ["_TRACTATE_BOOST"]
    assert second["best"]["_TRACTATE_BOOST"] == 0.2, "the night's winner was not carried forward"


def test_progress_is_discarded_when_someone_applies_a_value_by_hand(tmp_path, tune):
    """Coordinate descent keeps earlier winners, so every later knob was measured against the
    earlier ones. If the constants in hybrid.py move, the incumbent those measurements assumed no
    longer exists and carrying them forward compares things that were never comparable."""
    pairs, state_file = _pairs(tmp_path), tmp_path / "state.json"
    saved = tune._load_state(state_file, tune._fingerprint(pairs, BASE))
    saved["best"], saved["done"] = dict(BASE, _TRACTATE_BOOST=0.2), ["_TRACTATE_BOOST"]
    tune._save_state(state_file, saved)

    applied = dict(BASE, _FOUNDATIONAL_BOOST=0.2)          # a human edited hybrid.py
    fresh = tune._load_state(state_file, tune._fingerprint(pairs, applied))

    assert fresh["done"] == [] and fresh["best"] is None


def test_progress_is_discarded_when_the_pairs_pool_is_re_harvested(tmp_path, tune):
    """An mrr measured on one set of questions is not comparable to an mrr on another, and the
    harvest replaces the pool wholesale — 105 pairs became 3325 in a single night."""
    pairs, state_file = _pairs(tmp_path), tmp_path / "state.json"
    saved = tune._load_state(state_file, tune._fingerprint(pairs, BASE))
    saved["best"], saved["done"] = dict(BASE), ["_TRACTATE_BOOST", "_TRACTATE_TOP_K"]
    tune._save_state(state_file, saved)

    pairs.write_text("a much larger pool" * 100, encoding="utf-8")
    fresh = tune._load_state(state_file, tune._fingerprint(pairs, BASE))

    assert fresh["done"] == []


def test_a_corrupt_or_older_state_file_starts_over_instead_of_raising(tmp_path, tune):
    """This runs unattended at 00:01. A crash here costs the whole window and nobody is watching."""
    pairs, state_file = _pairs(tmp_path), tmp_path / "state.json"
    fp = tune._fingerprint(pairs, BASE)

    state_file.write_text("{not json", encoding="utf-8")
    assert tune._load_state(state_file, fp)["done"] == []

    state_file.write_text(json.dumps({"version": 0, "fingerprint": fp, "done": ["_BASE_SLOTS"]}),
                          encoding="utf-8")
    assert tune._load_state(state_file, fp)["done"] == []


def test_the_sweep_advances_one_knob_at_a_time_and_terminates(tmp_path, tune):
    """Five knobs, five nights, then done — rather than restarting the descent forever."""
    pairs, state_file = _pairs(tmp_path), tmp_path / "state.json"
    fp = tune._fingerprint(pairs, BASE)
    seen = []

    for _ in range(len(tune.KNOBS) + 2):                   # two extra nights past the end
        state = tune._load_state(state_file, fp)
        todo = [k for k in tune.KNOBS if k not in set(state["done"])]
        if not todo:
            break
        seen.append(todo[0])
        state["best"] = dict(state.get("best") or BASE)
        state["done"] = state["done"] + [todo[0]]
        tune._save_state(state_file, state)

    assert seen == list(tune.KNOBS), "the sweep did not advance in order, or repeated a knob"
    assert tune._load_state(state_file, fp)["done"] == list(tune.KNOBS)


# ── A pool that passes count+age but is still too thin to tune on (2026-08-16) ─────────────────
# Measured live: a 3325-pair pool sat under the count and age gates for three days while every
# single tick of a 16-hour Saturday window and a full nightly window re-derived and re-discarded
# the same "TOO THIN" verdict, because the gate that decides whether to re-harvest never looked at
# how much of the pool is actually answered — only its size and age. _mark_thin/_too_thin_reason
# close that gap; these tests pin the marker's own shape, since nightly_eval.py reads it
# independently (see test_bug_regressions.py for the reader side).
def test_a_thin_verdict_is_marked_beside_the_pairs_file(tmp_path, tune):
    pairs = _pairs(tmp_path)
    tune._mark_thin(pairs, hits=21, sample=800)

    marker = pairs.with_suffix(pairs.suffix + ".thin.json")
    assert marker.exists()
    info = json.loads(marker.read_text(encoding="utf-8"))
    assert info["hits"] == 21 and info["sample"] == 800 and info["min_hits"] == tune.MIN_HITS


def test_a_thin_mark_is_tagged_to_the_pool_that_earned_it(tmp_path, tune):
    """A re-harvest changes the pairs file's size and mtime — the mark must not silently apply to
    a pool it was never measured against."""
    pairs = _pairs(tmp_path)
    tune._mark_thin(pairs, hits=21, sample=800)
    marker = pairs.with_suffix(pairs.suffix + ".thin.json")
    before = json.loads(marker.read_text(encoding="utf-8"))["pool"]

    pairs.write_text("a completely different, larger pool" * 50, encoding="utf-8")

    stat = pairs.stat()
    after = f"{stat.st_size}:{int(stat.st_mtime)}"
    assert before != after, "the fixture pool must actually change size for this test to mean anything"
