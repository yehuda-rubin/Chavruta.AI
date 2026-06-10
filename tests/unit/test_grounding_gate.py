"""Unit: the citation-enforcement gate (task T040) — the concrete Principle I mechanism."""

from __future__ import annotations

from chavruta.generation.grounded import build_prompt, enforce_citations, no_source_answer
from chavruta.corpus.schema import Intent
from chavruta.retrieval.base import RankedHit


def _hits():
    return [
        RankedHit(chunk_id="c1", ref="Genesis.1.3", text="ויאמר אלהים יהי אור",
                  score=0.9, deep_link="l/1"),
        RankedHit(chunk_id="c2", ref="Rashi on Genesis.1.3", text="וגנזו לצדיקים",
                  score=0.8, commentator_id="rashi", deep_link="l/2"),
    ]


def test_valid_markers_become_resolving_citations():
    prompt, marker_map = build_prompt("q", _hits())
    text, citations, grounded = enforce_citations("האור נברא ביום הראשון [S1] ורש\"י מבאר [S2]", marker_map)
    assert grounded and len(citations) == 2
    assert {c.chunk_id for c in citations} == {"c1", "c2"}
    assert all(c.deep_link for c in citations)


def test_fabricated_marker_is_stripped():
    """A marker the model invented (no such source) must not survive (FR-002)."""
    _, marker_map = build_prompt("q", _hits())
    text, citations, grounded = enforce_citations("claim [S1] and fabricated [S9]", marker_map)
    assert "[S9]" not in text, "fabricated citation must be removed"
    assert {c.chunk_id for c in citations} == {"c1"}
    assert grounded  # still grounded by the one real citation


def test_answer_with_no_valid_markers_is_not_grounded():
    _, marker_map = build_prompt("q", _hits())
    text, citations, grounded = enforce_citations("an answer with no citations at all", marker_map)
    assert not grounded and citations == []


def test_no_source_answer_is_honest_in_both_languages():
    he = no_source_answer("he", Intent.QA)
    en = no_source_answer("en", Intent.QA)
    for a in (he, en):
        assert a.no_source and not a.grounded and a.citations == []


def test_prompt_contains_only_retrieved_sources():
    """The model receives ONLY retrieved material — the knowledge boundary (Principle I)."""
    prompt, marker_map = build_prompt("q", _hits())
    assert len(prompt.sources) == len(_hits()) == len(marker_map)
    texts = {s.text for s in prompt.sources}
    assert texts == {h.text for h in _hits()}
