#!/usr/bin/env python3
"""
One-shot: scan /video/youtube-clips/outputs/edl-prototype/* and write
DB rows (Topic + Source + Job + Output) for any render that doesn't
already have them.

Run once to migrate the existing filesystem-based renders into the
Postgres-backed flow before flipping the web UI's read path. Idempotent:
safe to re-run; it'll skip jobs that already have an `outputs` row
pointing at the render.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/backfill-db.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import db
from pipeline.profiles import fetch_profile

OUTPUTS_BASE = Path("/video/youtube-clips/outputs/edl-prototype")
RAW_BASE = Path("/video/youtube-clips/raw")


def ffprobe_duration(path: Path) -> float | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            text=True,
        ).strip()
        return float(out)
    except Exception:
        return None


def output_already_indexed(path: Path) -> bool:
    with db.cursor() as cur:
        cur.execute("SELECT 1 FROM outputs WHERE path = %s LIMIT 1", (str(path),))
        return cur.fetchone() is not None


def backfill_one(video_id: str, dir_path: Path) -> bool:
    """Returns True if rows were written, False if skipped."""
    edl_path = dir_path / "edl.json"
    render_path = dir_path / "render.mp4"
    if not edl_path.exists() or not render_path.exists():
        print(f"  skip {video_id}: missing edl.json or render.mp4")
        return False

    if output_already_indexed(render_path):
        print(f"  skip {video_id}: already in outputs table")
        return False

    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    if edl.get("decision") != "make":
        print(f"  skip {video_id}: edl.decision != make")
        return False

    profile_name = edl.get("profile_name", "tech-insights-cn")
    profile = fetch_profile(profile_name)

    # Topic — derive from EDL title.
    topic_title = edl.get("title_zh") or video_id
    topic_id = db.upsert_topic(
        profile_id=profile.id,
        title=topic_title,
        description=edl.get("description_zh"),
        keywords=edl.get("tags_zh"),
        status="approved",
        source="agent",
    )

    # Source — duration from existing source.mp4 if available.
    source_mp4 = RAW_BASE / video_id / "source.mp4"
    src_duration = int(ffprobe_duration(source_mp4) or 0) if source_mp4.exists() else None
    source_id = db.upsert_source(
        profile_id=profile.id,
        source_platform="youtube",
        external_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        duration_sec=src_duration,
        source_language="en",
        download_path=str(source_mp4) if source_mp4.exists() else None,
        downloaded=source_mp4.exists(),
    )

    # Stamp the ids before insert_job so jobs.edl_jsonb gets them too.
    edl["topic_id"] = topic_id
    edl["source_id"] = source_id

    # Job — full EDL stored.
    job_id = db.insert_job(
        topic_id=topic_id,
        profile_id=profile.id,
        edl_jsonb=edl,
        status="completed",
    )
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET edl_jsonb = edl_jsonb || jsonb_build_object('job_id', %s::bigint) WHERE id = %s",
            (job_id, job_id),
        )

    # Output — render metadata.
    out_dur = ffprobe_duration(render_path)
    out_size = render_path.stat().st_size
    platform = (profile.get("output", "platforms") or ["bilibili_long"])[0]
    output_id = db.insert_output(
        job_id=job_id,
        platform=platform,
        aspect_ratio="16:9",
        language="zh",
        path=str(render_path),
        duration_sec=out_dur,
        file_size_bytes=out_size,
        title=edl.get("title_zh"),
        description=edl.get("description_zh"),
        tags=edl.get("tags_zh"),
        status="ready",
    )

    # Stamp ids back into edl.json so future runs and the web UI can
    # join via these without filename guessing.
    edl["topic_id"] = topic_id
    edl["source_id"] = source_id
    edl["job_id"] = job_id
    edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"  {video_id}: profile={profile_name} topic={topic_id} "
        f"source={source_id} job={job_id} output={output_id}"
    )
    return True


def main() -> int:
    written = 0
    skipped = 0
    if not OUTPUTS_BASE.exists():
        sys.exit(f"no outputs directory: {OUTPUTS_BASE}")
    for d in sorted(OUTPUTS_BASE.iterdir()):
        if not d.is_dir():
            continue
        ok = backfill_one(d.name, d)
        if ok:
            written += 1
        else:
            skipped += 1
    print(f"\nbackfill: {written} written, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
