"""Contract: Retriever (T024) — scoping, commentator filtering, out-of-corpus → is_empty."""

from __future__ import annotations

from chavruta.config.profile import Profile
from chavruta.corpus.schema import AnchorKind, Chunk, Query, UnitType
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.store.base import StoredChunk


def _profile():
    return Profile(name="test", collection="c", top_k=5, hybrid=True, rerank=False,
                   relevance_threshold=0.0)


def _seed(store, emb, chunks: list[Chunk]):
    store.ensure_collection("c", emb.dim)
    stored = []
    for c in chunks:
        e = emb.embed_query(c.text)
        stored.append(StoredChunk(chunk_id=c.chunk_id, dense=e.dense, sparse=e.sparse,
                                  payload=c.to_payload()))
    store.upsert("c", stored)


def _commentary(cid, commentator, ref, text):
    return Chunk(chunk_id=cid, work_id="tanakh", unit_type=UnitType.COMMENTARY, ref=ref,
                 lang="he", text=text, text_he=text, anchor_ref="Genesis 1:1",
                 anchor_kind=AnchorKind.SOURCE, commentator_id=commentator)


def test_commentator_scoping(store, fake_embedding):
    _seed(store, fake_embedding, [
        _commentary("r1", "rashi", "Rashi on Genesis 1:1", "רש\"י אומר בראשית בשביל"),
        _commentary("rn1", "ramban", "Ramban on Genesis 1:1", "רמב\"ן אומר עניין הבריאה"),
    ])
    retr = HybridRetriever(fake_embedding, store, _profile())
    q = Query(text="בראשית", lang="he", commentator_ids=["rashi"])
    res = retr.retrieve(q, top_k=5)
    assert not res.is_empty
    assert all(h.commentator_id == "rashi" for h in res.hits)


def test_work_scoping(store, fake_embedding):
    _seed(store, fake_embedding, [
        Chunk(chunk_id="t1", work_id="tanakh", unit_type=UnitType.SOURCE,
              ref="Genesis 1:1", lang="he", text="בראשית ברא", text_he="בראשית ברא"),
        Chunk(chunk_id="b1", work_id="bavli", unit_type=UnitType.SOURCE,
              ref="Berakhot 2a", lang="he", text="מאימתי קורין", text_he="מאימתי קורין"),
    ])
    retr = HybridRetriever(fake_embedding, store, _profile())
    res = retr.retrieve(Query(text="בראשית", lang="he", work_ids=["tanakh"]), top_k=5)
    assert all(h.work_id == "tanakh" for h in res.hits)


def test_out_of_corpus_is_empty(store, fake_embedding):
    store.ensure_collection("c", fake_embedding.dim)   # empty corpus
    retr = HybridRetriever(fake_embedding, store, _profile())
    res = retr.retrieve(Query(text="anything", lang="en"), top_k=5)
    assert res.is_empty and res.hits == []
