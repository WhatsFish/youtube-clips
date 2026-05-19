#!/usr/bin/env python3
"""Smoke test localize_in_video.

Exercises:
  (a) Caption-path hit: "Jensen advice to graduates" against Caltech
      commencement (has dense English captions).
  (b) Vision-path hit: "Jensen holding up Blackwell" against GTC 2024
      keynote (visual moment, captions don't describe action). Cached
      source + frames from Exp 3 so it shouldn't re-download.
  (c) Vision negative: "Jensen at podcast desk" should return [] on a
      keynote source (sanity check that we don't hallucinate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.archival import localize_in_video


def show(label: str, result: dict):
    print(f"\n=== {label} ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    # (a) Caption tier — GTC 2024 NVIDIA keynote, looking for a caption-rich moment
    print("\n>>> caption tier (concept) — GTC 2024 keynote, 'Blackwell two GPUs in one' <<<")
    r = localize_in_video(
        video_id="Y2F8yisiS6E",
        source="youtube",
        target_desc="Jensen says Blackwell is really two GPUs in one",
        target_dur_sec=6,
    )
    show("caption tier", r)

    # (b) Vision tier — same source, visual moment captions can't describe
    print("\n>>> vision tier (visual) — GTC 2024 keynote, 'holding up Blackwell motherboard' <<<")
    r = localize_in_video(
        video_id="Y2F8yisiS6E",
        source="youtube",
        target_desc=(
            "Jensen Huang on stage holding up / showing the Blackwell GPU "
            "(a physical chip / motherboard / silicon wafer) to the audience"
        ),
        target_dur_sec=7,
    )
    show("vision tier", r)


if __name__ == "__main__":
    main()
