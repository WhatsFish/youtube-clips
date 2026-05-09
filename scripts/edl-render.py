#!/usr/bin/env python3
"""
EDL renderer (v2): consume an EDL JSON in the new "shots" schema and
render a single 16:9 mp4 with continuous Chinese narration over source
video as B-roll.

Each shot:
  visual = source video [source_start_sec .. source_start_sec + audio_dur]
           (padded with frozen last frame if source runs out)
  audio  = source audio at SOURCE_VOL  +  narration TTS at NARR_VOL

All shots concat back-to-back — no black intro/outro, no freeze gaps.
The narration audio drives the visual duration of every shot.

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
import time
from pathlib import Path

import requests

# Pipeline helpers live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import db

RAW_BASE = Path("/video/youtube-clips/raw")
OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")

# 16:9 standard. Phase 3 adds 9:16 fan-out.
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

# Volume balance for "narrator on top, original as ambience" feel.
# SOURCE_VOL is the original English audio multiplier; very low so the
# narration dominates but you can still tell the original speaker is
# there. NARR_VOL boosts Azure TTS — its native level is around -16
# LUFS which feels quiet against modern YouTube/Bilibili content.
SOURCE_VOL = 0.10
NARR_VOL = 1.6

# Defaults; can be overridden by EDL `voice` / `rate_pct` fields.
DEFAULT_VOICE = "zh-CN-YunxiNeural"
DEFAULT_RATE_PCT = 15


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


def tts(text: str, out_path: Path, voice: str, rate_pct: int) -> Path:
    """Azure Neural TTS with a prosody rate boost wrapped around the line.

    A modest +15-20% rate is the difference between "AI assistant reading
    a manual" and "UP 主 actually narrating". Adjust per-EDL if Claude
    flags the line as needing more deliberate pacing.
    """
    region = os.environ["AZURE_SPEECH_REGION"]
    key = os.environ["AZURE_SPEECH_KEY"]
    sign = "+" if rate_pct >= 0 else ""
    ssml = (
        f'<speak version="1.0" xml:lang="zh-CN">'
        f'<voice name="{voice}">'
        f'<prosody rate="{sign}{rate_pct}%">{_escape_xml(text)}</prosody>'
        f'</voice>'
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


def _escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def render_shot(
    source: Path,
    source_start: float,
    duration: float,
    narration_audio: Path,
    out: Path,
    source_total_dur: float,
) -> None:
    """Render one shot to a self-contained mp4.

    Visual: source[source_start .. source_start + duration]. If the source
    range runs short of `duration` (clipped to source end), pad the visual
    with a frozen last frame.

    Audio: source@SOURCE_VOL mixed with narration_audio@NARR_VOL.
    """
    # How much of the visual we can actually take from the source before
    # the source ends; the rest is filled with frozen last frame via tpad.
    available = max(0.0, source_total_dur - source_start)
    visual_take = min(duration, available)
    pad_dur = max(0.0, duration - visual_take)

    # Build filter chain. Two sub-filters on the video and on the audio.
    # tpad clones the last frame to extend the visual; apad would extend
    # the audio with silence — we don't need that here because the source
    # audio chain ends at `visual_take` and amix with `duration=longest`
    # will let narration carry past it.
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
        f"tpad=stop_mode=clone:stop_duration={pad_dur:.3f},"
        f"setsar=1"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{source_start:.3f}", "-t", f"{visual_take:.3f}",
        "-i", str(source),
        "-i", str(narration_audio),
        "-filter_complex",
        f"[0:v]{vf}[v];"
        f"[0:a]volume={SOURCE_VOL}[bg];"
        f"[1:a]volume={NARR_VOL}[fg];"
        f"[bg][fg]amix=inputs=2:duration=longest:dropout_transition=0,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{duration:.3f}",
        *VIDEO_ARGS, *AUDIO_ARGS,
        str(out),
    ]
    subprocess.run(cmd, check=True)


def concat(parts: list[Path], out: Path, work_dir: Path) -> None:
    list_file = work_dir / "concat-list.txt"
    list_file.write_text(
        "\n".join(f"file '{p}'" for p in parts), encoding="utf-8"
    )
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

    shots = edl.get("shots", [])
    if not shots:
        sys.exit("EDL has no shots")

    voice = edl.get("voice", DEFAULT_VOICE)
    rate_pct = int(edl.get("rate_pct", DEFAULT_RATE_PCT))
    source_dur = ffprobe_duration(source)

    work_dir = job_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    print(f"voice: {voice}  rate: +{rate_pct}%  shots: {len(shots)}")
    print(f"source_dur: {source_dur:.1f}s")

    parts: list[Path] = []
    overall_t0 = time.monotonic()

    for i, sh in enumerate(shots):
        narr_text = sh["narration"]
        src_start = float(sh["source_start_sec"])

        label = stage(f"s{i:02d} tts ({len(narr_text)}c)")
        narr_audio = work_dir / f"s{i:02d}_narr.mp3"
        tts(narr_text, narr_audio, voice, rate_pct)
        narr_dur = ffprobe_duration(narr_audio)
        done(label)

        label = stage(f"s{i:02d} shot ({narr_dur:.1f}s, src@{src_start:.1f})")
        shot_mp4 = work_dir / f"s{i:02d}_shot.mp4"
        render_shot(source, src_start, narr_dur, narr_audio, shot_mp4, source_dur)
        done(label)
        parts.append(shot_mp4)

    label = stage("concat")
    out = job_dir / "render.mp4"
    concat(parts, out, work_dir)
    done(label)

    overall = time.monotonic() - overall_t0
    final_dur = ffprobe_duration(out)
    size_bytes = out.stat().st_size
    size_mb = size_bytes / 1024 / 1024

    # Persist the Output row. job_id was stamped into edl.json by
    # edl-prototype.py; if it's missing (legacy EDL pre-DB), skip the
    # write and let the backfill script catch up.
    job_id = edl.get("job_id")
    output_id = None
    if job_id:
        platform = (
            (edl.get("output", {}) if isinstance(edl.get("output"), dict) else {}).get("platform")
            or "bilibili_long"
        )
        output_id = db.insert_output(
            job_id=job_id,
            platform=platform,
            aspect_ratio="16:9",
            language="zh",
            path=str(out),
            duration_sec=final_dur,
            file_size_bytes=size_bytes,
            title=edl.get("title_zh"),
            description=edl.get("description_zh"),
            tags=edl.get("tags_zh"),
            status="ready",
        )
        # Mark Job complete now that we have a ready Output.
        with db.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = 'completed', completed_at = NOW() "
                "WHERE id = %s",
                (job_id,),
            )

    print()
    print("=" * 60)
    print(f"  output:    {out}")
    print(f"  duration:  {final_dur:.1f}s ({final_dur/60:.1f} min)")
    print(f"  size:      {size_mb:.1f} MB")
    print(f"  shots:     {len(shots)}")
    print(f"  total:     {overall:.1f}s")
    if output_id:
        print(f"  db:        job_id={job_id} output_id={output_id}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
