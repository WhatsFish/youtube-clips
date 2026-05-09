#!/usr/bin/env python3
"""
Hello-world render: download a YouTube video, cut a 30-second clip,
overlay Chinese TTS narration on top of ducked original audio. No LLM
in the loop — pure mechanical chain test that validates yt-dlp + ffmpeg
+ Azure Speech work and surfaces real per-stage timings on this VM.

Usage:
  .venv/bin/python scripts/hello-render.py <youtube_url_or_id>

Output:
  /video/youtube-clips/outputs/hello-world/<video_id>/output.mp4

Reads from env (~/.config/youtube-clips.env via run-agent.sh, or sourced
manually): AZURE_SPEECH_KEY, AZURE_SPEECH_REGION.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
YT_DLP = str(PROJECT_ROOT / ".venv" / "bin" / "yt-dlp")

# YouTube anti-bot rejects cloud-VM IPs without authenticated cookies.
# User exports cookies.txt from their local browser (Netscape format)
# and lands it here. File is mode 600.
COOKIES_FILE = Path.home() / ".config" / "youtube-clips-cookies.txt"

OUT_BASE = Path("/video/youtube-clips/outputs/hello-world")
RAW_BASE = Path("/video/youtube-clips/raw")
CLIP_DURATION_SEC = 30

# Hardcoded Chinese narration text. Keep length roughly proportional to
# CLIP_DURATION_SEC — 中文 ~3-4 字/秒 自然语速。30s ≈ 90-120 chars.
NARRATION_TEXT = (
    "这是一段中文测试旁白。我们正在验证 youtube-clips 的渲染流水线："
    "从 YouTube 下载视频、用 ffmpeg 切片、调用 Azure 语音合成生成中文配音、"
    "把原片音轨压低后叠加中文解说。如果你听到这段话，整条机械链路就跑通了。"
)

TTS_VOICE = "zh-CN-XiaoxiaoNeural"


def parse_video_id(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", s):
        return s
    sys.exit(f"could not parse video id from: {s!r}")


def stage(name: str):
    print(f"[{name}] starting...", flush=True)
    return name, time.monotonic()


def done(label_t0: tuple[str, float]) -> float:
    name, t0 = label_t0
    elapsed = time.monotonic() - t0
    print(f"[{name}] done in {elapsed:.1f}s", flush=True)
    return elapsed


def download(video_id: str) -> Path:
    label = stage("download")
    raw_dir = RAW_BASE / video_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / "source.mp4"
    if out.exists() and out.stat().st_size > 0:
        print(f"  cached: {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        # 720p mp4 is plenty for a hello-world; cuts download size and
        # keeps the smoke test fast. Real pipeline can pick higher.
        if not COOKIES_FILE.exists():
            sys.exit(
                f"cookies file missing at {COOKIES_FILE}. Export from a "
                f"browser (logged into YouTube) using a cookies.txt extension "
                f"and copy it there with mode 600."
            )
        subprocess.run(
            [
                YT_DLP,
                "--cookies",
                str(COOKIES_FILE),
                # YouTube's stream URLs require client-side JS to "solve"
                # the n-parameter signature challenge. yt-dlp ships a deno
                # runtime hook for this, but the actual solver script lives
                # as a remote component fetched on first use. Without this
                # flag yt-dlp can only fetch metadata + thumbnails.
                "--remote-components",
                "ejs:github",
                "-f",
                "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
                "--merge-output-format",
                "mp4",
                "-o",
                str(out),
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            check=True,
        )
    done(label)
    return out


def cut(source: Path, job_dir: Path) -> Path:
    label = stage("cut")
    out = job_dir / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", "0", "-i", str(source),
            "-t", str(CLIP_DURATION_SEC),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(out),
        ],
        check=True,
    )
    done(label)
    return out


def tts(text: str, job_dir: Path) -> Path:
    label = stage("tts")
    out = job_dir / "narration.mp3"
    region = os.environ["AZURE_SPEECH_REGION"]
    key = os.environ["AZURE_SPEECH_KEY"]
    ssml = (
        f'<speak version="1.0" xml:lang="zh-CN">'
        f'<voice name="{TTS_VOICE}">{text}</voice>'
        f'</speak>'
    )
    r = requests.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-160kbitrate-mono-mp3",
            "User-Agent": "youtube-clips-hello",
        },
        data=ssml.encode("utf-8"),
        timeout=60,
    )
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"  {len(r.content) / 1024:.1f} KB")
    done(label)
    return out


def mix(clip: Path, narration: Path, job_dir: Path) -> Path:
    label = stage("mix")
    out = job_dir / "output.mp4"
    # Duck original audio to ~20% (~−14 dB), keep narration at full vol,
    # mix down to a single stereo track. Video stream is copied verbatim.
    # `duration=longest` keeps the full clip even if narration is shorter.
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(clip),
            "-i", str(narration),
            "-filter_complex",
            "[0:a]volume=0.2[ducked];"
            "[ducked][1:a]amix=inputs=2:duration=longest:dropout_transition=2[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(out),
        ],
        check=True,
    )
    done(label)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="YouTube URL or 11-char video ID")
    args = ap.parse_args()

    if "AZURE_SPEECH_KEY" not in os.environ or "AZURE_SPEECH_REGION" not in os.environ:
        sys.exit(
            "AZURE_SPEECH_KEY / AZURE_SPEECH_REGION must be set. "
            "Try: source ~/.config/youtube-clips.env"
        )

    vid = parse_video_id(args.video)
    job_dir = OUT_BASE / vid
    job_dir.mkdir(parents=True, exist_ok=True)
    print(f"video_id: {vid}")
    print(f"job_dir:  {job_dir}\n")

    overall_t0 = time.monotonic()
    src = download(vid)
    clip = cut(src, job_dir)
    nar = tts(NARRATION_TEXT, job_dir)
    out = mix(clip, nar, job_dir)
    overall = time.monotonic() - overall_t0

    size_mb = out.stat().st_size / 1024 / 1024
    print()
    print("=" * 50)
    print(f"  output: {out}")
    print(f"  size:   {size_mb:.1f} MB")
    print(f"  total:  {overall:.1f}s")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
