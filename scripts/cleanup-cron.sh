#!/usr/bin/env bash
# Daily cleanup. Drops yt-dlp downloads older than 7 days from
# /video/youtube-clips/raw/. Outputs (rendered mp4s, EDL JSON) are kept
# indefinitely — they're cheap and the operator may want to re-render
# from the same EDL later.
#
# Touches a heartbeat file on success so /status (host-disk-video and
# the cron group) can see the sweep ran.
#
# Run via cron — the entry includes the heartbeat touch:
#   30 5 * * * /home/liharr/src/youtube-clips/scripts/cleanup-cron.sh \
#     && touch /home/liharr/.local/share/cron-heartbeats/youtube-clips-cleanup
set -euo pipefail

RAW_DIR="/video/youtube-clips/raw"
RAW_TTL_DAYS="${RAW_TTL_DAYS:-7}"

[ -d "$RAW_DIR" ] || exit 0

# Per-video subdir is what yt-dlp writes into. Drop the whole subdir if
# its source.mp4 is older than the TTL — half-deleted dirs would still
# look populated to the next run, masking the real state.
find "$RAW_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' dir; do
  src="$dir/source.mp4"
  if [ -f "$src" ] && [ "$(find "$src" -mtime +${RAW_TTL_DAYS} -print)" ]; then
    echo "[$(date -u +%FT%TZ)] dropping $dir"
    rm -rf "$dir"
  fi
done

echo "[$(date -u +%FT%TZ)] cleanup ok"
