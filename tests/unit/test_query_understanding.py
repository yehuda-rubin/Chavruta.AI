"""Phase 1+2 (spec 002): Hebrew ref detection + landmark resolution + router wiring."""

from __future__ import annotations

import pytest

from chavruta.corpus.schema import Intent, Query
from chavruta.intents.hebrew_refs import detect_hebrew_refs, gematria
from chavruta.intents.landmarks import resolve_landmarks
from chavruta.intents.router import Router, retrieval_text
from chavruta.corpus.links import LinkGraph
from chavruta.generation.grounded import enforce_citations
from chavruta.retrieval.base import RankedHit
from chavruta.retrieval.hybrid import HybridRetriever


@pytest.mark.parametrize("token,value", [
    ("א", 1), ("י", 10), ("טו", 15), ("טז", 16), ("כא", 21), ("קנ", 150),
    ("תריג", 613),
])
def test_gematria(token, value):
    assert gematria(token) == value


@pytest.mark.parametrize("text,expected", [
    ("בראשית א:א", ["Genesis.1.1"]),
    ("בראשית פרק א פסוק ג", ["Genesis.1.3"]),
    ("שמות כ׳", ["Exodus.20"]),
    ('ויקרא י״ט:י״ח', ["Leviticus.19.18"]),
    ("דברים ו:ד", ["Deuteronomy.6.4"]),
    ("בבא מציעא ב׳ ע״א", ["Bava Metzia.2a"]),
    ("בבא מציעא ב׳ ע״ב", ["Bava Metzia.2b"]),
    ("בבא מציעא נט ע״א", ["Bava Metzia.59a"]),   # unmarked daf, disambiguated by the amud
    ("ברכות ב ע״ב", ["Berakhot.2b"]),
    ("שמואל א ג:י", ["I Samuel.3.10"]),
])
def test_detect_hebrew_refs(text, expected):
    assert detect_hebrew_refs(text) == expected


@pytest.mark.parametrize("text", [
    "בראשית ברא אלוקים את השמים ואת הארץ",   # prose, not a ref
    "מה כתוב בספר במדבר על המרגלים",           # book named, no chapter
    "מה הדין בבבא מציעא",                       # tractate named, no daf
])
def test_no_false_positive_refs(text):
    assert detect_hebrew_refs(text) == []


@pytest.mark.parametrize("text,expected", [
    ("מה המחלוקת בין רש\"י לרמב\"ן בפסוק הראשון בתורה?", "Genesis.1.1"),
    ("תסביר את עשרת הדיברות", "Exodus.20"),
    ("מה הפירוש של קריאת שמע", "Deuteronomy.6.4"),
    ("הפסוק הראשון בבראשית", "Genesis.1.1"),
    ("הדף הראשון בבבא מציעא", "Bava Metzia.2a"),
    ("תחילת ספר ויקרא", "Leviticus.1.1"),
])
def test_landmarks(text, expected):
    assert expected in resolve_landmarks(text)


def test_router_resolves_indirect_comparison():
    """The original failing question must now anchor to Genesis.1.1 with both commentators."""
    q = Router().route(Query(text="מה המחלוקת בין רש\"י לרמב\"ן בפסוק הראשון בתורה?"))
    assert q.named_refs == ["Genesis.1.1"]
    assert set(q.commentator_ids) == {"rashi", "ramban"}
    assert q.intent is Intent.COMPARE
    assert q.expand_links is True


def test_router_hebrew_explicit_ref():
    q = Router().route(Query(text="מה אומר רש\"י על בראשית א:א?"))
    assert "Genesis.1.1" in q.named_refs
    assert q.commentator_ids == ["rashi"]


def test_router_english_ref_still_works():
    q = Router().route(Query(text="What does Rashi say on Genesis 1:1?"))
    assert "Genesis.1.1" in q.named_refs


@pytest.mark.parametrize("text,expected", [
    ("הכן שיעור על שניים אוחזין בטלית", "שניים אוחזין בטלית"),
    ("שיעור על תשובה בספר יונה", "תשובה בספר יונה"),
    ("prepare a lesson on Shenayim Ochazin", "Shenayim Ochazin"),
    ("שניים אוחזין בטלית", "שניים אוחזין בטלית"),   # no lead-in → unchanged
])
def test_retrieval_text_strips_lesson_lead(text, expected):
    assert retrieval_text(text) == expected


def test_router_sets_search_text():
    q = Router().route(Query(text="הכן שיעור על שניים אוחזין"))
    assert q.search_text == "שניים אוחזין"


# ── 5 more (Phase 1–3 hardening) ─────────────────────────────────────────────────

