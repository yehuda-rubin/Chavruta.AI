"""Profile parity (task T038, SC-006, Principle II).

The same request under the `local` and `cloud` profiles must cite the same underlying
sources — behavior is identical, only quality/latency may differ. Validated over the
shared store with two pipelines whose profiles (and LLM backends) differ.
"""

from __future__ import annotations

import pytest

from chavruta.config.profile import Profile
from chavruta.corpus.schema import AnchorKind, Chunk, Query, UnitType
from chavruta.pipeline.pipeline import ChavrutaPipeline
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.store.base import StoredChunk
from tests.conftest import FakeLLM


class CloudFakeLLM(FakeLLM):
    profile = "cloud"
    model_id = "fake-cloud-llm"


def _seed(store, emb):
    store.ensure_collection("c", emb.dim)
    chunks = [
        Chunk(chunk_id="Genesis.1.3_pasuk", work_id="tanakh", unit_type=UnitType.SOURCE,
              ref="Genesis.1.3", lang="he", text="ויאמר אלהים יהי אור ויהי אור",
              text_he="יהי אור", deep_link="l/Genesis.1.3"),
        Chunk(chunk_id="Genesis.1.3_Rashi", work_id="tanakh", unit_type=UnitType.COMMENTARY,
              ref="Rashi on Genesis.1.3", lang="he", text="רש\"י יהי אור וגנזו לצדיקים",
              text_he="וגנזו לצדיקים", anchor_ref="Genesis.1.3",
              anchor_kind=AnchorKind.SOURCE, commentator_id="rashi", deep_link="l/rashi"),
    ]
    stored = []
    for c in chunks:
        e = emb.embed_query(c.text)
        stored.append(StoredChunk(chunk_id=c.chunk_id, dense=e.dense, sparse=e.sparse,
                                  payload=c.to_payload()))
    store.upsert("c", stored)


def _pipeline(profile_name: str, store, emb, llm):
    profile = Profile(name=profile_name, collection="c", top_k=5, relevance_threshold=0.0)
    retriever = HybridRetriever(emb, store, profile)
    return ChavrutaPipeline.from_backends(
        profile, embedding=emb, store=store, llm=llm, retriever=retriever
    )


def test_local_and_cloud_cite_the_same_sources(store, fake_embedding, fake_llm):
    _seed(store, fake_embedding)
    local = _pipeline("local", store, fake_embedding, fake_llm)
    cloud = _pipeline("cloud", store, fake_embedding, CloudFakeLLM())

    q = "ויאמר אלהים יהי אור"
    a_local = local.ask(Query(text=q, lang="he"))
    a_cloud = cloud.ask(Query(text=q, lang="he"))

    assert a_local.grounded and a_cloud.grounded
    assert {c.chunk_id for c in a_local.citations} == {c.chunk_id for c in a_cloud.citations}, \
        "profiles must cite the same sources (SC-006) — only the model differs"


def test_retrieval_identical_across_profiles(store, fake_embedding, fake_llm):
    _seed(store, fake_embedding)
    local = _pipeline("local", store, fake_embedding, fake_llm)
    cloud = _pipeline("cloud", store, fake_embedding, CloudFakeLLM())

    q = Query(text="יהי אור", lang="he")
    r_local = local.retriever.retrieve(q, top_k=5)
    r_cloud = cloud.retriever.retrieve(q, top_k=5)
    assert [h.chunk_id for h in r_local.hits] == [h.chunk_id for h in r_cloud.hits], \
        "retrieval is profile-independent (Principle II)"
