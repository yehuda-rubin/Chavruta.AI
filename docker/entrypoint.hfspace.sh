#!/usr/bin/env bash
# Chavruta.AI — HF Spaces (Docker SDK) single-container entrypoint.
#
# Unlike docker-compose.yml's four separate services, everything here runs in ONE container, so
# this script starts them in dependency order instead of relying on `depends_on`/healthchecks:
#   nginx (immediately, so SOMETHING answers the port right away)
#   -> qdrant -> restore the corpus (skipped if it's already there) -> payload indexes
#   -> the API (uvicorn) -> the UI (Next.js standalone server)
#
# nginx starts FIRST and stays up throughout: HF's own platform-level check that the exposed port
# is listening happens early, and a cold-start corpus restore (tens of GB) can take several minutes
# — nginx will just 502 on real requests until the backends are ready, which is fine; what matters
# is that the port itself is never simply closed.
set -euo pipefail

# /data is the one path HF Spaces mounts as a real (if ephemeral, on the free tier) writable
# volume at RUNTIME only — everything that needs to exist before Qdrant starts is created here,
# not in the Dockerfile (a build-time mkdir under /data would just be discarded).
QDRANT_STORAGE=/data/qdrant/storage
QDRANT_SNAPSHOTS=/data/qdrant/snapshots
mkdir -p "$QDRANT_STORAGE" "$QDRANT_SNAPSHOTS"

echo "[entrypoint] starting nginx (answers the port immediately, 502s until backends are up)…"
nginx -g "daemon off;" &

echo "[entrypoint] starting qdrant…"
export QDRANT__STORAGE__STORAGE_PATH="$QDRANT_STORAGE"
export QDRANT__STORAGE__SNAPSHOTS_PATH="$QDRANT_SNAPSHOTS"
export QDRANT__STORAGE__OPTIMIZERS__MEMMAP_THRESHOLD_KB="20000"
qdrant --config-path /qdrant/config/config.yaml &

echo "[entrypoint] waiting for qdrant…"
until curl -fsS http://127.0.0.1:6333/healthz > /dev/null 2>&1; do sleep 2; done
echo "[entrypoint] qdrant is up."

COLLECTION="${CHAVRUTA_COLLECTION:-chavruta_commercial}"
POINTS=$(curl -fsS "http://127.0.0.1:6333/collections/${COLLECTION}" 2>/dev/null \
         | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('points_count',0))" \
         2>/dev/null || echo 0)

if [ "${POINTS:-0}" -gt 0 ] 2>/dev/null; then
    echo "[entrypoint] '${COLLECTION}' already has ${POINTS} points (unexpected on ephemeral disk, but"
    echo "[entrypoint] harmless if it happens) — skipping restore."
else
    echo "[entrypoint] '${COLLECTION}' is empty — restoring from the HF snapshot (this is the slow part"
    echo "[entrypoint] on a cold start; a few minutes for a multi-GB download + recover)…"
    QDRANT_SNAPSHOT_DIR="$QDRANT_SNAPSHOTS" python3 scripts/restore_commercial_snapshot.py
    echo "[entrypoint] creating payload indexes (required, or ref-anchoring times out)…"
    python3 scripts/create_payload_indexes.py
fi

echo "[entrypoint] starting the API…"
CHAVRUTA_QDRANT_MODE=server CHAVRUTA_QDRANT_URL=http://127.0.0.1:6333 CHAVRUTA_COLLECTION="$COLLECTION" \
    uvicorn app.api:app --host 127.0.0.1 --port 8080 --workers 1 --proxy-headers &

echo "[entrypoint] waiting for the API…"
until curl -fsS http://127.0.0.1:8080/ready > /dev/null 2>&1; do sleep 3; done
echo "[entrypoint] API is ready."

echo "[entrypoint] starting the UI…"
(cd /web && PORT=3000 HOSTNAME=127.0.0.1 node server.js) &

echo "[entrypoint] all processes started — waiting."
wait -n
