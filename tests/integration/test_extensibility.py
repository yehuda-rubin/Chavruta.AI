"""Extensibility — SC-005 / Principle III (T024a).

Register a brand-new Work via the CorpusRegistry, ingest it through the standard ingestion
path, and retrieve it with the SAME retriever — proving corpus growth is a data/config
operation with no change to retrieval/ranking/generation code.
"""

from __future__ import annotations

import pytest

from chavruta.config.profile import Profile
from chavruta.corpus.ingest import ingest_work
from chavruta.corpus.registry import default_registry
from chavruta.corpus.schema import Chunk, Query, UnitType, Work
from chavruta.retrieval.hybrid import HybridRetriever


class FakeAdapter:
    """A minimal SourceAdapter for a hypothetical new corpus."""

    def __init__(self, chunks):
        self._chunks = chunks

    def fetch_chunks(self, work, refs=None):
        return list(self._chunks)

    def fetch_links(self, work, refs=None):
        return []


def test_add_new_work_is_data_config_only(store, fake_embedding):
    # Use a fictional work_id guaranteed absent from the (ever-growing) default registry — the point is
    # that ADDING a corpus is a data/config op, not which specific work it is.
    NEW = "sefer_test_extensibility"
    reg = default_registry()
    assert not reg.has(NEW)   # genuinely outside the default registry

    # 1. Register a new Work (data/config).
    work = Work(work_id=NEW, title_he="ספר בדיקה", title_en="Test Work", kind="emunah")
    reg.register(work)
    assert reg.has(NEW)

    # 2. Ingest it via the standard ingestion path (no new code).
    chunks = [
        Chunk(chunk_id="tn1", work_id=NEW, unit_type=UnitType.SOURCE,
              ref="Test Work 1:1", lang="he",
              text="בריש הורמנותא דמלכא", text_he="בריש הורמנותא דמלכא"),
    ]
    profile = Profile(name="test", collection="c", top_k=5, relevance_threshold=0.0)
    n = ingest_work(work, FakeAdapter(chunks), ["Test Work 1:1"],
                    fake_embedding, store, collection="c")
    assert n == 1

    # 3. Retrieve with the UNCHANGED retriever, scoped to the new work.
    retr = HybridRetriever(fake_embedding, store, profile)
    res = retr.retrieve(Query(text="בריש הורמנותא", lang="he", work_ids=[NEW]), top_k=5)
    assert not res.is_empty
    assert res.hits[0].work_id == NEW
