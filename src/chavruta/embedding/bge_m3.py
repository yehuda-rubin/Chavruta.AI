"""BgeM3Embedding — bge-m3 dense + learned-sparse embeddings (research D3).

Multilingual (HE/EN) so a Hebrew question and its English translation land near the same
source. Emits both dense and sparse vectors, which feed hybrid retrieval (D5). The heavy
model is imported lazily so the module can be imported without FlagEmbedding installed
(tests substitute a fake EmbeddingBackend).
"""

from __future__ import annotations

from chavruta.embedding.base import Embedding


class BgeM3Embedding:
    dim = 1024

    def __init__(self, model_id: str = "BAAI/bge-m3", device: str = "cpu",
                 max_length: int = 512, use_fp16: bool | None = None):
        self.model_id = model_id
        self.device = device
        self.max_length = max_length
        self._use_fp16 = (device != "cpu") if use_fp16 is None else use_fp16
        self._model = None  # lazy

    def _ensure_model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel  # heavy; imported on first use

            self._model = BGEM3FlagModel(
                self.model_id, use_fp16=self._use_fp16, device=self.device
            )
        return self._model

    def _encode(self, texts: list[str]) -> list[Embedding]:
        model = self._ensure_model()
        out = model.encode(
            texts,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense = out["dense_vecs"]
        sparse_weights = out["lexical_weights"]
        embeddings: list[Embedding] = []
        for i in range(len(texts)):
            sparse = {int(tok): float(w) for tok, w in dict(sparse_weights[i]).items()}
            embeddings.append(Embedding(dense=[float(x) for x in dense[i]], sparse=sparse))
        return embeddings

    def embed_query(self, text: str) -> Embedding:
        return self._encode([text])[0]

    def embed_batch(self, texts: list[str]) -> list[Embedding]:
        if not texts:
            return []
        return self._encode(texts)
