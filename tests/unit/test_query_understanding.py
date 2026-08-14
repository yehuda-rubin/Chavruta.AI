"""Phase 1+2 (spec 002): Hebrew ref detection + landmark resolution + router wiring."""

from __future__ import annotations

import pytest

from chavruta.corpus.links import LinkGraph
from chavruta.corpus.schema import Intent, Query
from chavruta.generation.grounded import enforce_citations
from chavruta.intents.hebrew_refs import detect_hebrew_refs, gematria
from chavruta.intents.landmarks import resolve_landmarks
from chavruta.intents.router import Router, retrieval_text
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


@pytest.mark.parametrize("text", [
    "האם מותר לשחק במחשב בשבת",
    "אפשר להשתמש בטלפון בשבת?",
    "is it permitted to use a computer on Shabbat",
])
def test_router_expands_tech_terms_toward_electricity_concept(text):
    """Regression (2026-08-07 prod finding): a modern-device question embeds close to an unrelated
    sugya sharing only a surface word (e.g. שחק/שחוק) and misses the corpus's own on-point
    electricity/muktzeh responsa. search_text (embedding input only) must carry the concept bridge;
    query.text (what the model sees) must stay untouched."""
    q = Router().route(Query(text=text))
    assert "חשמל" in q.search_text
    assert q.text == text


def test_router_does_not_expand_tech_terms_when_absent():
    q = Router().route(Query(text="מה אומר רש\"י על בראשית א:א?"))
    assert "חשמל" not in q.search_text


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


# ── The daf named BEFORE the tractate — reported live 2026-08-13 ─────────────
# Someone opened chavruta mode with "אני באמצע ללמוד את דף עט בחולין", was answered about
# שיעור ארבע מילין out of a Shulchan Arukh commentary, said "זאת לא הסוגיה", and got the same
# wrong source a second time. Only when he described the sugya in his own words did retrieval
# find Chullin.158.6 — which IS daf 79b. The daf was in the corpus the whole time.
#
# Every pattern read the tractate FIRST, so this phrasing produced neither a ref nor even a
# tractate to scope the search to, and retrieval fell back to unscoped semantic search over a
# sentence that carries almost no meaning on its own.
@pytest.mark.parametrize("text,expected", [
    ("אני באמצע ללמוד את דף עט בחולין", ["Chullin.79a", "Chullin.79b"]),
    ("דף עט בחולין", ["Chullin.79a", "Chullin.79b"]),
    ("בדף עט בחולין", ["Chullin.79a", "Chullin.79b"]),
    ("דף עט במסכת חולין", ["Chullin.79a", "Chullin.79b"]),
    ("אני באמצע ללמוד את דף ב בבבא מציעא", ["Bava Metzia.2a", "Bava Metzia.2b"]),
    # An explicit amud still wins — it is more specific than "the daf", so don't widen it.
    ("דף עט. בחולין", ["Chullin.79a"]),
    ("דף עט: בחולין", ["Chullin.79b"]),
])
def test_a_daf_named_before_its_tractate_resolves(text, expected):
    assert detect_hebrew_refs(text) == expected


def test_a_bare_daf_covers_both_amudim():
    """"דף עט" names the whole daf, and a sugya does not stop at the page turn. The answer this
    bug was about sat on 79b; anchoring only to 79a would reproduce the miss more quietly."""
    from chavruta.corpus.refs import with_ref_variants

    refs = detect_hebrew_refs("אני לומד דף עט בחולין")
    corpus = {v for r in refs for v in with_ref_variants([r])}
    # Amud-linear: 79a → 157, 79b → 158 (N = 2·daf ∓ 1).
    assert "Chullin.157.1" in corpus and "Chullin.158.1" in corpus


@pytest.mark.parametrize("text", [
    "ברכות טובות",          # ט = 9; a tractate followed by an innocent word
    "שבת קודש",             # ק = 100 — the case the amud requirement exists for
    "דף על השולחן",         # "דף" with no tractate anywhere
    "אני קורא ספר טוב",
])
def test_prose_that_merely_contains_a_tractate_name_still_anchors_nothing(text):
    """The amud marker was required precisely to stop these. Relaxing it for the daf-first form
    must not reopen them — the literal word דף is what carries the disambiguation instead."""
    assert detect_hebrew_refs(text) == []


def test_the_tractate_alone_is_scoped_even_in_the_daf_first_order():
    """The floor beneath the ref. Even when a daf number is implausible or the exact ref misses,
    an answer from somewhere in Chullin beats one from a Shulchan Arukh commentary on a different
    subject — which is what the live report got."""
    from chavruta.intents.hebrew_refs import detect_tractates

    assert detect_tractates("אני באמצע ללמוד את דף עט בחולין") == ["Chullin"]
    assert detect_tractates("דף ב בבבא מציעא") == ["Bava Metzia"]


# ── The reverent spelling (reported 2026-08-14) ──────────────────────────────
# A user asked for the source of "הנשמה היא חלק אלוק ממעל" and was answered from works nobody has
# heard of. The phrase is a verbatim quotation of Iyov 31:2, which sits in the corpus — but he wrote
# the divine name the way observant Hebrew writes it outside prayer, with ק for ה, and the corpus
# (being the texts themselves) spells it in full. Measured on the live collection: his spelling put
# the pasuk nowhere in the top ten; the real spelling put it second.
@pytest.mark.parametrize("written,sources_spell_it", [
    ("חלק אלוק ממעל", "חלק אלוה ממעל"),
    ("אלוקים", "אלוהים"),
    ("אלקים", "אלהים"),
    ("ואלוקי אבותינו", "ואלוהי אבותינו"),
    ("באלקים", "באלהים"),
    ("אלוקינו", "אלוהינו"),
    ("מה המקור לכך שהנשמה היא חלק אלוק ממעל?", "מה המקור לכך שהנשמה היא חלק אלוה ממעל?"),
])
def test_the_reverent_spelling_is_restored_for_search(written, sources_spell_it):
    from chavruta.corpus.normalize import deuphemize_he

    assert deuphemize_he(written) == sources_spell_it


@pytest.mark.parametrize("ordinary", [
    "חלק", "צדק", "חוק", "רק", "שוק", "דק", "תיק", "פרק", "הצדק שלך", "חלק מהתשובה",
    "אלוקיסט",          # a longer word that merely begins the same way
])
def test_ordinary_words_ending_in_kuf_are_left_alone(ordinary):
    """A blanket ק→ה would wreck the language. The rewrite is anchored to the אל- stem with a word
    boundary on both sides, so nothing but the divine name is touched."""
    from chavruta.corpus.normalize import deuphemize_he

    assert deuphemize_he(ordinary) == ordinary


def test_the_rewrite_is_for_search_only_and_never_shown_to_the_reader():
    """What a user chose to write is theirs. This exists so the query and the corpus can meet — the
    retriever embeds the rewritten form, and nothing else in the request is altered."""
    import importlib
    import inspect

    from chavruta.retrieval import hybrid

    src = inspect.getsource(hybrid.HybridRetriever.retrieve)
    assert "deuphemize_he(query.search_text or query.text)" in src, "not wired into embedding"
    # The rewrite feeds the embedder and nothing else — the raw text must never be embedded
    # alongside it, and no display path may call it.
    assert "embed_query(query.search_text" not in src, "the un-rewritten text is still embedded"
    for module in ("app.api", "chavruta.generation.grounded"):
        mod = importlib.import_module(module)
        assert "deuphemize" not in inspect.getsource(mod), f"{module} rewrites what the reader sees"
