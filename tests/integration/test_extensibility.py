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
    assert not reg.has("mishnah")

    # 1. Register a new Work (data/config) — e.g. a slice of Mishnah.
    mishnah = Work(work_id="mishnah", title_he="משנה", title_en="Mishnah", kind="mishnah")
    reg.register(mishnah)
    assert reg.has("mishnah")

    # 2. Ingest it via the standard ingestion path (no new code).
    chunks = [
        Chunk(chunk_id="m1", work_id="mishnah", unit_type=UnitType.SOURCE,
              ref="Mishnah Berakhot 1:1", lang="he",
              text="מאימתי קורין את שמע בערבית", text_he="מאימתי קורין את שמע בערבית"),
    ]
    profile = Profile(name="test", collection="c", top_k=5, relevance_threshold=0.0)
    n = ingest_work(mishnah, FakeAdapter(chunks), ["Mishnah Berakhot 1:1"],
                    fake_embedding, store, collection="c")
    assert n == 1

    # 3. Retrieve with the UNCHANGED retriever, scoped to the new work.
    retr = HybridRetriever(fake_embedding, store, profile)
    res = retr.retrieve(Query(text="מאימתי קורין", lang="he", work_ids=["mishnah"]), top_k=5)
    assert not res.is_empty
    assert res.hits[0].work_id == "mishnah"
