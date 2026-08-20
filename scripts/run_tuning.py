"""run_tuning.py — run tune_retrieval.py's real sweep with a from-scratch GPU embedder standing in
for chavruta.embedding.bge_m3.BgeM3Embedding.

tune_retrieval.py, hybrid.py, and bge_m3.py stay byte-for-byte untouched. What changes is WHICH CLASS
gets constructed for `embedding`: chavruta.pipeline.pipeline.build_backends() does
`from chavruta.embedding.bge_m3 import BgeM3Embedding` as a LOCAL import inside the function body (not
a module-level import cached at import time) — so replacing the name `BgeM3Embedding` inside the
chavruta.embedding.bge_m3 module's own namespace, before that function ever runs, is enough to
redirect it to gpu_embedder.py's GpuBgeM3Embedder instead. BgeM3Embedding itself is never
instantiated and never executes a single line — the real embedding work happens entirely in
gpu_embedder.py, a file with no dependency on it.

Everything else runs exactly as if tune_retrieval.py had been invoked directly: hybrid.py's
retrieve() (the actual thing being tuned — its conditional Qdrant calls, its boosts) and
tune_retrieval.py's coordinate-descent sweep, veto logic, and --state checkpointing are all the real,
unduplicated code.

USAGE — identical CLI to tune_retrieval.py, just point at this file instead:
    python scripts/run_tuning.py --pairs eval/harvested_pairs_v1.jsonl --sample 1600 --state ...
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import torch  # noqa: E402 — must precede qdrant_client on Windows (pyarrow DLL order)

from gpu_embedder import GpuBgeM3Embedder  # noqa: E402 — the new, independent file


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def _query_texts() -> list[str]:
    """Every (normalized) text the sweep will read an embedding for while it's running — used only
    to know what to pre-warm. tune_retrieval.py's own _load() is still what actually reads these
    files during scoring; this mirrors its --pairs 50/50 split + --sample cap, plus the human veto
    sets, closely enough that warming reaches everything score() will touch."""
    from chavruta.corpus.normalize import deuphemize_he  # text normalization, not embedding logic —
    # retrieve() applies this to every query before embedding it (hybrid.py:272); the cache key has
    # to match that exact string or every warmed entry is a guaranteed miss during real scoring.

    args = sys.argv[1:]
    pairs_path = ROOT / (args[args.index("--pairs") + 1] if "--pairs" in args
                         else "eval/harvested_pairs_v1.jsonl")
    sample = int(args[args.index("--sample") + 1]) if "--sample" in args else 400

    pairs = _load(pairs_path)
    cut = int(len(pairs) * 0.5)
    raw = [p["question"] for p in pairs[:cut][:sample] + pairs[cut:][:sample]]
    for name in ("eval/torah_questions_v1.jsonl", "eval/regressions_v1.jsonl",
                 "eval/user_questions_v1.jsonl"):
        raw += [p["question"] for p in _load(ROOT / name)]
    return [deuphemize_he(t) for t in raw]


def _install_embedder() -> None:
    import chavruta.embedding.bge_m3 as bge_m3_module

    bge_m3_module.BgeM3Embedding = GpuBgeM3Embedder  # see this file's module docstring


def main() -> None:
    _install_embedder()

    from chavruta.config.profile import Profile
    profile = Profile.from_env()

    # A separate warming pass, not the instance build_backends() constructs later: two objects, one
    # disk cache file (see gpu_embedder._default_cache_path) — the point is doing the FIRST embedding
    # of every unique query as one real batch, so the GPU sees parallel work instead of tune_retrieval
    # calling embed_query one text at a time on cache misses.
    warmer = GpuBgeM3Embedder(model_id=profile.embedding_model, device=profile.embedding_device,
                              use_sparse=profile.hybrid)
    warmer.warm(_query_texts())
    warmer.close()

    # run_name="__main__" makes tune_retrieval.py's own `if __name__ == "__main__":` fire exactly as
    # if it had been invoked directly — including its `raise SystemExit(main())`, which propagates
    # its real exit code out of this process.
    runpy.run_path(str(ROOT / "scripts" / "tune_retrieval.py"), run_name="__main__")


if __name__ == "__main__":
    main()
