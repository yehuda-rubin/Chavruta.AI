"""Unit tests for Reranker ONNX and PyTorch paths."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from chavruta.retrieval.base import RankedHit
from chavruta.retrieval.rerank import Reranker


def test_reranker_empty_hits():
    reranker = Reranker()
    hits = []
    res = reranker.rerank("שאלה", hits)
    assert res == []


def test_reranker_torch_mock():
    mock_model = MagicMock()
    mock_model.predict.return_value = [2.5, -1.0]

    with patch("sentence_transformers.CrossEncoder", return_value=mock_model):
        reranker = Reranker(backend="torch")
        hits = [
            RankedHit(chunk_id="c1", ref="Genesis.1.1", text="בראשית ברא", score=0.0),
            RankedHit(chunk_id="c2", ref="Genesis.1.2", text="והארץ הייתה תהו", score=0.0)
        ]
        res = reranker.rerank("בראשית", hits)
        assert len(res) == 2
        # Highest score should be first
        assert res[0].chunk_id == "c1"
        assert res[0].score > res[1].score


def test_reranker_onnx_mock():
    mock_session = MagicMock()

    # Raw logits from ONNX run: [3.0, -2.0]
    import numpy as np
    mock_session.run.return_value = [np.array([[3.0], [-2.0]])]

    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": np.array([[1, 2], [3, 4]]),
        "attention_mask": np.array([[1, 1], [1, 1]])
    }

    with patch("onnxruntime.InferenceSession", return_value=mock_session), \
         patch("transformers.AutoTokenizer.from_pretrained", return_value=mock_tokenizer):

        reranker = Reranker(backend="onnx", onnx_path="fake_model.onnx")
        hits = [
            RankedHit(chunk_id="c1", ref="Bava_Metzia.2a", text="שניים אוחזין", score=0.0),
            RankedHit(chunk_id="c2", ref="Bava_Metzia.2b", text="זה אומר אני מצאתיה", score=0.0)
        ]
        res = reranker.rerank("שניים אוחזין", hits)
        assert len(res) == 2
        assert res[0].chunk_id == "c1"
        # Sigmoid of 3.0: 1 / (1 + exp(-3)) ≈ 0.9525
        assert math.isclose(res[0].score, 1.0 / (1.0 + math.exp(-3.0)), abs_tol=1e-3)
