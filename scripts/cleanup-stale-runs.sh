#!/bin/bash
# Cron: mark any zombie `runs` row as failed. A run is a zombie when its
# python process died ungracefully (SIGKILL from TaskStop / OOM killer /
# host reboot) and the atexit handler in pipeline/events.py never got to
# run finish_run(). The row stays status='running' forever and clutters
# the dashboard.
#
# Heuristic: status='running' AND no run_events for >= 1h. Genuine work
# emits events every few seconds (download progress, render_shot done,
# etc.), so 1h of silence = dead.
#
# Crontab: */10 * * * * /home/liharr/src/youtube-clips/scripts/cleanup-stale-runs.sh
set -euo pipefail

mkdir -p "$HOME/.local/share/cron-heartbeats"

# grep returns 1 when no matches → would kill script under pipefail.
# Use awk for line counting numeric-only output without that footgun.
KILLED=$(docker exec -i traffic-monitor-db-1 \
    psql -tA -U youtube_clips -d youtube_clips <<'SQL' | awk '/^[0-9]+$/ {n++} END {print n+0}'
WITH stale AS (
  SELECT r.id
    FROM runs r
    LEFT JOIN LATERAL (
      SELECT MAX(created_at) AS last_evt
        FROM run_events WHERE run_id = r.id
    ) e ON true
   WHERE r.status = 'running'
     AND COALESCE(e.last_evt, r.started_at) < NOW() - INTERVAL '1 hour'
)
UPDATE runs
   SET status = 'failed',
       finished_at = NOW(),
       error_message = COALESCE(error_message || ' | ', '')
                       || 'watchdog: stale >=1h with no run_events (likely SIGKILL on parent process)'
 WHERE id IN (SELECT id FROM stale)
RETURNING id;
SQL
)

touch "$HOME/.local/share/cron-heartbeats/yc-cleanup-stale-runs"

if [ "$KILLED" -gt 0 ]; then
    echo "[$(date -Is)] watchdog: marked $KILLED stale runs as failed" \
        >> /home/liharr/.local/share/youtube-clips-watchdog.log
fi
