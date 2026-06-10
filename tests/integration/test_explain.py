"""Integration: explain & compare commentators (task T034, User Story 2).

Covers: single-commentator explanation, comparison with both views present and attributed,
the honest missing-commentator case (never invent), and supercommentary-on-dispute
surfacing via anchor chains (T033a) once such texts are loaded.
"""

from __future__ import annotations

import pytest

from chavruta.config.profile import Profile
from chavruta.corpus.links import LinkGraph
from chavruta.corpus.schema import AnchorKind, Chunk, Intent, Query, UnitType
from chavruta.generation import grounded
from chavruta.pipeline.pipeline import ChavrutaPipeline
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.retrieval.link_expand import LinkExpander
from chavruta.store.base import StoredChunk


def _chunks():
    return [
        Chunk(chunk_id="Genesis.1.1_pasuk", work_id="tanakh", unit_type=UnitType.SOURCE,
              ref="Genesis.1.1", lang="he", text="בראשית ברא אלהים את השמים ואת הארץ",
              text_he="בראשית ברא אלהים", deep_link="l/Genesis.1.1"),
        Chunk(chunk_id="Genesis.1.1_Rashi", work_id="tanakh", unit_type=UnitType.COMMENTARY,
              ref="Rashi on Genesis.1.1", lang="he",
              text="רש\"י בראשית — אמר רבי יצחק לא היה צריך להתחיל את התורה אלא מהחודש הזה",
              text_he="אמר רבי יצחק", anchor_ref="Genesis.1.1",
              anchor_kind=AnchorKind.SOURCE, commentator_id="rashi", deep_link="l/rashi"),
        Chunk(chunk_id="Genesis.1.1_Ramban", work_id="tanakh", unit_type=UnitType.COMMENTARY,
              ref="Ramban on Genesis.1.1", lang="he",
              text="רמב\"ן בראשית — הקדוש ברוך הוא ברא הכל מאפס מוחלט יש מאין",
              text_he="ברא הכל יש מאין", anchor_ref="Genesis.1.1",
              anchor_kind=AnchorKind.SOURCE, commentator_id="ramban", deep_link="l/ramban"),
        # Supercommentary: Mizrachi explains Rashi — anchored on Rashi's comment, not the verse
        Chunk(chunk_id="Mizrachi.Genesis.1.1", work_id="mizrachi", unit_type=UnitType.COMMENTARY,
              ref="Mizrachi on Genesis.1.1", lang="he",
              text="המזרחי מבאר את דברי רש\"י למה התחילה התורה בבראשית",
              text_he="המזרחי מבאר", anchor_ref="Rashi on Genesis.1.1",
              anchor_kind=AnchorKind.COMMENTARY, commentator_id="mizrachi", deep_link="l/miz"),
    ]


def _seed(store, emb):
    store.ensure_collection("c", emb.dim)
    stored = []
    for c in _chunks():
        e = emb.embed_query(c.text)
        stored.append(StoredChunk(chunk_id=c.chunk_id, dense=e.dense, sparse=e.sparse,
                                  payload=c.to_payload()))
    store.upsert("c", stored)


def _link_graph():
    g = LinkGraph()
    g.add_anchor("Rashi on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    g.add_anchor("Ramban on Genesis.1.1", "Genesis.1.1", "tanakh", "tanakh")
    g.add_anchor("Mizrachi on Genesis.1.1", "Rashi on Genesis.1.1", "mizrachi", "tanakh")
    return g


@pytest.fixture
def pipeline(store, fake_embedding, fake_llm):
    _seed(store, fake_embedding)
    profile = Profile(name="test", collection="c", top_k=8, relevance_threshold=0.0)
    expander = LinkExpander(store, _link_graph(), profile)
    retriever = HybridRetriever(fake_embedding, store, profile, link_expander=expander)
    return ChavrutaPipeline.from_backends(
        profile, embedding=fake_embedding, store=store, llm=fake_llm, retriever=retriever
    )


def test_explain_single_commentator_attributed(pipeline):
    answer = pipeline.ask(Query(text="תסביר מה אומר רש\"י על בראשית", lang="he"))
    assert answer.grounded
    assert all(c.commentator_id == "rashi" for c in answer.citations), \
        "explain path must attribute to the requested commentator only (FR-006)"


def test_compare_retrieves_both_views(pipeline):
    """Both commentators' sources reach the prompt — disagreement can be surfaced (FR-007)."""
    q = pipeline.router.route(Query(text="מה המחלוקת בין רש\"י לרמב\"ן על בראשית 1:1?", lang="he"))
    assert q.intent is Intent.COMPARE
    result = pipeline.retriever.retrieve(q, top_k=8)
    who = {h.commentator_id for h in result.hits if h.commentator_id}
    assert {"rashi", "ramban"} <= who, "comparison needs both views present and attributed"


def test_missing_commentator_is_honest(pipeline):
    """A commentator with no comment here → honest absence, not invention."""
    answer = pipeline.ask(Query(
        text="explain", lang="he", intent=Intent.EXPLAIN, commentator_ids=["sforno"],
        named_refs=["Genesis.1.1"],
    ))
    assert answer.no_source and not answer.citations
    assert "ספורנו" in answer.text or "sforno" in answer.text


def test_partial_missing_adds_note(pipeline):
    answer = pipeline.ask(Query(
        text="בראשית ברא רש\"י וספורנו", lang="he", intent=Intent.COMPARE,
        commentator_ids=["rashi", "sforno"], named_refs=["Genesis.1.1"],
    ))
    assert answer.grounded
    assert any("sforno" in c or "ספורנו" in c for c in answer.caveats), \
        "partially-missing commentator must be noted honestly"


def test_supercommentary_on_dispute_surfaces(pipeline):
    """T033a: link expansion (depth 2) reaches Mizrachi, who explains Rashi's comment."""
    q = pipeline.router.route(Query(text="מה המחלוקת בין רש\"י לרמב\"ן על בראשית 1:1?", lang="he"))
    assert q.expand_links and q.expand_depth >= 2
    result = pipeline.retriever.retrieve(q, top_k=8)
    ids = {h.chunk_id for h in result.hits}
    assert "Mizrachi.Genesis.1.1" in ids, \
        "supercommentary anchored on Rashi's comment must surface via the anchor chain"


def test_no_commentator_answer_text_languages():
    he = grounded.no_commentator_answer("he", ["rashi"], Intent.EXPLAIN)
    en = grounded.no_commentator_answer("en", ["rashi"], Intent.EXPLAIN)
    assert he.no_source and en.no_source
    assert "rashi" in he.text and "rashi" in en.text
