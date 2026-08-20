"""gpu_embedder.py — a from-scratch BGE-M3 embedding backend with a disk-persisted cache.

Independent of chavruta.embedding.bge_m3.BgeM3Embedding: this calls FlagEmbedding's BGEM3FlagModel
directly and shares no code with that class. The only thing kept the same is the tiny data shape
hybrid.py's retrieve() reads off whatever `.embedding.embed_query()` returns (a `.dense` list and a
`.sparse` dict) — defined locally below as `Vector`, not imported — and the constructor keyword names
(model_id, device, use_sparse) that chavruta.pipeline.pipeline.build_backends() calls with, so this
class is a drop-in replacement for that slot. See run_tuning.py for how it's actually put there.

WHY A CACHE, AND WHY IT MATTERS HERE SPECIFICALLY
----------------------------------------------------
tune_retrieval.py's coordinate descent only ever changes retrieval CONSTANTS between scoring passes —
never the query text (see that file's `_apply()`). So the exact same ~1600+ queries get embedded from
scratch on every one of the ~8 scoring passes a knob makes (incumbent, carried-forward best, each
candidate, held-out before/after — see nightly_eval.py's own accounting), times 8 knobs — and again on
every fresh subprocess our kaggle/lightning bootstrap scripts launch per knob (--state). Embedding a
query is a pure function of its (normalized) text, so caching eliminates nearly all of that repeated
work for free — it changes nothing about WHAT gets computed, only how many times.

Persisted to disk, not just kept in memory, because a fresh subprocess per knob would otherwise throw
the cache away between knobs — exactly where most of the redundant embedding lives.
"""

from __future__ import annotations

import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Vector:
    dense: list[float]
    sparse: dict[int, float] = field(default_factory=dict)


def _default_cache_path() -> Path:
    """Derived from the CLI args this process was actually launched with (--state's directory if
    given, else eval/), so a warming pass and the instance build_backends() constructs later in the
    SAME process — two different objects — land on the same file without needing to be told."""
    args = sys.argv[1:]
    state = args[args.index("--state") + 1] if "--state" in args else None
    pairs = args[args.index("--pairs") + 1] if "--pairs" in args else "eval/harvested_pairs_v1.jsonl"
    root = Path(__file__).resolve().parents[1]
    base = Path(state).parent if state else (root / "eval")
    return base / (Path(pairs).stem + ".embed_cache.pkl")


class GpuBgeM3Embedder:
    dim = 1024

    def __init__(self, model_id: str = "BAAI/bge-m3", device: str = "cuda",
                 use_sparse: bool = True, max_length: int = 512,
                 cache_path: Path | str | None = None):
        self.model_id = model_id
        self.device = device
        self.use_sparse = use_sparse
        self.max_length = max_length
        self._model = None
        self._cache_path = Path(cache_path) if cache_path else _default_cache_path()
        self._cache: dict[str, Vector] = {}
        self._new_since_save = 0
        if self._cache_path.exists():
            with self._cache_path.open("rb") as f:
                self._cache = pickle.load(f)
            print(f"[gpu_embedder] loaded {len(self._cache)} cached vectors from {self._cache_path}")

    def _ensure_model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel

            print(f"[gpu_embedder] loading {self.model_id} on {self.device}…")
            self._model = BGEM3FlagModel(self.model_id, use_fp16=(self.device != "cpu"),
                                         device=self.device)
        return self._model

    def _encode(self, texts: list[str]) -> list[Vector]:
        # Always request sparse — this mirrors the "flag" path of the class it replaces, which does
        # the same regardless of use_sparse (that flag only chooses FlagEmbedding vs a dense-only
        # fallback one layer up; it never gates the call itself once FlagEmbedding is in use).
        out = self._ensure_model().encode(
            texts, max_length=self.max_length,
            return_dense=True, return_sparse=True, return_colbert_vecs=False,
        )
        dense, sparse_weights = out["dense_vecs"], out["lexical_weights"]
        return [Vector(dense=[float(x) for x in dense[i]],
                       sparse={int(tok): float(w) for tok, w in dict(sparse_weights[i]).items()})
                for i in range(len(texts))]

    def _save_cache(self) -> None:
        if self._new_since_save == 0:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cache_path.open("wb") as f:
            pickle.dump(self._cache, f)
        print(f"[gpu_embedder] saved {len(self._cache)} vectors to {self._cache_path}")
        self._new_since_save = 0

    def embed_query(self, text: str) -> Vector:
        hit = self._cache.get(text)
        if hit is not None:
            return hit
        vec = self._encode([text])[0]
        self._cache[text] = vec
        self._new_since_save += 1
        if self._new_since_save >= 200:  # periodic, not just at close() — a killed session shouldn't
            self._save_cache()           # lose a whole knob's worth of first-time embeddings
        return vec

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        if not texts:
            return []
        misses = [t for t in texts if t not in self._cache]
        if misses:
            for t, v in zip(misses, self._encode(misses)):
                self._cache[t] = v
            self._new_since_save += len(misses)
            if self._new_since_save >= 200:
                self._save_cache()
        return [self._cache[t] for t in texts]

    def warm(self, texts: list[str], batch_size: int = 1024) -> None:
        """Pre-embed everything the sweep will need, in real batches, so the GPU sees parallel work
        once instead of thousands of sequential batch-of-1 calls the first time each unique query is
        touched during scoring."""
        todo = sorted({t for t in texts if t not in self._cache})
        if not todo:
            print("[gpu_embedder] nothing to warm — every query already cached")
            return
        print(f"[gpu_embedder] warming {len(todo)} uncached queries in batches of {batch_size}")
        for i in range(0, len(todo), batch_size):
            chunk = todo[i:i + batch_size]
            for t, v in zip(chunk, self._encode(chunk)):
                self._cache[t] = v
            print(f"[gpu_embedder]   {min(i + batch_size, len(todo))}/{len(todo)}")
        self._new_since_save += len(todo)
        self._save_cache()

    def close(self) -> None:
        self._save_cache()
