# Chavruta.AI — launch the backend in BRIDGE mode (Claude answers grounded jobs in-session; NO external LLM API).
#   docker compose --profile server up -d qdrant   # 1. Qdrant server (holds the hybrid index)
#   powershell -ExecutionPolicy Bypass -File scripts\serve_bridge.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$env:CHAVRUTA_PROFILE              = "local"
$env:CHAVRUTA_QDRANT_MODE          = "server"
$env:CHAVRUTA_QDRANT_URL           = "http://localhost:6333"
$env:CHAVRUTA_COLLECTION           = "chavruta"
$env:CHAVRUTA_EMBEDDING_DEVICE     = "cpu"
$env:CHAVRUTA_HYBRID               = "true"
$env:CHAVRUTA_RERANK               = "false"
$env:CHAVRUTA_RELEVANCE_THRESHOLD  = "0.55"
$env:CHAVRUTA_TOP_K                = "16"
$env:CHAVRUTA_QUERY_PLANNER        = "heuristic"   # no LLM planner in bridge mode
$env:CHAVRUTA_LLM_BACKEND          = "bridge"      # Claude answers pending jobs; no Nebius/external API

Write-Host "Starting Chavruta backend (BRIDGE) on http://localhost:8080 (qdrant=server, hybrid)..."
& .\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8080
