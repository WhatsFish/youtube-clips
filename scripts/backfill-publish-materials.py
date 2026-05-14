#!/usr/bin/env python3
"""Backfill publish materials for already-rendered jobs.

Re-runs _generate_publish_materials() for the given job_id(s) without
re-rendering. Useful when:
  - We add a new publish channel to a Profile and want to backfill old jobs
  - A produce-time publish stage failed (non-fatal) and we want to retry
  - The publish prompt is iterated and we want fresh materials

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/backfill-publish-materials.py 34 33   # job_ids
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.profiles import fetch_profile
from pipeline import db

# Re-import _generate_publish_materials from produce-original via importlib
# since it's not a normal package module.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "produce_original",
    Path(__file__).resolve().parent / "produce-original.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
_generate_publish_materials = mod._generate_publish_materials


OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")


def backfill(job_id: int) -> None:
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT j.edl_jsonb, p.name AS profile_name, j.id
              FROM jobs j JOIN profiles p ON p.id = j.profile_id
              WHERE j.id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if not row:
        print(f"  job {job_id}: not found")
        return
    edl = row["edl_jsonb"]
    profile = fetch_profile(row["profile_name"])
    slug = edl.get("url_slug") or edl.get("source_id") or f"job-{job_id}"
    job_dir = OUT_BASE / slug
    if not job_dir.exists():
        print(f"  job {job_id} ({slug}): job_dir missing, skipping")
        return
    print(f"\n==== backfilling job_id={job_id} profile={row['profile_name']} ====")
    _generate_publish_materials(
        profile=profile, edl=edl, job_id=job_id, job_dir=job_dir, run_id=None,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_ids", nargs="+", type=int)
    args = ap.parse_args()
    for jid in args.job_ids:
        try:
            backfill(jid)
        except Exception as e:
            print(f"  job {jid}: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
