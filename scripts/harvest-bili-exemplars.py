#!/usr/bin/env python3
"""Harvest a batch of Bilibili videos for style exemplar packs.

Reads a JSON manifest of BV ids (or full URLs) grouped by genre tag,
fetches each video's metadata + AI-generated transcript via the
Bilibili web API, and writes the result to disk.

The output is intended to be embedded in a Profile's `style_exemplars`
field (or referenced from there) so that the producer / synthesis /
commentary prompts can use the harvested videos as few-shot writing
examples — teaching the agent "what hook + rhythm goes viral on
Bilibili in this genre."

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/harvest-bili-exemplars.py
      [--manifest path/to/manifest.json]
      [--out-dir /video/youtube-clips/exemplars]

Manifest format (JSON):
{
  "<genre_tag>": [
    "BV1xxxxxxxxx" or "https://www.bilibili.com/video/BVxxx...",
    ...
  ],
  ...
}
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.bilibili import BilibiliClient, extract_bvid, format_transcript_lines

DEFAULT_OUT = Path("/video/youtube-clips/exemplars")

# Default manifest: the 8 URLs the operator hand-picked on 2026-05-11
# as stylistic references — 6 social/economic op-ed, 2 tech.
DEFAULT_MANIFEST = {
    "social-editorial": [
        "BV1fzdGBzE8n",
        "BV1kLdsByEhq",
        "BV1Su411a7A3",
        "BV12T4y1F7LT",
        "BV1KkRZBGEwi",
        "BV1fgoVBGE2M",
    ],
    "tech-synthesis": [
        "BV1jEAaz3E6K",
        "BV1QwT9zKE8g",
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--manifest",
        type=Path,
        help="JSON file with {genre: [BV ids or URLs]}. Defaults to operator's hand-picked set.",
    )
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    else:
        manifest = DEFAULT_MANIFEST

    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = BilibiliClient.from_env()

    all_exemplars: dict[str, list[dict]] = {}

    for genre, refs in manifest.items():
        print(f"\n==== {genre} ({len(refs)} videos) ====")
        bucket: list[dict] = []
        for ref in refs:
            bvid = extract_bvid(ref)
            try:
                info = client.video_info(bvid)
                print(f"  {bvid}  view={info.stat.get('view'):,}  {info.title[:50]}")
                lines = client.transcript(info)
                if not lines:
                    print(f"    ⚠ no transcript available")
                # Per-video file: full transcript + metadata. Profile-side
                # we may want to summarize / trim, but keep the full data
                # on disk so a future "style extraction" pass can re-derive.
                per_video = {
                    "bvid": info.bvid,
                    "url": info.url,
                    "title": info.title,
                    "desc": info.desc,
                    "owner": info.owner,
                    "duration_sec": info.duration,
                    "pubdate": info.pubdate,
                    "stat": info.stat,
                    "tname": info.tname,
                    "transcript_lines": [
                        {"start": s.start, "end": s.end, "text": s.text}
                        for s in lines
                    ],
                    "transcript_text": format_transcript_lines(lines),
                    "harvested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
                (args.out_dir / f"{bvid}.json").write_text(
                    json.dumps(per_video, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                bucket.append({
                    "bvid": info.bvid,
                    "title": info.title,
                    "desc": info.desc,
                    "owner": info.owner,
                    "duration_sec": info.duration,
                    "stat": info.stat,
                    "transcript_chars": sum(len(s.text) for s in lines),
                    "transcript_lines_count": len(lines),
                })
                # Be polite to the API — half-second per request is well
                # under any reasonable rate cap.
                time.sleep(0.5)
            except Exception as e:
                print(f"  ERR {bvid}: {e}")
        all_exemplars[genre] = bucket

    # Manifest index file — easy human-readable summary + the grouping
    # of which BV id belongs to which genre.
    index = {
        "harvested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "groups": all_exemplars,
    }
    (args.out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print(f"  harvested:  {sum(len(v) for v in all_exemplars.values())} videos")
    print(f"  per-video:  {args.out_dir}/<bvid>.json")
    print(f"  index:      {args.out_dir}/index.json")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
