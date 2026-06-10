"""Integration: lesson preparation (task T037, User Story 3).

A lesson request returns a coherent structure whose every citation resolves (FR-008),
grouped per anchor and ordered along the chain — pasuk first, then commentaries (FR-008a).
"""

from __future__ import annotations

import pytest

from chavruta.config.profile import Profile
from chavruta.corpus.schema import AnchorKind, Chunk, Intent, Query, UnitType
from chavruta.pipeline.pipeline import ChavrutaPipeline
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.store.base import StoredChunk


def _seed(store, emb):
    store.ensure_collection("c", emb.dim)
    chunks = [
        Chunk(chunk_id="Jonah.3.10_pasuk", work_id="tanakh", unit_type=UnitType.SOURCE,
              ref="Jonah.3.10", lang="he",
              text="וירא האלהים את מעשיהם כי שבו מדרכם הרעה תשובה",
              text_he="וירא האלהים את מעשיהם", deep_link="l/Jonah.3.10"),
        Chunk(chunk_id="Jonah.3.10_Radak", work_id="tanakh", unit_type=UnitType.COMMENTARY,
              ref="Radak on Jonah.3.10", lang="he",
              text="רד\"ק תשובה — כי שבו מדרכם הרעה ולא אמר ומחמס אשר בכפיהם",
              text_he="כי שבו מדרכם", anchor_ref="Jonah.3.10",
              anchor_kind=AnchorKind.SOURCE, commentator_id="radak", deep_link="l/radak"),
        Chunk(chunk_id="Jonah.3.8_pasuk", work_id="tanakh", unit_type=UnitType.SOURCE,
              ref="Jonah.3.8", lang="he",
              text="ויקראו אל אלהים בחזקה וישבו איש מדרכו הרעה תשובה",
              text_he="ויקראו אל אלהים בחזקה", deep_link="l/Jonah.3.8"),
    ]
    stored = []
    for c in chunks:
        e = emb.embed_query(c.text)
        stored.append(StoredChunk(chunk_id=c.chunk_id, dense=e.dense, sparse=e.sparse,
                                  payload=c.to_payload()))
    store.upsert("c", stored)


@pytest.fixture
def pipeline(store, fake_embedding, fake_llm):
    _seed(store, fake_embedding)
    profile = Profile(name="test", collection="c", top_k=8, relevance_threshold=0.0)
    retriever = HybridRetriever(fake_embedding, store, profile)
    return ChavrutaPipeline.from_backends(
        profile, embedding=fake_embedding, store=store, llm=fake_llm, retriever=retriever
    )


def test_lesson_returns_structured_plan_with_resolving_citations(pipeline):
    answer = pipeline.ask(Query(text="הכן שיעור על תשובה בספר יונה", lang="he"))
    assert answer.intent is Intent.LESSON, "lesson phrasing must route to the lesson intent"
    plan = answer.lesson_plan
    assert plan is not None and plan.sections, "a lesson carries a structured plan (FR-008)"
    for section in plan.sections:
        assert section.heading and section.source_refs
        assert section.citations, "every lesson section must be cited"
        for c in section.citations:
            assert c.chunk_id and c.ref and c.deep_link, "citations must resolve"


def test_lesson_sections_put_pasuk_before_commentary(pipeline):
    """Chain order (FR-008a): within a section the pasuk precedes its commentaries."""
    answer = pipeline.ask(Query(text="הכן שיעור על תשובה בספר יונה", lang="he"))
    section = next(s for s in answer.lesson_plan.sections if s.heading == "Jonah.3.10")
    assert section.citations[0].commentator_id is None, "pasuk first"
    assert any(c.commentator_id == "radak" for c in section.citations[1:]), "then commentary"


def test_lesson_router_enables_link_expansion(pipeline):
    q = pipeline.router.route(Query(text="Prepare a lesson on teshuva in Jonah", lang=""))
    assert q.intent is Intent.LESSON
    assert q.expand_links and q.expand_depth >= 2, \
        "lessons follow the chain of transmission across loaded corpora (T036a)"
