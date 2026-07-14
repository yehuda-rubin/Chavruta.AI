"""Deployment profile + settings (Constitution Principle II).

A single `Profile`, resolved from environment, selects every backend. `local` and `cloud`
differ by configuration only — no forked code paths. Nothing else in the codebase branches
on the profile beyond backend construction (see `chavruta.pipeline`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Profile:
    """All knobs that distinguish offline-personal from cloud-product."""

    name: str = "local"                       # "local" | "cloud"

    # ── Embedding (shared model both profiles; device differs) ──
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"             # "cpu" | "cuda"

    # ── Vector store (Qdrant) ──
    qdrant_mode: str = "embedded"             # "embedded" | "server"
    qdrant_path: str = str(BASE_DIR / "data" / "qdrant")   # embedded storage path
    qdrant_url: str = ""                      # server URL (cloud)
    qdrant_api_key: str = ""                  # Qdrant Cloud API key
    collection: str = "chavruta"
    qdrant_mem_tier: str = "16gb"             # "16gb" | "32gb" | "max" — RAM budget for the index
                                              # (quantization + on-disk; see store.MEM_TIERS)

    # ── Retrieval ──
    top_k: int = 8
    hybrid: bool = True                       # dense + sparse via RRF
    rerank: bool = False                      # heavy cross-encoder; on in cloud, optional local
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    relevance_threshold: float = 0.5          # min DENSE cosine to be "relevant" (bge-m3 in-corpus ≈0.60–0.70,
    #                                           off-corpus ≈0.47–0.58); server may tighten via env (we use 0.55)

    # ── Generation (LLM) — two backends: "nebius" (the API, DEFAULT) | "bridge" (Claude in-session).
    # The local DictaLM/Ollama backend was removed (product decision 2026-07-13). ──
    llm_backend: str = "nebius"
    llm_model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"
    llm_base_url: str = "https://api.studio.nebius.ai/v1"
    llm_api_key: str = ""                     # the API key (CHAVRUTA_LLM_API_KEY or NEBIUS_API_KEY)
    llm_temperature: float = 0.2
    llm_max_tokens: int = 512                 # bounds CPU generation latency; config-tunable

    # ── Query understanding (spec 002) ──
    query_planner: str = "none"               # "none" (heuristic only) | "llm" (LLM fallback)

    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Profile":
        """Resolve the active profile from environment variables.

        CHAVRUTA_PROFILE selects the preset (local/cloud); individual CHAVRUTA_* vars
        override any field.
        """
        name = _env("CHAVRUTA_PROFILE", "local").lower()
        p = _cloud_preset() if name == "cloud" else _local_preset()

        # Per-field overrides (apply to either preset)
        p.embedding_model = _env("CHAVRUTA_EMBEDDING_MODEL", p.embedding_model)
        p.embedding_device = _env("CHAVRUTA_EMBEDDING_DEVICE", p.embedding_device)
        p.qdrant_mode = _env("CHAVRUTA_QDRANT_MODE", p.qdrant_mode)
        p.qdrant_path = _env("CHAVRUTA_QDRANT_PATH", p.qdrant_path)
        p.qdrant_url = _env("CHAVRUTA_QDRANT_URL", p.qdrant_url)
        p.qdrant_api_key = _env("CHAVRUTA_QDRANT_API_KEY", p.qdrant_api_key)
        p.collection = _env("CHAVRUTA_COLLECTION", p.collection)
        p.qdrant_mem_tier = _env("CHAVRUTA_MEM_TIER", p.qdrant_mem_tier)
        p.top_k = int(_env("CHAVRUTA_TOP_K", str(p.top_k)))
        p.hybrid = _env_bool("CHAVRUTA_HYBRID", p.hybrid)
        p.rerank = _env_bool("CHAVRUTA_RERANK", p.rerank)
        p.rerank_model = _env("CHAVRUTA_RERANK_MODEL", p.rerank_model)
        p.relevance_threshold = float(_env("CHAVRUTA_RELEVANCE_THRESHOLD", str(p.relevance_threshold)))
        p.llm_backend = _env("CHAVRUTA_LLM_BACKEND", p.llm_backend)
        p.llm_model = _env("CHAVRUTA_LLM_MODEL", p.llm_model)
        p.llm_base_url = _env("CHAVRUTA_LLM_BASE_URL", p.llm_base_url)
        p.llm_api_key = _env("CHAVRUTA_LLM_API_KEY", p.llm_api_key)
        p.llm_temperature = float(_env("CHAVRUTA_LLM_TEMPERATURE", str(p.llm_temperature)))
        p.llm_max_tokens = int(_env("CHAVRUTA_LLM_MAX_TOKENS", str(p.llm_max_tokens)))
        p.query_planner = _env("CHAVRUTA_QUERY_PLANNER", p.query_planner)
        return p


def _local_preset() -> Profile:
    """Personal machine: local CPU embedding + local Qdrant, generation via the Nebius API (default).
    The local DictaLM/Ollama backend was removed — set CHAVRUTA_LLM_BACKEND=bridge for the no-API
    (Claude in-session) path instead."""
    return Profile(
        name="local",
        embedding_device="cpu",
        # Local Qdrant SERVER in Docker (docker compose up -d) — real HNSW indexes → ms queries.
        # No Docker? CHAVRUTA_QDRANT_MODE=embedded falls back to the in-process store.
        qdrant_mode="server",
        qdrant_url="http://localhost:6333",
        # Dense-only queries locally (measured trade-off): hybrid adds +0.9pp retrieval
        # but needs FlagEmbedding in RAM (~4.6GB vs ~2GB ST). The hybrid-indexed
        # collection serves both; CHAVRUTA_HYBRID=true flips it on (eval gate / cloud).
        hybrid=False,
        rerank=False,                         # keep RAM budget on the laptop
        llm_backend="nebius",                 # the API is the default, even locally
        llm_model=_env("CHAVRUTA_LLM_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
        llm_base_url=_env("CHAVRUTA_LLM_BASE_URL", "https://api.studio.nebius.ai/v1"),
        llm_api_key=_env("CHAVRUTA_LLM_API_KEY", _env("NEBIUS_API_KEY", "")),
    )


def _cloud_preset() -> Profile:
    """Scalable product: GPU embedding, Qdrant server, stronger serverless model via Nebius."""
    return Profile(
        name="cloud",
        embedding_device=_env("CHAVRUTA_EMBEDDING_DEVICE", "cuda"),
        qdrant_mode="server",
        qdrant_url=_env("CHAVRUTA_QDRANT_URL", "http://localhost:6333"),
        rerank=True,                          # compute available — sharpen ranking
        llm_backend="nebius",
        llm_model=_env("CHAVRUTA_LLM_MODEL", "Qwen/Qwen3-32B"),
        llm_base_url=_env("CHAVRUTA_LLM_BASE_URL", "https://api.studio.nebius.ai/v1"),
        llm_api_key=_env("CHAVRUTA_LLM_API_KEY", _env("NEBIUS_API_KEY", "")),
    )
