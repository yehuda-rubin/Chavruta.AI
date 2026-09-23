"""Reranker (research D5) — task T017.

Optional cross-encoder reranking (bge-reranker-v2-m3): sharpens ordering when compute is
available (cloud profile by default; optional locally). Config-gated via `profile.rerank`.

Uses sentence-transformers' CrossEncoder rather than FlagEmbedding's FlagReranker: the
latter calls `tokenizer.prepare_for_model`, which current transformers removed, breaking
the slow XLM-Roberta path. CrossEncoder runs the same model on a maintained code path.
"""

from __future__ import annotations

import math
from pathlib import Path

from chavruta.retrieval.base import RankedHit


class Reranker:
    def __init__(self, model_id: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu",
                 use_fp16: bool | None = None, backend: str = "auto", onnx_path: str | None = None):
        self.model_id = model_id
        self.device = device
        self.backend = backend
        self.onnx_path = onnx_path
        self._model = None  # lazy
        self._tokenizer = None

    def _ensure(self):
        if self._model is not None or self.backend == "api" or self.model_id.startswith("@cf/"):
            return

        is_onnx = (self.backend == "onnx") or (self.onnx_path is not None) or self.model_id.endswith(".onnx")
        if is_onnx:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            model_file = self.onnx_path or self.model_id
            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._model = ort.InferenceSession(str(model_file), session_options, providers=["CPUExecutionProvider"])
            # Tokenizer from path or parent folder
            tok_path = Path(model_file).parent if Path(model_file).exists() else self.model_id
            self._tokenizer = AutoTokenizer.from_pretrained(tok_path)
            self.backend = "onnx"
        else:
            from sentence_transformers import CrossEncoder  # lazy

            self._model = CrossEncoder(self.model_id, device=self.device)
            self.backend = "torch"

    def rerank(self, query: str, hits: list[RankedHit]) -> list[RankedHit]:
        if not hits:
            return hits
        self._ensure()

        if self.backend == "api" or self.model_id.startswith("@cf/"):
            import json
            import logging
            import os
            import urllib.request

            cf_account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
            cf_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
            if not cf_token or not cf_account:
                return hits
            cf_model = self.model_id if self.model_id.startswith("@cf/") else "@cf/baai/bge-reranker-base"
            cf_url = f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/run/{cf_model}"

            to_rank = hits[:12]
            contexts = [
                {"id": str(i), "text": (getattr(h, "text", "") or "")[:1000]}
                for i, h in enumerate(to_rank)
            ]
            try:
                body = json.dumps({"query": query, "contexts": contexts}).encode("utf-8")
                req = urllib.request.Request(
                    cf_url,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {cf_token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=12.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                response_items = data.get("result", {}).get("response", [])
                for item in response_items:
                    idx = int(item["id"])
                    if 0 <= idx < len(to_rank):
                        to_rank[idx].score = float(item["score"])
                to_rank.sort(key=lambda h: h.score, reverse=True)
                hits = to_rank + hits[12:]
            except Exception as exc:
                logging.getLogger("chavruta.retrieval.rerank").warning("Cloudflare Reranker API error: %s", exc)
        elif self.backend == "onnx":
            import numpy as np

            queries = [query] * len(hits)
            passages = [h.text for h in hits]
            inputs = self._tokenizer(queries, passages, padding=True, truncation=True, max_length=256, return_tensors="np")
            onnx_inputs = {k: v.astype(np.int64) for k, v in inputs.items()}
            
            # Executed via C++ ONNX Runtime CPU kernel
            outputs = self._model.run(None, onnx_inputs)
            raw_logits = outputs[0].flatten()

            for h, s in zip(hits, raw_logits):
                neg_s = -float(s)
                if neg_s > 700:
                    h.score = 0.0
                elif neg_s < -700:
                    h.score = 1.0
                else:
                    h.score = 1.0 / (1.0 + math.exp(neg_s))
        else:
            raw = self._model.predict([(query, h.text) for h in hits])
            for h, s in zip(hits, raw):
                neg_s = -float(s)
                if neg_s > 700:
                    h.score = 0.0
                elif neg_s < -700:
                    h.score = 1.0
                else:
                    h.score = 1.0 / (1.0 + math.exp(neg_s))

        hits.sort(key=lambda h: h.score, reverse=True)
        try:
            from chavruta.llm import metering
            total_chars = len(query) + sum(len(getattr(h, "text", "") or "") for h in hits)
            metering.record(max(1, total_chars // 3), 0, model=self.model_id or "reranker")
        except Exception:
            pass
        return hits

