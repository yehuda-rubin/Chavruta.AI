"""Unit: retrieval building blocks — dedup, anchoring, ref matching, link graph (task T040)."""

from __future__ import annotations

from chavruta.corpus.links import LinkGraph
from chavruta.eval.harness import _ref_matches
from chavruta.retrieval.base import RankedHit
from chavruta.retrieval.hybrid import HybridRetriever


def _hit(cid, ref, score=0.5, commentator=None, anchor=None):
    return RankedHit(chunk_id=cid, ref=ref, text="t", score=score,
                     commentator_id=commentator, anchor_ref=anchor)


def test_dedup_keeps_first_occurrence():
    hits = [_hit("a", "r1", 0.9), _hit("a", "r1", 0.3), _hit("b", "r2", 0.5)]
    out = HybridRetriever._dedup(hits)
    assert [h.chunk_id for h in out] == ["a", "b"]


def test_anchor_refs_prefer_anchor_over_own_ref():
    hits = [
        _hit("p", "Genesis.1.3", 0.9),                                   # pasuk → its own ref
        _hit("r", "Rashi on Genesis.1.3", 0.8, "rashi", "Genesis.1.3"),  # commentary → anchor
    ]
    anchors = HybridRetriever._anchor_refs(hits)
    assert anchors == ["Genesis.1.3"], "one underlying pasuk, not two entries"


def test_ref_matches_segmentwise():
    assert _ref_matches("Genesis.1.1", "Genesis.1.1")
    assert _ref_matches("Genesis.1", "Genesis.1.3")          # chapter-level
    assert not _ref_matches("Genesis.1.1", "Genesis.1.10")   # no string-prefix false positive
    assert _ref_matches("Song of Songs.6.3", "Song of Songs.6.3")
    assert not _ref_matches("Genesis.1.1", "Exodus.1.1")


def test_link_graph_expand_depth():
    g = LinkGraph()
    g.add_anchor("Rashi on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    g.add_anchor("Mizrachi on Genesis.1.1", "Rashi on Genesis.1.1", "mizrachi", "tanakh")

    depth1 = g.expand(["Genesis.1.1"], depth=1)
    assert "Rashi on Genesis.1.1" in depth1
    assert "Mizrachi on Genesis.1.1" not in depth1

    depth2 = g.expand(["Genesis.1.1"], depth=2)
    assert "Mizrachi on Genesis.1.1" in depth2, "depth 2 reaches the supercommentary"


def test_link_graph_work_scoping():
    g = LinkGraph()
    g.add_anchor("Rashi on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    g.add_anchor("Mizrachi on Genesis.1.1", "Rashi on Genesis.1.1", "mizrachi", "tanakh")
    reached = g.expand(["Genesis.1.1"], depth=2, work_ids=["tanakh"])
    assert "Mizrachi on Genesis.1.1" not in reached, "scoping excludes unloaded works"
