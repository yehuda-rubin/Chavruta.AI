"""Integration: the qa path end-to-end (task T031, User Story 1).

Covers: grounded happy path with resolving citations, honest no-source (never fabricate),
HE/EN parity reaching the same source, and the answer quoting Hebrew source text (FR-012).
Runs on the in-memory fakes — no models, no corpus, no LLM required.
"""

from __future__ import annotations

import pytest

from chavruta.config.profile import Profile
from chavruta.corpus.schema import AnchorKind, Chunk, Intent, Query, UnitType
from chavruta.pipeline.pipeline import ChavrutaPipeline
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.store.base import StoredChunk

HE_VERSE = "וַיֹּאמֶר אֱלֹהִים יְהִי אוֹר וַיְהִי אוֹר"


def _seed_corpus(store, emb):
    store.ensure_collection("c", emb.dim)
    chunks = [
        Chunk(chunk_id="Genesis.1.3_pasuk", work_id="tanakh", unit_type=UnitType.SOURCE,
              ref="Genesis.1.3", lang="he",
              text=f"Genesis 1:3 {HE_VERSE} God said let there be light",
              text_he=HE_VERSE, text_en="God said, Let there be light",
              deep_link="https://www.sefaria.org/Genesis.1.3"),
        Chunk(chunk_id="Genesis.1.3_Rashi", work_id="tanakh", unit_type=UnitType.COMMENTARY,
              ref="Rashi on Genesis.1.3", lang="he",
              text="רש\"י יהי אור — ראה שאין העולם כדאי להשתמש באור וגנזו לצדיקים",
              text_he="ראה שאין העולם כדאי", anchor_ref="Genesis.1.3",
              anchor_kind=AnchorKind.SOURCE, commentator_id="rashi",
              deep_link="https://www.sefaria.org/Rashi_on_Genesis.1.3"),
    ]
    stored = []
    for c in chunks:
        e = emb.embed_query(c.text)
        stored.append(StoredChunk(chunk_id=c.chunk_id, dense=e.dense, sparse=e.sparse,
                                  payload=c.to_payload()))
    store.upsert("c", stored)


@pytest.fixture
def pipeline(store, fake_embedding, fake_llm):
    _seed_corpus(store, fake_embedding)
    profile = Profile(name="test", collection="c", top_k=5, relevance_threshold=0.0)
    retriever = HybridRetriever(fake_embedding, store, profile)
    return ChavrutaPipeline.from_backends(
        profile, embedding=fake_embedding, store=store, llm=fake_llm, retriever=retriever
    )


def test_grounded_happy_path(pipeline):
    answer = pipeline.ask(Query(text="God said let there be light", lang="en"))
    assert answer.grounded and not answer.no_source
    assert answer.citations, "every grounded answer carries resolving citations (FR-001)"
    for c in answer.citations:
        assert c.ref and c.deep_link and c.chunk_id   # resolvable (Principle I)


def test_honest_no_source(store, fake_embedding, fake_llm):
    """Out-of-corpus question → honest empty state, nothing fabricated (FR-003/SC-002)."""
    store.ensure_collection("empty", fake_embedding.dim)
    profile = Profile(name="test", collection="empty", top_k=5, relevance_threshold=0.0)
    retriever = HybridRetriever(fake_embedding, store, profile)
    p = ChavrutaPipeline.from_backends(
        profile, embedding=fake_embedding, store=store, llm=fake_llm, retriever=retriever
    )
    answer = p.ask(Query(text="What does the Mishnah say about Shabbat candles?", lang="en"))
    assert answer.no_source and not answer.grounded and answer.citations == []


def test_bilingual_parity_same_source(pipeline):
    """HE and EN forms of one question reach the same underlying source (FR-011).

    Parity is measured on the retrieval anchors (the pesukim the answer hangs on) —
    a commentary hit and a pasuk hit on the same verse are the same underlying source.
    """
    he = pipeline.retriever.retrieve(Query(text="ויאמר אלהים יהי אור", lang="he"), top_k=5)
    en = pipeline.retriever.retrieve(Query(text="God said let there be light", lang="en"), top_k=5)
    assert set(he.anchor_refs) & set(en.anchor_refs), \
        "expected overlapping anchor pesukim across languages"


def test_answer_language_matches_question(pipeline):
    he = pipeline.ask(Query(text="ויאמר אלהים יהי אור", lang=""))
    assert any("א" <= ch <= "ת" for ch in he.text), "Hebrew question → Hebrew answer (FR-010)"


def test_hebrew_source_quoted(pipeline):
    """The cited material carries the Hebrew source text (FR-012)."""
    answer = pipeline.ask(Query(text="ויאמר אלהים יהי אור", lang="he"))
    assert answer.citations
    assert any(any("א" <= ch <= "ת" for ch in c.quote) for c in answer.citations), \
        "citation quotes must include the Hebrew source"


def test_intent_autodetection_routes_compare(pipeline):
    q = Query(text="מה המחלוקת בין רש\"י לרמב\"ן על בראשית?", lang="")
    routed = pipeline.router.route(q)
    assert routed.intent is Intent.COMPARE
    assert set(routed.commentator_ids or []) >= {"rashi", "ramban"}
