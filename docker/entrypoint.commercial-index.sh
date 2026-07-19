#!/bin/sh
# Start the co-located Qdrant, wait until it's ready, then run the embed+index+publish job.
set -e

# On-disk storage + snapshots under /app so a big collection doesn't fill a small root fs.
export QDRANT__STORAGE__STORAGE_PATH=/app/qdrant_storage
export QDRANT__STORAGE__SNAPSHOTS_PATH=/app/qdrant_snapshots
mkdir -p "$QDRANT__STORAGE__STORAGE_PATH" "$QDRANT__STORAGE__SNAPSHOTS_PATH"

echo "[entrypoint] starting Qdrant ${QDRANT_VERSION}…"
qdrant &
QDRANT_PID=$!

# Wait for readiness (up to ~60s).
i=0
until curl -sf http://localhost:6333/readyz >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then echo "[entrypoint] Qdrant did not become ready" >&2; exit 1; fi
  sleep 1
done
echo "[entrypoint] Qdrant ready — running the job"

python3 scripts/index_commercial_job.py
STATUS=$?

kill "$QDRANT_PID" 2>/dev/null || true
exit $STATUS
