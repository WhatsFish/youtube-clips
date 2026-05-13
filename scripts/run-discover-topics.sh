#!/usr/bin/env bash
# Cron entry point for topic discovery. Runs every profile with a
# `topic_discovery` block in its config (so new profiles auto-enroll).
#
# Crontab:
#   0 9 * * * /home/liharr/src/youtube-clips/scripts/run-discover-topics.sh >>/home/liharr/src/youtube-clips/cron.log 2>&1 && touch /home/liharr/.local/share/cron-heartbeats/youtube-clips-discover-topics

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Auto-export so vars are visible to the python subprocess. Without `set -a`
# the variables only live in this shell — cron-time `python` invocations
# don't inherit them and KeyError on YOUTUBE_CLIPS_PG_PASSWORD.
set -a
# shellcheck disable=SC1091
source ~/.config/youtube-clips.env
set +a

echo "=== discover-topics $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
.venv/bin/python scripts/discover-topics.py --all
