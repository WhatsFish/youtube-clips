#!/usr/bin/env python3
"""
EDL renderer (prototype): consume an EDL JSON produced by edl-prototype.py
and render a single 16:9 mp4. No DB, no profile lookup, single source.

Visual strategy v0:
  intro narration   →  black 1280x720 with TTS audio
  each segment      →  cut clip (audio ducked) + freeze-last-frame held
                       for the narration duration with TTS audio
  outro narration   →  black with TTS audio

Audio: original cut audio at 0.2 volume during clips, narration TTS at
full volume during fillers (and intro/outro). No mixing — the narration
plays in dedicated filler segments, not over the clips themselves, so
viewers can still hear the original speaker (quietly) during the clip.

Usage:
  .venv/bin/python scripts/edl-render.py <video_id>

Inputs:
  /video/youtube-clips/raw/<video_id>/source.mp4
  /video/youtube-clips/outputs/edl-prototype/<video_id>/edl.json

Output:
  /video/youtube-clips/outputs/edl-prototype/<video_id>/render.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

RAW_BASE = Path("/video/youtube-clips/raw")
OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")

# 16:9 standard for Bilibili long videos. Phase 3 will branch to 9:16
# variants for Shorts/Douyin.
W, H = 1280, 720
FPS = 30
VIDEO_ARGS = [
    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    "-pix_fmt", "yuv420p",
    "-r", str(FPS),
]
AUDIO_ARGS = [
    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
]
# Original audio level under narration / during clips when narration could
# overlap. 0.2 ≈ −14 dB. Subjectively "audible but background".
DUCKED_VOL = 0.2


def stage(name: str):
    print(f"[{name}] starting...", flush=True)
    return name, time.monotonic()


def done(label_t0):
    name, t0 = label_t0
    elapsed = time.monotonic() - t0
    print(f"[{name}] done in {elapsed:.1f}s", flush=True)
    return elapsed


def ffprobe_duration(path: Path) -> float:
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


def tts(text: str, out_path: Path, voice: str) -> Path:
    region = os.environ["AZURE_SPEECH_REGION"]
    key = os.environ["AZURE_SPEECH_KEY"]
    ssml = (
        f'<speak version="1.0" xml:lang="zh-CN">'
        f'<voice name="{voice}">{text}</voice>'
        f'</speak>'
    )
    r = requests.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-160kbitrate-mono-mp3",
            "User-Agent": "youtube-clips-render",
        },
        data=ssml.encode("utf-8"),
        timeout=60,
    )
    r.raise_for_status()
    out_path.write_bytes(r.content)
    return out_path


def cut_clip(source: Path, out: Path, start: float, end: float) -> None:
    """Cut [start, end] from source, ducked audio, normalized to W×H@FPS."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start}", "-to", f"{end}",
            "-i", str(source),
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
            "-af", f"volume={DUCKED_VOL}",
            *VIDEO_ARGS, *AUDIO_ARGS,
            str(out),
        ],
        check=True,
    )


def grab_last_frame(clip: Path, out: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-sseof", "-0.5", "-i", str(clip),
            "-frames:v", "1",
            "-q:v", "2",
            str(out),
        ],
        check=True,
    )


def freeze_with_audio(image: Path, audio: Path, duration: float, out: Path) -> None:
    """Render a still image as video for `duration` seconds with the given audio."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(image),
            "-i", str(audio),
            "-t", f"{duration}",
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
            *VIDEO_ARGS, *AUDIO_ARGS,
            "-shortest",
            str(out),
        ],
        check=True,
    )


def black_with_audio(audio: Path, duration: float, out: Path) -> None:
    """Render `duration` of black video with the given audio underneath."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={duration}",
            "-i", str(audio),
            *VIDEO_ARGS, *AUDIO_ARGS,
            "-shortest",
            str(out),
        ],
        check=True,
    )


def concat(parts: list[Path], out: Path, work_dir: Path) -> None:
    """Concat-demuxer concat. All parts must share encoding params."""
    list_file = work_dir / "concat-list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in parts), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out),
        ],
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument(
        "--voice",
        default="zh-CN-XiaoxiaoNeural",
        help="Azure Speech voice name (defaults to Profile's tts_voice)",
    )
    args = ap.parse_args()

    if "AZURE_SPEECH_KEY" not in os.environ:
        sys.exit("source ~/.config/youtube-clips.env first")

    raw_dir = RAW_BASE / args.video_id
    job_dir = OUT_BASE / args.video_id
    source = raw_dir / "source.mp4"
    edl_path = job_dir / "edl.json"

    if not source.exists():
        sys.exit(f"missing source: {source}")
    if not edl_path.exists():
        sys.exit(f"missing edl: {edl_path}")

    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    if edl.get("decision") != "make":
        sys.exit(f"EDL decision is {edl.get('decision')!r}; nothing to render")

    work_dir = job_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    parts: list[Path] = []
    overall_t0 = time.monotonic()

    # ---- intro ----
    intro = edl["narration_intro"]
    label = stage("intro tts")
    intro_audio = work_dir / "intro_narr.mp3"
    tts(intro["text"], intro_audio, args.voice)
    intro_dur = ffprobe_duration(intro_audio)
    done(label)
    label = stage("intro video")
    intro_video = work_dir / "intro.mp4"
    black_with_audio(intro_audio, intro_dur, intro_video)
    parts.append(intro_video)
    done(label)

    # ---- segments ----
    for i, seg in enumerate(edl["segments"]):
        label = stage(f"seg{i} tts")
        narr_audio = work_dir / f"seg{i}_narr.mp3"
        tts(seg["narration_after"]["text"], narr_audio, args.voice)
        narr_dur = ffprobe_duration(narr_audio)
        done(label)

        label = stage(f"seg{i} clip")
        clip = work_dir / f"seg{i}_clip.mp4"
        cut_clip(source, clip, seg["clip"]["start_sec"], seg["clip"]["end_sec"])
        done(label)

        label = stage(f"seg{i} freeze")
        last_frame = work_dir / f"seg{i}_last.png"
        grab_last_frame(clip, last_frame)
        filler = work_dir / f"seg{i}_filler.mp4"
        freeze_with_audio(last_frame, narr_audio, narr_dur, filler)
        done(label)

        parts.append(clip)
        parts.append(filler)

    # ---- outro ----
    outro = edl["narration_outro"]
    label = stage("outro tts")
    outro_audio = work_dir / "outro_narr.mp3"
    tts(outro["text"], outro_audio, args.voice)
    outro_dur = ffprobe_duration(outro_audio)
    done(label)
    label = stage("outro video")
    outro_video = work_dir / "outro.mp4"
    black_with_audio(outro_audio, outro_dur, outro_video)
    parts.append(outro_video)
    done(label)

    # ---- concat ----
    label = stage("concat")
    out = job_dir / "render.mp4"
    concat(parts, out, work_dir)
    done(label)

    overall = time.monotonic() - overall_t0
    final_dur = ffprobe_duration(out)
    size_mb = out.stat().st_size / 1024 / 1024

    print()
    print("=" * 60)
    print(f"  output:    {out}")
    print(f"  duration:  {final_dur:.1f}s ({final_dur/60:.1f} min)")
    print(f"  size:      {size_mb:.1f} MB")
    print(f"  segments:  {len(edl['segments'])}")
    print(f"  total:     {overall:.1f}s")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
