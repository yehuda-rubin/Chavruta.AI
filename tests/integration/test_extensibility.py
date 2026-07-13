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
    reg = default_registry()
    assert not reg.has("zohar")   # a work still outside the default registry

    # 1. Register a new Work (data/config) — e.g. a slice of the Zohar.
    zohar = Work(work_id="zohar", title_he="זוהר", title_en="Zohar", kind="emunah")
    reg.register(zohar)
    assert reg.has("zohar")

    # 2. Ingest it via the standard ingestion path (no new code).
    chunks = [
        Chunk(chunk_id="z1", work_id="zohar", unit_type=UnitType.SOURCE,
              ref="Zohar, Bereshit 1:1", lang="he",
              text="בריש הורמנותא דמלכא", text_he="בריש הורמנותא דמלכא"),
    ]
    profile = Profile(name="test", collection="c", top_k=5, relevance_threshold=0.0)
    n = ingest_work(zohar, FakeAdapter(chunks), ["Zohar, Bereshit 1:1"],
                    fake_embedding, store, collection="c")
    assert n == 1

    # 3. Retrieve with the UNCHANGED retriever, scoped to the new work.
    retr = HybridRetriever(fake_embedding, store, profile)
    res = retr.retrieve(Query(text="בריש הורמנותא", lang="he", work_ids=["zohar"]), top_k=5)
    assert not res.is_empty
    assert res.hits[0].work_id == "zohar"
