#!/usr/bin/env bash
# Cron entry: run the youtube-clips pipeline agent. Phase 1 ships this as
# a stub — the agent logic is the substance of Phase 2 (topic discovery
# → source search → download → transcribe → translate → EDL → render).
#
# Mirrors the stock-analyst pattern: source env, run claude headless,
# log a cost_event row best-effort. Cost logging never masks the agent's
# exit code.
set -euo pipefail

PROJECT_DIR="/home/liharr/src/youtube-clips"
ENV_FILE="${YOUTUBE_CLIPS_ENV_FILE:-/home/liharr/.config/youtube-clips.env}"
COST_ENV="/home/liharr/.config/cost-tracker.env"
HEARTBEAT_DIR="/home/liharr/.local/share/cron-heartbeats"
HEARTBEAT_FILE="$HEARTBEAT_DIR/youtube-clips-pipeline"
AGENT_COST_USD_ESTIMATE="${AGENT_COST_USD_ESTIMATE:-1.00}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

cd "$PROJECT_DIR"

START_TS=$(date -u +%s)
START_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Phase 1 stub: nothing to run yet. Exit 0 + heartbeat so /status reports
# the cron entry as healthy once it's wired up. Phase 2 replaces this
# block with the real agent invocation.
echo "[$START_ISO] youtube-clips Phase 1 stub — pipeline lands in Phase 2."
EXIT=0

END_TS=$(date -u +%s)
DURATION_MS=$(( (END_TS - START_TS) * 1000 ))

if [ "$EXIT" -eq 0 ]; then
  mkdir -p "$HEARTBEAT_DIR"
  touch "$HEARTBEAT_FILE"
fi

# Best-effort cost-tracker logging.
if [ -f "$COST_ENV" ]; then
  set +e
  # shellcheck disable=SC1090
  source "$COST_ENV"
  METADATA="{\"started_at\":\"$START_ISO\",\"exit_code\":$EXIT,\"script\":\"youtube-clips run-agent.sh (stub)\"}"
  docker exec -e PGPASSWORD="$COST_PG_PASSWORD" "$COST_DB_CONTAINER" \
    psql -h "$COST_PG_HOST" -p "$COST_PG_PORT" -U "$COST_PG_USER" -d "$COST_PG_DB" \
    -c "INSERT INTO cost_event (service, provider, cost_usd, duration_ms, metadata) \
        VALUES ('youtube-clips-agent', 'anthropic', 0, $DURATION_MS, '$METADATA'::jsonb);" \
    > /dev/null 2>&1 || true
  set -e
fi

exit $EXIT
