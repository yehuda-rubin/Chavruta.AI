#!/usr/bin/env bash
# Daily backup of chavruta.db (the chavruta_db volume) to Nebius Object Storage (S3-compatible).
# This is the WHOLE sqlite file, not just chat history — sessions/messages, saved_lessons,
# usage_events (usage telemetry, incl. concurrency), accounts, coupons, billing_ledger etc. all
# live in this one file (see app/db.py), so one full-file backup covers all of them together;
# there is nothing app-data-related left uncovered by this script.
# The corpus (qdrant_storage volume) is deliberately NOT included here — it's already backed up on
# HF (see commercial-corpus-on-hf.md) and barely changes day to day; re-uploading 17GB+ on a daily
# cron would waste storage/egress for no benefit. Back the corpus up manually, only when it's
# actually updated (see docs/DEPLOY_NEBIUS.md).
#
# Requires on the host: docker, awscli (`apt install awscli` or `pip install awscli`), and an
# ~/.aws/credentials [default] profile holding a Nebius Object Storage static access key/secret
# (console: IAM -> Service accounts -> Access keys). Never put those keys in this repo.
#
# Run via cron, e.g.: 0 3 * * * CHAVRUTA_BACKUP_BUCKET=... CHAVRUTA_BACKUP_S3_ENDPOINT=... /path/to/backup_chat_db.sh
set -euo pipefail

CONTAINER="${CHAVRUTA_API_CONTAINER:-chavruta-api}"
BUCKET="${CHAVRUTA_BACKUP_BUCKET:?set CHAVRUTA_BACKUP_BUCKET (Object Storage bucket name)}"
ENDPOINT="${CHAVRUTA_BACKUP_S3_ENDPOINT:?set CHAVRUTA_BACKUP_S3_ENDPOINT (e.g. https://storage.eu-north1.nebius.cloud)}"
RETAIN="${CHAVRUTA_BACKUP_RETAIN_DAYS:-30}"
DATE="$(date -u +%F)"
REMOTE_KEY="chavruta-db/chavruta_$DATE.db"
LOCAL_TMP="/tmp/chavruta_backup_$DATE.db"

# sqlite3's own .backup API gives a consistent snapshot even while the WAL-mode DB is being
# written to concurrently by the running app — a plain file copy could grab a half-committed page.
# Runs inside the api container (python3 + stdlib sqlite3 are always there; no extra tooling needed).
docker exec "$CONTAINER" python3 -c "
import sqlite3
src = sqlite3.connect('/app-data/chavruta.db')
dst = sqlite3.connect('/tmp/chavruta_backup.db')
src.backup(dst)
dst.close()
src.close()
"
docker cp "$CONTAINER:/tmp/chavruta_backup.db" "$LOCAL_TMP"
docker exec "$CONTAINER" rm -f /tmp/chavruta_backup.db

aws --endpoint-url "$ENDPOINT" s3 cp "$LOCAL_TMP" "s3://$BUCKET/$REMOTE_KEY"
rm -f "$LOCAL_TMP"

# Retention: keep only the last N daily backups so storage doesn't grow unbounded.
aws --endpoint-url "$ENDPOINT" s3 ls "s3://$BUCKET/chavruta-db/" \
  | awk '{print $4}' | sed '/^$/d' | sort | head -n "-$RETAIN" \
  | while read -r old; do
      aws --endpoint-url "$ENDPOINT" s3 rm "s3://$BUCKET/chavruta-db/$old"
    done

echo "backed up chavruta.db -> s3://$BUCKET/$REMOTE_KEY"
