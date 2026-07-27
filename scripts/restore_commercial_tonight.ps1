<#
  restore_commercial_tonight.ps1
  Finish loading the commercial RAG into the local Qdrant the RAM-safe way.

  Why this exists: uploading the 17 GB snapshot over HTTP (restore_commercial_snapshot.py)
  buffers the whole file inside Qdrant's request pipeline and, on a 15.7 GB machine, drives it
  into swap. This script instead recovers from a LOCAL FILE already copied into the container,
  so Qdrant streams it from disk. Run it when the machine is idle.

  Idempotent: copies the snapshot into the container only if missing, recovers, then verifies count.
  ASCII-only on purpose (Windows PowerShell 5.1 mis-parses UTF-8 dashes/quotes without a BOM).

  Usage:
      powershell -ExecutionPolicy Bypass -File scripts\restore_commercial_tonight.ps1
#>
$ErrorActionPreference = "Stop"
$QDRANT     = "http://localhost:6333"
$COLL       = "chavruta_commercial"
$CONTAINER  = "chavruta-qdrant"
$SNAP_IN    = "/qdrant/snapshots/chavruta_commercial/chavruta_commercial.snapshot"
$HOST_SNAP  = "C:\Users\rubin\.cache\huggingface\hub\datasets--Yehuda-Rubin--chavruta-commercial-index\snapshots\67d1693887bb964e992fd1dd04992c50d33ee6b3\snapshots\chavruta_commercial-7696045650165295-2026-07-19-15-42-49.snapshot"

function Log($m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $m) }

# 1) Docker daemon up?
Log "checking Docker..."
try { docker info *> $null } catch {
  Log "Docker not running - launching Docker Desktop, waiting up to 5 min..."
  Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  $t = Get-Date
  do { Start-Sleep 8; $ok = $false; try { docker info *> $null; $ok = $true } catch {} }
  until ($ok -or ((Get-Date)-$t).TotalMinutes -gt 5)
  if (-not $ok) { throw "Docker did not start in time." }
}
Log "Docker OK."

# 2) Start Qdrant
Log "starting Qdrant container..."
docker compose start qdrant 2>$null
if (-not $?) { docker compose up -d qdrant | Out-Null }

# 3) Wait until ready (only chavruta_templates loads now, so this is fast)
Log "waiting for Qdrant readyz..."
$t = Get-Date
do {
  Start-Sleep 5
  try { $code = (Invoke-WebRequest "$QDRANT/readyz" -UseBasicParsing -TimeoutSec 5).StatusCode } catch { $code = 0 }
} until ($code -eq 200 -or ((Get-Date)-$t).TotalMinutes -gt 10)
if ($code -ne 200) { throw "Qdrant not ready in time." }
Log "Qdrant ready."

# Already loaded? (idempotent)
try {
  $info = Invoke-RestMethod "$QDRANT/collections/$COLL"
  if ($info.result.points_count -gt 0) { Log ("Already loaded: {0} points. Nothing to do." -f $info.result.points_count); exit 0 }
} catch { }

# 4) Ensure the snapshot file is inside the container (copy only if missing)
$have = (docker exec $CONTAINER sh -c "test -f $SNAP_IN && echo yes || echo no").Trim()
if ($have -ne "yes") {
  Log "snapshot missing in container - copying 17 GB (one-time, about 25 min)..."
  docker exec $CONTAINER sh -c "mkdir -p /qdrant/snapshots/chavruta_commercial" | Out-Null
  if (-not (Test-Path $HOST_SNAP)) { throw "Host snapshot not found: $HOST_SNAP" }
  docker cp $HOST_SNAP "${CONTAINER}:${SNAP_IN}"
  Log "copy done."
} else { Log "snapshot already present in container." }

# 5) Recover from the LOCAL file (RAM-safe)
Log "recovering collection from local file (the light step; a few minutes)..."
$body = @{ location = "file://$SNAP_IN"; priority = "snapshot" } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$QDRANT/collections/$COLL/snapshots/recover" -ContentType "application/json" -Body $body -TimeoutSec 3600 | Out-Null

# 6) Verify
$info = Invoke-RestMethod "$QDRANT/collections/$COLL"
Log ("DONE - {0} points, status={1}" -f $info.result.points_count, $info.result.status)
Log "Next: verify citations; serve.ps1/.env already point at $COLL."
