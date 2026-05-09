#!/usr/bin/env bash
# Bootstrap the youtube_clips Postgres role + DB inside the shared
# traffic-monitor-db-1 container, then apply schema.sql.
#
# Idempotent: safe to re-run. Reads YOUTUBE_CLIPS_PG_PASSWORD from the env
# file at /home/liharr/.config/youtube-clips.env (mode 600).
#
# Run from the repo root.
set -euo pipefail

ENV_FILE="${YOUTUBE_CLIPS_ENV_FILE:-/home/liharr/.config/youtube-clips.env}"
DB_CONTAINER="${YOUTUBE_CLIPS_DB_CONTAINER:-traffic-monitor-db-1}"
SCHEMA_FILE="$(dirname "$0")/schema.sql"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Create it with YOUTUBE_CLIPS_PG_PASSWORD=..." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

if [ -z "${YOUTUBE_CLIPS_PG_PASSWORD:-}" ]; then
  echo "ERROR: YOUTUBE_CLIPS_PG_PASSWORD not set in $ENV_FILE" >&2
  exit 1
fi

# Step 1: create role + database. Shared db container's superuser is `umami`.
docker exec -i "$DB_CONTAINER" psql -U umami -d umami <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'youtube_clips') THEN
    CREATE ROLE youtube_clips WITH LOGIN PASSWORD '${YOUTUBE_CLIPS_PG_PASSWORD}';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE youtube_clips OWNER youtube_clips'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'youtube_clips')\gexec

GRANT ALL PRIVILEGES ON DATABASE youtube_clips TO youtube_clips;
SQL

# Step 2: apply schema as the owner role.
docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" "$DB_CONTAINER" \
  psql -h localhost -U youtube_clips -d youtube_clips < "$SCHEMA_FILE"

echo "youtube_clips bootstrap complete."
