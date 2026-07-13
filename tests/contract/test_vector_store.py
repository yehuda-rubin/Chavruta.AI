"""Contract: VectorStore (T022) — idempotent upsert, filter isolation, fetch-by-ref.

Validated against the in-memory store, which mirrors the contract semantics that QdrantStore
must also satisfy (and is exercised by the embedded-mode test when qdrant-client is present).
"""

from __future__ import annotations

from chavruta.store.base import HybridQuery, StoredChunk


def _chunk(cid, work, ref, commentator=None, dense=None):
    return StoredChunk(
        chunk_id=cid, dense=dense or [1.0] + [0.0] * 15, sparse={},
        payload={"chunk_id": cid, "work_id": work, "ref": ref, "commentator_id": commentator,
                 "text": f"text of {ref}", "deep_link": f"link/{ref}"},
    )


def test_upsert_idempotent_by_chunk_id(store):
    store.ensure_collection("c", 16)
    store.upsert("c", [_chunk("x1", "tanakh", "Genesis 1:1")])
    store.upsert("c", [_chunk("x1", "tanakh", "Genesis 1:1")])
    assert store.count("c") == 1


def test_filter_isolation_by_work(store):
    store.ensure_collection("c", 16)
    store.upsert("c", [_chunk("a", "tanakh", "Genesis 1:1"),
                       _chunk("b", "bavli", "Berakhot 2a")])
    hits = store.search("c", HybridQuery(dense=[1.0] + [0.0] * 15), top_k=10,
                        filters={"work_id": "tanakh"})
    assert {h.payload["work_id"] for h in hits} == {"tanakh"}


def test_fetch_by_refs(store):
    store.ensure_collection("c", 16)
    store.upsert("c", [_chunk("a", "tanakh", "Genesis 1:1"),
                       _chunk("b", "tanakh", "Genesis 1:2")])
    hits = store.fetch_by_refs("c", ["Genesis 1:2"])
    assert [h.payload["ref"] for h in hits] == ["Genesis 1:2"]


def test_delete_by_filter(store):
    store.ensure_collection("c", 16)
    store.upsert("c", [_chunk("a", "tanakh", "Genesis 1:1", commentator="rashi"),
                       _chunk("b", "tanakh", "Genesis 1:1", commentator="ramban")])
    store.delete("c", {"commentator_id": "rashi"})
    assert store.count("c") == 1
