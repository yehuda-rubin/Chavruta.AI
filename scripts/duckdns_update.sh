#!/usr/bin/env bash
# Chavruta.AI — keep chavruta.duckdns.org pointed at this VM's current public IP.
#
# Fallback ONLY for an instance that does NOT have an Oracle Reserved Public IP
# (see docs/DEPLOY_ORACLE.md §4). Without either of those, a reboot's new ephemeral
# IP silently breaks the domain until someone notices.
#
# Setup:
#   1. Add DUCKDNS_TOKEN=<your token, from the DuckDNS domains page> to .env (gitignored —
#      the token never goes in this script or in git).
#   2. crontab -e, add:
#        */5 * * * * /path/to/chavruta/scripts/duckdns_update.sh >> /var/log/duckdns.log 2>&1

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

DOMAIN="chavruta"   # subdomain part only — i.e. chavruta.duckdns.org

if [[ ! -f .env ]]; then
  echo "error: .env not found. Set DUCKDNS_TOKEN there — see .env.example." >&2
  exit 1
fi
token="$(sed -nE 's/^[[:space:]]*DUCKDNS_TOKEN=[[:space:]]*"?([^"]+)"?[[:space:]]*$/\1/p' .env | head -1)"
if [[ -z "${token}" ]]; then
  echo "error: DUCKDNS_TOKEN not found in .env." >&2
  exit 1
fi

response="$(curl -fsS "https://www.duckdns.org/update?domains=${DOMAIN}&token=${token}&ip=")"
if [[ "${response}" != OK* ]]; then
  echo "duckdns update failed: ${response}" >&2
  exit 1
fi
echo "$(date -Iseconds) duckdns updated: ${response}"
