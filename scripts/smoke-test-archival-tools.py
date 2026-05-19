#!/usr/bin/env python3
"""Smoke test the archival_tools functions directly (without going
through MCP). Verifies search returns sensible candidates and transcript
fetches work for both sources."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.tools.archival_tools import (
    search_youtube_archival,
    search_bilibili_archival,
    read_youtube_transcript,
    read_bilibili_transcript,
)


def show(label: str, obj):
    print(f"\n--- {label} ---")
    if isinstance(obj, dict):
        # Trim long fields for readability
        if "results" in obj:
            print(f"query: {obj.get('query')}  ·  {len(obj['results'])} results")
            for i, r in enumerate(obj["results"][:5]):
                official = "★" if r.get("is_official") else " "
                print(f"  [{i}] {official} {r.get('title', '')[:60]!r}")
                print(f"        channel: {r.get('channel') or r.get('owner')}")
                print(f"        dur: {r.get('duration_sec')}s  views: {r.get('view_count'):,}  "
                      f"url: {r.get('url')}")
        elif "transcript_lines" in obj:
            n = len(obj.get("transcript_lines", []))
            print(f"video: {obj.get('title') or obj.get('video_id')}")
            print(f"transcript: {n} lines")
            if obj.get("error"):
                print(f"error: {obj['error']}")
            for line in obj.get("transcript_lines", [])[:5]:
                print(f"  {line['start']:.1f}s  {line['text'][:80]}")
        else:
            print(json.dumps(obj, ensure_ascii=False, indent=2)[:800])


def main():
    print("=" * 60)
    print("YouTube archival search")
    print("=" * 60)
    yt = search_youtube_archival(
        "Jensen Huang GTC 2024 Blackwell keynote", max_results=10,
    )
    show("YouTube · Jensen GTC 2024", yt)

    print("=" * 60)
    print("Bilibili archival search")
    print("=" * 60)
    bili = search_bilibili_archival("黄仁勋 GTC 主题演讲", max_results=10)
    show("Bilibili · 黄仁勋 GTC", bili)

    # Transcript on first official (or just first) result from each
    yt_results = yt.get("results", [])
    if yt_results:
        first_official = next(
            (r for r in yt_results if r.get("is_official")),
            yt_results[0],
        )
        print(f"\n→ pulling YouTube transcript for: {first_official['video_id']}")
        t = read_youtube_transcript(first_official["video_id"], language="en")
        show("YouTube transcript", t)

    bili_results = bili.get("results", [])
    if bili_results:
        first_official = next(
            (r for r in bili_results if r.get("is_official")),
            bili_results[0],
        )
        print(f"\n→ pulling Bilibili transcript for: {first_official['bvid']}")
        t = read_bilibili_transcript(first_official["bvid"])
        show("Bilibili transcript", t)


if __name__ == "__main__":
    main()
