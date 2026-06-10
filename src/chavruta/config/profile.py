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
    collection: str = "chavruta"

    # ── Retrieval ──
    top_k: int = 8
    hybrid: bool = True                       # dense + sparse via RRF
    rerank: bool = False                      # heavy cross-encoder; on in cloud, optional local
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    relevance_threshold: float = 0.3          # below this → no grounded source

    # ── Generation (LLM) — the dual-model strategy lives here ──
    llm_backend: str = "ollama"               # "ollama" (local) | "nebius" (cloud)
    llm_model: str = "dictalm2.0-instruct:q4_k_m"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""                     # for the cloud backend
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

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
        p.collection = _env("CHAVRUTA_COLLECTION", p.collection)
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
        return p


def _local_preset() -> Profile:
    """Offline personal machine: CPU, small Hebrew model via Ollama, embedded Qdrant."""
    return Profile(
        name="local",
        embedding_device="cpu",
        qdrant_mode="embedded",
        rerank=False,                         # keep RAM budget on the laptop
        llm_backend="ollama",
        llm_model="dictalm2.0-instruct:q4_k_m",
        llm_base_url="http://localhost:11434",
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
        llm_model=_env("CHAVRUTA_LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
        llm_base_url=_env("CHAVRUTA_LLM_BASE_URL", "https://api.studio.nebius.ai/v1"),
        llm_api_key=_env("CHAVRUTA_LLM_API_KEY", _env("NEBIUS_API_KEY", "")),
    )
