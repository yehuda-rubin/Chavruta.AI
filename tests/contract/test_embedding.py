"""Contract: EmbeddingBackend (T021) — determinism, dim, HE/EN handling."""

from __future__ import annotations

import pytest


def test_dense_length_equals_dim(fake_embedding):
    e = fake_embedding.embed_query("בראשית ברא אלהים")
    assert len(e.dense) == fake_embedding.dim


def test_deterministic(fake_embedding):
    a = fake_embedding.embed_query("the creation of light")
    b = fake_embedding.embed_query("the creation of light")
    assert a.dense == b.dense


def test_handles_hebrew_and_english(fake_embedding):
    he = fake_embedding.embed_query("מה אומר רש\"י")
    en = fake_embedding.embed_query("what does Rashi say")
    assert len(he.dense) == len(en.dense) == fake_embedding.dim


@pytest.mark.requires_llm
def test_real_bge_m3_dim_when_available():
    """Real bge-m3 conformance — runs only if FlagEmbedding + the model are present."""
    pytest.importorskip("FlagEmbedding")
    from chavruta.embedding.bge_m3 import BgeM3Embedding

    emb = BgeM3Embedding(device="cpu")
    assert emb.dim == 1024
