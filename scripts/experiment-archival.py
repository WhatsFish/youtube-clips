#!/usr/bin/env python3
"""One-off feasibility experiment for asset_strategy="archival".

Given a target description ("Jensen Huang shaking hands with student at CMU
commencement"), search YouTube, filter to viable archival candidates, fetch
captions, fuzzy-match the target_desc to find the right timestamp range.

This is NOT production code — it's prototype. Run by hand, observe what
works, decide whether to build the real MCP tool.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/experiment-archival.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import youtube_search
from pipeline.transcript import parse_vtt


CHANNEL_BLACKLIST_HINTS = [
    "reaction", "react", "compilation", "best of", "top 10",
    "你绝对", "震惊", "细思极恐",
]


@dataclass
class ArchivalMatch:
    video_id: str
    url: str
    title: str
    channel: str
    start_sec: float
    end_sec: float
    matched_text: str
    confidence: float


def filter_candidates(cs: list, *, min_views: int = 5000, min_dur_sec: int = 60):
    """Apply hard filters before spending caption-fetch quota."""
    out = []
    for c in cs:
        if c.view_count < min_views:
            continue
        if c.duration_sec < min_dur_sec:
            continue
        if not c.has_captions:
            continue
        title_lower = c.title.lower()
        chan_lower = c.channel.lower()
        if any(b in title_lower or b in chan_lower for b in CHANNEL_BLACKLIST_HINTS):
            continue
        out.append(c)
    return out


def fetch_captions(video_id: str) -> list[dict] | None:
    """Use yt-dlp to grab English auto-captions; return parsed vtt entries."""
    YTDLP = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "yt-dlp")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        cmd = [
            YTDLP,
            "--skip-download",
            "--write-auto-subs",
            "--sub-lang", "en",
            "--sub-format", "vtt",
            "-o", str(td_path / "%(id)s.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        # Try with cookies if available (improves auth-walled fetches)
        cookies = Path.home() / ".config" / "youtube-clips-cookies.txt"
        if cookies.exists():
            cmd.extend(["--cookies", str(cookies)])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return None
        vtts = list(td_path.glob("*.vtt"))
        if not vtts:
            return None
        entries = parse_vtt(vtts[0])
        return entries


def find_match_in_captions(
    captions: list[tuple[float, str]],
    target_desc: str,
    *,
    target_dur_sec: float = 7.0,
) -> tuple[float, float, str, float] | None:
    """Slide a target_dur window over the caption track and pick the
    highest fuzzy-match-score window.

    Returns (start_sec, end_sec, matched_text, confidence) or None.
    confidence in [0, 1].
    """
    if not captions:
        return None
    target_norm = re.sub(r"\s+", " ", target_desc.lower()).strip()

    # captions is list[(start_sec, text)] from parse_vtt
    items = [(float(s), str(t).lower()) for s, t in captions]
    if not items:
        return None

    best = None  # (score, start, end, text)
    for i, (start, _) in enumerate(items):
        # Collect text spanning approximately target_dur_sec after this point
        window_text_parts = []
        j = i
        while j < len(items) and items[j][0] < start + target_dur_sec:
            window_text_parts.append(items[j][1])
            j += 1
        if not window_text_parts:
            continue
        window_text = " ".join(window_text_parts).strip()
        if not window_text:
            continue
        score = SequenceMatcher(None, target_norm, window_text).ratio()
        # Also boost score if any target keyword appears verbatim
        keywords = [t for t in re.findall(r"\w{4,}", target_norm) if t]
        kw_hits = sum(1 for k in keywords if k in window_text)
        score += 0.08 * kw_hits
        end = items[j - 1][0] if j > i else start + target_dur_sec
        if best is None or score > best[0]:
            best = (score, start, end, window_text)

    if best is None:
        return None
    score, start, end, text = best
    # Confidence: cap at 1.0; min useful threshold ~0.20 (very loose match).
    confidence = min(1.0, score)
    return (start, min(end, start + target_dur_sec), text, confidence)


def find_archival_clip(
    query: str,
    target_desc: str,
    *,
    target_dur_sec: float = 7.0,
    n_candidates: int = 5,
) -> ArchivalMatch | None:
    print(f"\n[scenario] query={query!r}")
    print(f"           target_desc={target_desc!r}, target_dur={target_dur_sec}s")
    raw = youtube_search.search(
        query, max_results=15, video_duration="any", relevance_language="en",
    )
    print(f"  yt search: {len(raw)} raw hits")
    candidates = filter_candidates(raw)
    print(f"  after filter (views≥5k, dur≥60s, has_captions, no_react): {len(candidates)}")
    candidates = candidates[:n_candidates]

    best_global = None  # (confidence, candidate, range)
    for i, c in enumerate(candidates):
        print(f"  [{i}] {c.title[:70]!r} · {c.channel} · {c.duration_sec}s · {c.view_count:,} views")
        captions = fetch_captions(c.id)
        if not captions:
            print(f"      no captions fetched (yt-dlp failed or empty)")
            continue
        print(f"      {len(captions)} caption entries")
        m = find_match_in_captions(captions, target_desc, target_dur_sec=target_dur_sec)
        if not m:
            print(f"      no match window found")
            continue
        start, end, text, conf = m
        print(f"      best match: {start:.1f}s-{end:.1f}s  conf={conf:.2f}  text={text[:80]!r}")
        if best_global is None or conf > best_global[0]:
            best_global = (conf, c, start, end, text)

    if best_global is None:
        print("  ✗ no usable archival match found")
        return None

    conf, c, start, end, text = best_global
    print(f"  ✓ PICK: {c.url} @ {start:.1f}-{end:.1f}s  conf={conf:.2f}")
    return ArchivalMatch(
        video_id=c.id, url=c.url, title=c.title, channel=c.channel,
        start_sec=start, end_sec=end, matched_text=text, confidence=conf,
    )


def main():
    scenarios = [
        # (query, target_desc, target_dur)
        (
            "Jensen Huang CMU commencement speech 2024",
            "Jensen Huang giving advice to graduates about luck and hardship",
            8.0,
        ),
        (
            "Jensen Huang GTC keynote 2024 AI",
            "Jensen Huang holding up a Blackwell GPU on stage",
            6.0,
        ),
        (
            "Jensen Huang China visit Beijing",
            "Jensen Huang in Beijing speaking with reporters about China",
            7.0,
        ),
        (
            "Jensen Huang interview leather jacket",
            "Jensen Huang explaining why he wears the same leather jacket",
            6.0,
        ),
    ]
    results: list[ArchivalMatch | None] = []
    for query, desc, dur in scenarios:
        m = find_archival_clip(query, desc, target_dur_sec=dur)
        results.append(m)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for (q, _, _), m in zip(scenarios, results):
        if m:
            print(f"  ✓  {q[:50]:<50}  conf={m.confidence:.2f}  → {m.video_id} @ {m.start_sec:.0f}s")
        else:
            print(f"  ✗  {q[:50]:<50}  no match")


if __name__ == "__main__":
    main()
