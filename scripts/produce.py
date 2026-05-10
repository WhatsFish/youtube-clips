#!/usr/bin/env python3
"""
End-to-end producer: discover → download → EDL → render in one command.

Two ways to invoke:

  # Full chain from a topic
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/produce.py \\
      --topic "Federal Reserve rate decision" \\
      [--profile finance-insights-cn]

  # Skip discovery — pipe an already-known video into the chain
  .venv/bin/python scripts/produce.py \\
      --video-id YZ15suxtiaM \\
      [--title "..."] [--channel "..."] [--profile X]

Each step writes its own artifacts to disk (discovery JSON / source.mp4 +
VTT / edl.json / render.mp4 / per-shot intermediates). If cookies expire
mid-chain, fix them and re-run — completed steps either skip cleanly
(yt-dlp sees source.mp4) or harmlessly overwrite (EDL + render). The
chain is idempotent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.prompts import load_prompt
from pipeline.profiles import fetch_profile, Profile
from pipeline.claude_io import call_claude, extract_json
from pipeline.transcript import parse_vtt, format_transcript
from pipeline.downloader import download, BotWallError, CookiesMissingError, COOKIES_FILE
from pipeline.youtube_search import enrich

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DISCOVER_BASE = Path("/video/youtube-clips/outputs/discovered")


def _fmt_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def cookie_age_preflight() -> None:
    """Print how stale ~/.config/youtube-clips-cookies.txt is. The
    Azure-VM-vs-YouTube anti-bot dance means cookies usually only buy
    you minutes-to-hours of valid downloads, not weeks. Surfacing the
    age makes it obvious whether to refresh before kicking off the
    chain (especially if you've burned a few downloads already today).
    """
    if not COOKIES_FILE.exists():
        print("[cookies]  MISSING — yt-dlp will fail. Re-export from a logged-in browser.")
        return
    age_sec = time.time() - COOKIES_FILE.stat().st_mtime
    label = _fmt_age(age_sec)
    if age_sec > 3600:
        print(f"[cookies]  last refresh: {label} ago — likely stale on this VM, refresh recommended")
    else:
        print(f"[cookies]  last refresh: {label} ago")


def _slugify(s: str) -> str:
    s = re.sub(r"[^\w一-鿿\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:60] or "topic"


def _stage_header(label: str) -> None:
    print(f"\n{'─' * 4} {label} {'─' * (54 - len(label))}", flush=True)


def discover(topic: str, profile_name: str) -> tuple[dict, Path]:
    """Run the discover-source script and return (pick_json, json_path)."""
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "python"),
        str(PROJECT_ROOT / "scripts" / "discover-source.py"),
        "--topic", topic,
        "--profile", profile_name,
    ]
    subprocess.run(cmd, check=True)
    out_file = DISCOVER_BASE / profile_name / f"{_slugify(topic)}.json"
    if not out_file.exists():
        sys.exit(f"discover output not found: {out_file}")
    return json.loads(out_file.read_text(encoding="utf-8")), out_file


def fetch_video_metadata(video_id: str) -> tuple[str, str]:
    """Use videos.list (1 quota unit) to grab title + channel for a known id."""
    cands = enrich([video_id])
    if not cands:
        return ("(unknown)", "(unknown)")
    c = cands[0]
    return (c.title, c.channel)


def run_edl_from_discovery(
    discovery_json: Path,
    *,
    profile_name: str,
    prompt_version: str,
    primary_video_id: str,
) -> Path:
    """Multi-source EDL: edl-prototype reads sources directly from discovery JSON."""
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "python"),
        str(PROJECT_ROOT / "scripts" / "edl-prototype.py"),
        "--from-discovery", str(discovery_json),
        "--profile", profile_name,
        "--prompt-version", prompt_version,
    ]
    subprocess.run(cmd, check=True)
    return Path("/video/youtube-clips/outputs/edl-prototype") / primary_video_id / "edl.json"


def run_edl_single(
    video_id: str,
    *,
    title: str,
    channel: str,
    profile_name: str,
    prompt_version: str,
) -> Path:
    """Single-source EDL (legacy --video-id path)."""
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "python"),
        str(PROJECT_ROOT / "scripts" / "edl-prototype.py"),
        "--title", title,
        "--channel", channel,
        "--profile", profile_name,
        "--prompt-version", prompt_version,
        "--", video_id,
    ]
    subprocess.run(cmd, check=True)
    return Path("/video/youtube-clips/outputs/edl-prototype") / video_id / "edl.json"


def run_render(video_id: str) -> Path:
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "python"),
        str(PROJECT_ROOT / "scripts" / "edl-render.py"),
        "--", video_id,
    ]
    subprocess.run(cmd, check=True)
    return Path("/video/youtube-clips/outputs/edl-prototype") / video_id / "render.mp4"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic", help="Run full chain starting from discovery")
    g.add_argument("--video-id", help="Skip discovery; download + EDL + render this id")
    ap.add_argument("--profile", default="tech-insights-cn")
    ap.add_argument("--prompt-version", default="latest")
    ap.add_argument("--title", help="Source title (used when --video-id is given)")
    ap.add_argument("--channel", help="Source channel (used when --video-id is given)")
    ap.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download even if source.mp4 already exists",
    )
    args = ap.parse_args()

    overall_t0 = time.monotonic()

    # 1. Resolve sources to use. --topic runs multi-source discovery
    # (1-3 picks); --video-id is the legacy single-source path.
    discovery_json: Path | None = None
    if args.topic:
        _stage_header("discover")
        pick, discovery_json = discover(args.topic, args.profile)
        picked_sources = pick.get("picked_sources") or []
        if not picked_sources:
            sys.exit(f"discovery returned skip: {pick.get('skip_reason')}")
        sources_to_dl = [
            (p["id"], p.get("title") or "(unknown)", p.get("channel") or "(unknown)")
            for p in picked_sources
        ]
        primary_video_id = sources_to_dl[0][0]
    else:
        primary_video_id = args.video_id
        if args.title and args.channel:
            title, channel = args.title, args.channel
        else:
            print("[meta] fetching title/channel via videos.list...", flush=True)
            title, channel = fetch_video_metadata(primary_video_id)
        sources_to_dl = [(primary_video_id, title, channel)]
        print(f"video_id: {primary_video_id}")
        print(f"title:    {title}")
        print(f"channel:  {channel}")

    # 2. Download — every picked source. The agent is conservative about
    # picking 2 or 3, so this loops 1-3 times typically. Each download
    # runs through the same yt-dlp + cookies + PO-token path.
    _stage_header("download")
    cookie_age_preflight()
    print(f"sources to download: {len(sources_to_dl)}")
    for vid, title, channel in sources_to_dl:
        print(f"  → {vid}  {title[:55]}")
        try:
            result = download(vid, force=args.force_download)
        except CookiesMissingError as e:
            sys.exit(f"\nERROR: {e}")
        except BotWallError as e:
            sys.exit(
                f"\nERROR ({vid}): {e}\n"
                f"Refresh ~/.config/youtube-clips-cookies.txt from a logged-in "
                f"browser, then re-run this same command."
            )
        if not result.vtt_path:
            sys.exit(f"ERROR ({vid}): no English captions found; cannot run the EDL agent")

    # 3. EDL. Multi-source path reads the discovery JSON directly so
    # edl-prototype sees titles/channels/roles without re-deriving them.
    _stage_header("edl")
    if discovery_json is not None:
        edl_path = run_edl_from_discovery(
            discovery_json,
            profile_name=args.profile,
            prompt_version=args.prompt_version,
            primary_video_id=primary_video_id,
        )
    else:
        # --video-id legacy path: single source
        vid, title, channel = sources_to_dl[0]
        edl_path = run_edl_single(
            vid,
            title=title,
            channel=channel,
            profile_name=args.profile,
            prompt_version=args.prompt_version,
        )

    # 4. Render — keyed off the primary video_id (which is the EDL output dir).
    _stage_header("render")
    render_path = run_render(primary_video_id)

    elapsed = time.monotonic() - overall_t0
    print()
    print("=" * 60)
    print(f"  produce complete: {primary_video_id}  (sources: {len(sources_to_dl)})")
    print(f"  edl:    {edl_path}")
    print(f"  render: {render_path}")
    print(f"  total:  {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(
        f"  view:   https://ai-native.japaneast.cloudapp.azure.com/youtube-clips/"
        f"jobs/{primary_video_id}"
    )
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
