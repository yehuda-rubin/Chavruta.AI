# Chavruta.AI — launch the full local backend (hybrid retrieval).
#
#   1. Start the Qdrant server (holds the 449k-point hybrid index):
#        docker compose --profile server up -d qdrant
#   2. Run this script:
#        powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
#   3. Frontend (separate terminal):  cd app\frontend ; npm run dev
#        → open http://localhost:5173
#
# Retrieval runs HYBRID (dense + sparse) against the Qdrant SERVER — embedded mode
# cannot do hybrid at this scale. Generation uses Nebius (Llama-3.3-70B; the default
# Qwen3 is a "thinking" model that returns empty content under a tight token budget).

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$env:CHAVRUTA_PROFILE              = "local"
$env:CHAVRUTA_QDRANT_MODE          = "server"
$env:CHAVRUTA_QDRANT_URL           = "http://localhost:6333"
$env:CHAVRUTA_COLLECTION           = "chavruta"
$env:CHAVRUTA_EMBEDDING_DEVICE     = "cpu"
$env:CHAVRUTA_HYBRID               = "true"
$env:CHAVRUTA_RERANK               = "false"  # cross-encoder is GPU-only in practice (too slow on CPU)
$env:CHAVRUTA_RELEVANCE_THRESHOLD  = "0.0"
$env:CHAVRUTA_TOP_K                = "16"
$env:CHAVRUTA_QUERY_PLANNER        = "heuristic"  # LLM planner hallucinated wrong named_refs (e.g. Bava
                                                  # Metzia for a Sanhedrin topic) which scoped retrieval to
                                                  # the wrong tractate → 0 sources. Heuristic is reliable.
$env:CHAVRUTA_LLM_BACKEND          = "nebius"
$env:CHAVRUTA_LLM_BASE_URL         = "https://api.studio.nebius.ai/v1"
$env:CHAVRUTA_LLM_MODEL            = "meta-llama/Llama-3.3-70B-Instruct"
$env:CHAVRUTA_LLM_MAX_TOKENS       = "1024"   # per-intent caps (qa 3000 / lesson 30000 / compare 10000) override this in pipeline

# Read the Nebius key from .env (keeps the secret out of this script)
$m = Select-String -Path .env -Pattern '^\s*NEBIUS_API_KEY=(.+)\s*$'
if (-not $m) { throw "NEBIUS_API_KEY not found in .env" }
$env:CHAVRUTA_LLM_API_KEY = $m.Matches[0].Groups[1].Value.Trim().Trim('"')

Write-Host "Starting Chavruta backend on http://localhost:8080 (qdrant=server, hybrid, Llama-3.3-70B)..."
& .\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8080