def test_dedup_keeps_highest_score():
    """Regression: an anchored hit (1.0) must beat the same chunk as a low vector hit,
    otherwise a verse's named commentator gets demoted out of top_k."""
    low = RankedHit(chunk_id="rashi@gen1.1", ref="Rashi on Genesis.1.1", text="…", score=0.13)
    high = RankedHit(chunk_id="rashi@gen1.1", ref="Rashi on Genesis.1.1", text="…", score=1.0)
    out = HybridRetriever._dedup([low, high])
    assert len(out) == 1
    assert out[0].score == 1.0


def test_multiple_hebrew_refs_in_one_question():
    assert detect_hebrew_refs("השווה בין בראשית א:א לשמות כ׳") == ["Genesis.1.1", "Exodus.20"]


def test_chapter_only_and_psalms_gematria():
    # Psalms 119 via a marked multi-letter numeral (קי״ט = 119), chapter-level anchor.
    assert detect_hebrew_refs("מה כתוב בתהילים קי״ט") == ["Psalms.119"]


def test_router_lesson_intent_with_landmark():
    q = Router().route(Query(text="הכן שיעור על עשרת הדיברות"))
    assert q.intent is Intent.LESSON
    assert "Exodus.20" in q.named_refs
    assert q.expand_links is True


def test_router_single_commentator_explain_with_verse():
    q = Router().route(Query(text="מה אומר אבן עזרא על שמות ג׳ י״ד?"))
    assert q.commentator_ids == ["ibn_ezra"]
    assert "Exodus.3.14" in q.named_refs
    assert q.intent is Intent.EXPLAIN


# ── Phase 4: links graph (anchor chains → related material) ──────────────────────

def test_linkgraph_reaches_commentaries_then_supercommentary():
    g = LinkGraph()
    g.add_anchor("Rashi on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    g.add_anchor("Ramban on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    g.add_anchor("Mizrachi on Genesis.1.1.1", "Rashi on Genesis.1.1", "tanakh", "tanakh")

    d1 = set(g.expand(["Genesis.1.1"], depth=1))
    assert {"Rashi on Genesis.1.1", "Ramban on Genesis.1.1"} <= d1
    assert "Mizrachi on Genesis.1.1.1" not in d1   # supercommentary is one hop further

    d2 = set(g.expand(["Genesis.1.1"], depth=2))
    assert "Mizrachi on Genesis.1.1.1" in d2        # pasuk → Rashi → Mizrachi


def test_linkgraph_save_load_roundtrip(tmp_path):
    g = LinkGraph()
    g.add_anchor("Rashi on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    path = tmp_path / "links.jsonl"
    g.save(path)
    loaded = LinkGraph.load(path)
    assert "Rashi on Genesis.1.1" in loaded.expand(["Genesis.1.1"], depth=1)


# ── Citation enforcement robustness (combined / fabricated markers) ──────────────

def _hit(cid, ref):
    return RankedHit(chunk_id=cid, ref=ref, text="…", score=1.0)


def test_enforce_citations_handles_combined_markers():
    mm = {"S1": _hit("a", "Rashi on Genesis.1.1"), "S2": _hit("b", "Ramban on Genesis.1.1")}
    clean, cites, grounded = enforce_citations("שניהם מצטטים את רבי יצחק [S1, S2].", mm)
    assert grounded
    assert {c.ref for c in cites} == {"Rashi on Genesis.1.1", "Ramban on Genesis.1.1"}


def test_enforce_citations_drops_fabricated_marker():
    mm = {"S1": _hit("a", "Rashi on Genesis.1.1")}
    clean, cites, grounded = enforce_citations("טענה [S1] ומקור בדוי [S9].", mm)
    assert grounded and len(cites) == 1
    assert "[S9]" not in clean   # fabricated marker removed
    assert "[S1]" in clean


# ── Phase 5: optional LLM query-planner fallback (fake planner, no network) ───────

def test_router_llm_planner_fallback_when_heuristics_miss():
    class FakePlanner:
        def plan(self, text):
            return {"refs": ["Genesis.1.1"], "commentators": ["rashi", "ramban"], "intent": "compare"}
    q = Router(planner=FakePlanner()).route(Query(text="what is the dispute about the opening of scripture?"))
    assert q.named_refs == ["Genesis.1.1"]
    assert set(q.commentator_ids) == {"rashi", "ramban"}
    assert q.intent is Intent.COMPARE


def test_router_planner_skipped_when_heuristics_resolve():
    class BoomPlanner:
        def plan(self, text):
            raise AssertionError("planner must not run when heuristics already found a ref")
    q = Router(planner=BoomPlanner()).route(Query(text="בראשית א:א"))
    assert q.named_refs == ["Genesis.1.1"]


def test_router_planner_failure_is_swallowed():
    class FailPlanner:
        def plan(self, text):
            raise RuntimeError("LLM down")
    q = Router(planner=FailPlanner()).route(Query(text="a general question with no reference at all"))
    assert not q.named_refs   # None or [] — request still routed, no exception
