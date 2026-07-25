#!/usr/bin/env bash
# Chavruta.AI — launch the full local backend (hybrid retrieval). Linux/macOS.
# Windows: use scripts/serve.ps1, which this mirrors. Keep the two in sync.
#
#   1. Start the Qdrant server (holds the 2.93M-point hybrid index):
#        docker compose up -d qdrant
#      It starts EMPTY on a fresh machine — load the corpus first (see docs/CORPUS.md):
#        python scripts/load_all_indexes.py && python scripts/create_payload_indexes.py
#      /ready will 503 with a reason until it has points.
#   2. Run this script:
#        ./scripts/serve.sh
#   3. Frontend (separate terminal):  cd app/frontend && npm run dev
#        -> open http://localhost:5173
#
# Retrieval runs HYBRID (dense + sparse) against the Qdrant SERVER — embedded mode cannot do
# hybrid at this scale. Generation uses the cloud API with Qwen3-235B-A22B-Instruct: a
# NON-thinking instruct model, which is why it doesn't hit the empty-content problem the older
# Qwen3 "thinking" models had under a tight token budget.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export CHAVRUTA_PROFILE="local"
export CHAVRUTA_QDRANT_MODE="server"
export CHAVRUTA_QDRANT_URL="http://localhost:6333"
export CHAVRUTA_COLLECTION="chavruta_commercial"   # the live collection (old 'chavruta' deleted 2026-07-20)
export CHAVRUTA_MEM_TIER="ssd"
export CHAVRUTA_EMBEDDING_DEVICE="cpu"
export CHAVRUTA_HYBRID="true"
export CHAVRUTA_RERANK="false"          # cross-encoder is GPU-only in practice (too slow on CPU)
export CHAVRUTA_RELEVANCE_THRESHOLD="0.0"
export CHAVRUTA_TOP_K="16"
# The LLM planner hallucinated wrong named_refs (e.g. Bava Metzia for a Sanhedrin topic), which
# scoped retrieval to the wrong tractate -> 0 sources. The heuristic is reliable.
export CHAVRUTA_QUERY_PLANNER="heuristic"
export CHAVRUTA_LLM_BACKEND="nebius"
export CHAVRUTA_LLM_BASE_URL="https://api.studio.nebius.ai/v1"
export CHAVRUTA_LLM_MODEL="Qwen/Qwen3-235B-A22B-Instruct-2507"
# Per-intent caps (qa 3000 / lesson 30000 / compare 10000) override this in the pipeline.
export CHAVRUTA_LLM_MAX_TOKENS="1024"

# Read the key from .env, so the secret is never in this script (and never in your shell history).
if [[ ! -f .env ]]; then
  echo "error: .env not found. Copy .env.example and set NEBIUS_API_KEY." >&2
  exit 1
fi
key="$(sed -nE 's/^[[:space:]]*NEBIUS_API_KEY=[[:space:]]*"?([^"]+)"?[[:space:]]*$/\1/p' .env | head -1)"
if [[ -z "${key}" ]]; then
  echo "error: NEBIUS_API_KEY not found in .env — see .env.example." >&2
  echo "       (to run with no external API instead: CHAVRUTA_LLM_BACKEND=bridge)" >&2
  exit 1
fi
export CHAVRUTA_LLM_API_KEY="${key}"

# Prefer the project venv when present, so this behaves like serve.ps1; fall back to python3.
PY="./.venv/bin/python"
[[ -x "${PY}" ]] || PY="python3"

echo "Starting Chavruta backend on http://localhost:8080 (qdrant=server, hybrid, ${CHAVRUTA_LLM_MODEL})..."
exec "${PY}" -m uvicorn app.api:app --host 127.0.0.1 --port 8080
