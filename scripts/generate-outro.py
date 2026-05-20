#!/usr/bin/env python3
"""Generate a channel-specific outro video (5s, no TTS).

Pipeline:
  1. CogView produces an abstract gradient background (1920x1080).
  2. ffmpeg runs zoompan (slow 1.0 → 1.08 zoom over 5s) + drawtext for the
     2-line CTA + 0.5s fade in/out.

Output is cached at /video/youtube-clips/outros/<channel>.mp4. To
regenerate, delete the file and re-run, or pass --force.

The outro is concept-cheap (abstract gradient + text) so it should look
clean even with no TTS — keep it short, let the visual rest.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/generate-outro.py --profile ai-deep-cn
  .venv/bin/python scripts/generate-outro.py --profile ai-deep-cn --force
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.cogview import CogViewClient
from pipeline.profiles import fetch_profile


OUTROS_DIR = Path("/video/youtube-clips/outros")
OUTROS_DIR.mkdir(parents=True, exist_ok=True)
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
DURATION_SEC = 3.0

# Per-aspect render shapes — match edl-render.py PLATFORM_SPEC exactly so
# concat demuxer (copy mode) joins outros to renders without re-encoding
# the whole video. 1280x720 for bilibili_long, 720x1280 for douyin.
ASPECT_SPECS = {
    "16:9": {
        "w": 1280, "h": 720,
        "font1": 56, "font2": 44,
        "suffix": "",   # ai-deep-cn.mp4 (default)
    },
    "9:16": {
        "w": 720, "h": 1280,
        "font1": 64, "font2": 50,
        "suffix": "-douyin",  # ai-deep-cn-douyin.mp4
    },
}


def _drawtext_escape(s: str) -> str:
    """ffmpeg drawtext: escape special chars for the `text=` argument."""
    return (
        s.replace("\\", r"\\")
         .replace(":", r"\:")
         .replace("'", r"\'")
         .replace("%", r"\%")
    )


def generate_bg(prompt_en: str, out_path: Path) -> Path:
    """CogView 1280x720 gradient. We use the standard supported size
    (CogView-3-Flash 400's on 1920x1080 — the documented ≤ 2^21 pixel
    budget seems aspirational) and rely on ffmpeg's zoompan to upscale
    to 1920x1080 with the slow zoom motion."""
    print(f"  generating bg via CogView (prompt: {prompt_en[:60]!r})...")
    client = CogViewClient()
    t0 = time.monotonic()
    res = client.generate(prompt_en, size="1280x720")
    client.download(res, out_path)
    print(f"  ✓ bg saved in {time.monotonic() - t0:.0f}s: {out_path}")
    return out_path


def compose_outro(
    bg_path: Path,
    line1_zh: str,
    line2_zh: str,
    out_path: Path,
    duration_sec: float = DURATION_SEC,
    aspect: str = "16:9",
) -> Path:
    """ffmpeg: ken-burns slow zoom + 2-line drawtext center + 0.5s fade
    in/out. No audio track — outro audio is silent.

    aspect: "16:9" → 1920x1080 (bilibili), "9:16" → 1080x1920 (douyin).
    """
    spec = ASPECT_SPECS[aspect]
    w, h, f1, f2 = spec["w"], spec["h"], spec["font1"], spec["font2"]
    fps = 30
    frames = int(duration_sec * fps)
    zoom_step = 0.06 / frames
    line1_esc = _drawtext_escape(line1_zh)
    line2_esc = _drawtext_escape(line2_zh)
    # Pre-scale source to 1.25× final dims so zoompan has headroom to zoom in.
    pre_w, pre_h = int(w * 1.25), int(h * 1.25)
    vf = (
        f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=increase,"
        f"crop={pre_w}:{pre_h},"
        f"zoompan=z='min(1+{zoom_step}*on,1.06)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},"
        f"drawtext=fontfile={FONT_PATH}:text='{line1_esc}':fontcolor=white:"
        f"fontsize={f1}:bordercolor=black@0.8:borderw=4:"
        f"x=(w-text_w)/2:y=(h/2)-text_h-20,"
        f"drawtext=fontfile={FONT_PATH}:text='{line2_esc}':fontcolor=white:"
        f"fontsize={f2}:bordercolor=black@0.8:borderw=4:"
        f"x=(w-text_w)/2:y=(h/2)+30,"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration_sec - 0.5}:d=0.5"
    )
    print(f"  compositing {aspect} outro ({w}x{h})...")
    t0 = time.monotonic()
    # Encode params (codec / pix_fmt / fps / dimensions / audio config) MUST
    # match edl-render output exactly so concat demuxer + -c copy can stitch
    # outro to the main render without re-encoding the whole video.
    # Silent stereo aac satisfies the stream-count parity.
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(bg_path),
            "-f", "lavfi", "-t", f"{duration_sec:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", vf,
            "-t", f"{duration_sec:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-ar", "48000", "-ac", "2",
            "-shortest",
            str(out_path),
        ],
        check=True,
    )
    print(f"  ✓ outro composited in {time.monotonic() - t0:.0f}s: {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--force", action="store_true", help="regenerate even if outro exists")
    ap.add_argument(
        "--aspects", default="",
        help="comma-separated subset of 16:9,9:16 (default: both)",
    )
    args = ap.parse_args()

    profile = fetch_profile(args.profile)
    ch = (profile.config or {}).get("channel") or {}
    outro_cfg = ch.get("outro") or {}
    if not outro_cfg:
        sys.exit(
            f"profile {args.profile!r} has no channel.outro config. "
            "Add it to the seed JSON: outro: {text_line1_zh, text_line2_zh, background_prompt_en}"
        )
    line1 = (outro_cfg.get("text_line1_zh") or "").strip()
    line2 = (outro_cfg.get("text_line2_zh") or "").strip()
    bg_prompt = (outro_cfg.get("background_prompt_en") or "").strip()
    if not (line1 and bg_prompt):
        sys.exit(
            "outro.text_line1_zh and outro.background_prompt_en are required"
        )

    # CogView bg is aspect-agnostic (abstract gradient looks fine cropped
    # either way); generate it once and reuse for both 16:9 and 9:16 renders.
    bg_path = OUTROS_DIR / f"{profile.name}.bg.png"
    if not bg_path.exists() or args.force:
        generate_bg(bg_prompt, bg_path)
    else:
        print(f"  using cached bg: {bg_path}")

    # Generate both aspects unless explicitly limited
    aspects = args.aspects.split(",") if args.aspects else list(ASPECT_SPECS.keys())
    outputs: list[Path] = []
    for aspect in aspects:
        if aspect not in ASPECT_SPECS:
            print(f"  [warn] unknown aspect {aspect!r}; skipping")
            continue
        spec = ASPECT_SPECS[aspect]
        out_path = OUTROS_DIR / f"{profile.name}{spec['suffix']}.mp4"
        if out_path.exists() and not args.force:
            print(f"  outro exists ({aspect}): {out_path} — skip (--force to regen)")
            outputs.append(out_path)
            continue
        compose_outro(bg_path, line1, line2, out_path, aspect=aspect)
        outputs.append(out_path)

    print()
    print("=" * 60)
    for p in outputs:
        actual_dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            text=True,
        ).strip())
        print(f"  {p.name}  {actual_dur:.2f}s  {p.stat().st_size / 1024:.0f} KB")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
