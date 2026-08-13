#!/usr/bin/env bash
# Host-side cron entry for the nightly retrieval evaluation.
#
# Install (on the VM, as the chavruta user):
#     crontab -l 2>/dev/null | grep -v nightly_eval_cron > /tmp/ct; \
#     echo "0,30 * * * * /home/chavruta/chavruta/scripts/nightly_eval_cron.sh" >> /tmp/ct; \
#     crontab /tmp/ct
#
# Cron fires this every 30 minutes, ALL DAY, and it exits immediately outside a permitted window.
# The schedule itself lives in scripts/nightly_eval.py because it is stated in Israel local time
# while this host runs on UTC — and Israel moves between UTC+2 and UTC+3, so a cron expression with
# a baked-in offset would drift by an hour twice a year and start a heavy batch job in the evening.
# Waking often and letting the job decide is what makes the schedule survive DST untouched.
#
# The work runs INSIDE the api container: it needs bge-m3, the Qdrant client, and the same
# CHAVRUTA_* environment the service runs with. `docker exec` inherits all of that for free, and the
# CPU budget (taskset + thread caps) is applied by nightly_eval.py around each step.
set -uo pipefail

CONTAINER=chavruta-api
LOCK=/tmp/chavruta-nightly-eval.lock

# A run cut off by its window can still be finishing when the next tick arrives; a second one would
# then compete for the same cores this whole design exists to ration. flock makes overlap impossible
# and -n makes the loser exit silently rather than queue up behind it.
exec 9>"$LOCK" || exit 0
flock -n 9 || exit 0

# Nothing to do if the service is not up — this is a background chore, never a reason to page anyone.
docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true || exit 0

docker exec "$CONTAINER" python /app/scripts/nightly_eval.py >>/tmp/chavruta-nightly-eval.out 2>&1
