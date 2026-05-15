#!/bin/bash
# Cron: every minute, atomically claim one approved draft job and run
# Phase 2 (produce-render.py) for it. Single-threaded by design — we
# don't want two Doubao calls running concurrently and burning quota.
#
# Approve flow: web sets jobs.script_approved_at=NOW(). This script's
# UPDATE…RETURNING (with `script_approved_at IS NOT NULL`) flips status
# to 'rendering' atomically, so a concurrent cron tick won't re-claim
# the same row.
#
# Crontab: * * * * * /home/liharr/src/youtube-clips/scripts/dispatch-renders.sh
set -euo pipefail

# Single-flight: at most one renderer at a time (Doubao quota).
LOCK=/tmp/youtube-clips-dispatch-renders.lock
exec 9>"$LOCK"
if ! flock -n 9; then
    # Another invocation is already running. Heartbeat still ticks so
    # /status doesn't show this cron as dead.
    mkdir -p "$HOME/.local/share/cron-heartbeats"
    touch "$HOME/.local/share/cron-heartbeats/yc-dispatch-renders"
    exit 0
fi

# set -a so sourced vars are exported into the python child process,
# not just kept in this shell's local scope.
set -a
. ~/.config/youtube-clips.env
set +a
cd /home/liharr/src/youtube-clips

# psql -tA prints tuple rows AND the trailing command tag ("UPDATE 1") on
# stdout — filter to just the numeric id row, else we feed "UPDATE 0" or
# "36\nUPDATE 1" into --job-id and produce-original.py barfs.
JOB_ID=$(docker exec -i traffic-monitor-db-1 \
    psql -tA -U youtube_clips -d youtube_clips <<'SQL' | grep -E '^[0-9]+$' | head -n1
WITH claimed AS (
  SELECT id FROM jobs
  WHERE status = 'script_draft'
    AND script_approved_at IS NOT NULL
  ORDER BY script_approved_at ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE jobs
   SET status = 'rendering',
       started_at = NOW()
 WHERE id IN (SELECT id FROM claimed)
RETURNING id;
SQL
)

mkdir -p "$HOME/.local/share/cron-heartbeats"
touch "$HOME/.local/share/cron-heartbeats/yc-dispatch-renders"

if [ -z "$JOB_ID" ]; then
    exit 0
fi

echo "[$(date -Is)] dispatching render for job $JOB_ID" >> /home/liharr/.local/share/youtube-clips-render.log
.venv/bin/python scripts/produce-render.py --job-id "$JOB_ID" \
    >> /home/liharr/.local/share/youtube-clips-render.log 2>&1 || true
