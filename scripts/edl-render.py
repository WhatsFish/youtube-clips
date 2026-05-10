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


# ---- Subtitle burn-in ------------------------------------------------------
# We bake Chinese captions directly into the final mp4 (rather than ship a
# sidecar .srt) because the operator uploads to Bilibili / 抖音 / TikTok by
# hand, and those platforms either re-encode anyway or mangle external
# subtitle tracks. Bilibili-style burned subs also hit harder visually.
#
# We use ASS instead of SRT because libass's outline + shadow rendering on
# Chinese characters is much more readable over busy B-roll than SRT's
# default style.

# Bilibili-ish lower-third style: bold sans-serif, white fill, black
# outline, semi-transparent shadow. PlayRes is locked at 1280x720 to match
# render output so font sizes are predictable.
SUBTITLE_FONT = "Noto Sans CJK SC"
SUBTITLE_SIZE = 38
# Place subtitles above where most YouTube/Bloomberg/CNBC lower-thirds
# sit (roughly 0-90px from bottom). 110px clears the typical name-supers
# and ticker bars while still feeling like a subtitle, not a caption-card.
SUBTITLE_MARGIN_V = 110


def _ass_timestamp(sec: float) -> str:
    """Format float seconds as ASS H:MM:SS.cc (centiseconds, exactly 2 digits)."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    """Escape characters that have meaning to libass dialogue lines.

    Inside Dialogue text, the special tokens are `{...}` (override blocks)
    and `\\N` / `\\n` / `\\h` (line break / soft break / hard space). The
    raw narration shouldn't contain `{` or `}` or stray backslashes, but
    sanitize anyway so a future edit can't silently break rendering.
    """
    return (
        text.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\n", " ")
    )


def write_ass_subs(
    shot_durations: list[float],
    shots: list[dict],
    out_path: Path,
    play_w: int = W,
    play_h: int = H,
) -> None:
    """Generate an ASS subtitle file aligned to the concatenated render's
    timeline. Each shot becomes one Dialogue event spanning that shot's
    duration on the final timeline.
    """
    style = (
        # Format fields per V4+ spec; ASS colors are &HAABBGGRR (alpha,
        # then blue-green-red). White fill (&H00FFFFFF). Black outline
        # for stroke-on-busy-source-video (&H000000FF used as Secondary,
        # not actually rendered for static subs). 60%-alpha black box
        # behind text (&H99000000) — alpha 0x99 ≈ 60%, dark enough to
        # read white text over any source clutter (Bloomberg lower-
        # thirds, news tickers, b-roll graphics) but not so opaque that
        # it dominates the frame. BorderStyle=3 (opaque-ish box rendered
        # behind text) is the key to readability against busy B-roll;
        # outline mode (BorderStyle=1) blew away too easily over the
        # red CNBC banners during the dry-run frame check. Bold=1 for
        # stroke weight. Alignment=2 (bottom-center). MarginV from the
        # bottom edge of PlayResY.
        f"Style: Default,{SUBTITLE_FONT},{SUBTITLE_SIZE},"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,"
        "1,0,0,0,100,100,0,0,3,1.5,0,2,"
        f"60,60,{SUBTITLE_MARGIN_V},1"
    )
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_w}\n"
        f"PlayResY: {play_h}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    events = []
    t = 0.0
    for sh, dur in zip(shots, shot_durations):
        end = t + dur
        text = _ass_escape(sh.get("narration", ""))
        events.append(
            f"Dialogue: 0,{_ass_timestamp(t)},{_ass_timestamp(end)},"
            f"Default,,0,0,0,,{text}"
        )
        t = end
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def burn_subs(in_path: Path, ass_path: Path, out_path: Path) -> None:
    """Re-encode `in_path` with `ass_path` baked in, write to `out_path`.

    Uses ffmpeg's libass-backed `subtitles` filter. The path is passed
    through filter-graph quoting, which means single quotes wrap and
    `:` / `\\` need escaping if they appear in the path. We control the
    work_dir so this is always under a clean directory; the assertion
    catches a future regression that might place subs.ass in a hostile
    path.
    """
    sp = str(ass_path)
    assert ":" not in sp and "'" not in sp and "\\" not in sp, sp
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_path),
        "-vf", f"subtitles={sp}",
        # Keep audio passthrough; only video re-encodes.
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id", help="primary source's video_id (matches the EDL output dir)")
    args = ap.parse_args()

    if "AZURE_SPEECH_KEY" not in os.environ:
        sys.exit("source ~/.config/youtube-clips.env first")

    job_dir = OUT_BASE / args.video_id
    edl_path = job_dir / "edl.json"
    if not edl_path.exists():
        sys.exit(f"missing edl: {edl_path}")

    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    if edl.get("decision") != "make":
        sys.exit(f"EDL decision is {edl.get('decision')!r}; nothing to render")

    shots = edl.get("shots", [])
    if not shots:
        sys.exit("EDL has no shots")

    # Resolve sources. v4 EDLs carry an explicit `sources[]`; pre-v4
    # single-source EDLs only have shots[*].source_start_sec and the
    # implicit assumption that the source mp4 lives at RAW_BASE/<arg>.
    sources_meta = edl.get("sources")
    if sources_meta:
        source_paths: list[Path] = []
        source_durs: list[float] = []
        for i, s in enumerate(sources_meta):
            sp = RAW_BASE / s["video_id"] / "source.mp4"
            if not sp.exists():
                sys.exit(f"missing source mp4 for source_idx={i}: {sp}")
            source_paths.append(sp)
            source_durs.append(ffprobe_duration(sp))
        print(f"sources: {len(source_paths)} ({', '.join(s['video_id'] for s in sources_meta)})")
    else:
        sp = RAW_BASE / args.video_id / "source.mp4"
        if not sp.exists():
            sys.exit(f"missing source: {sp}")
        source_paths = [sp]
        source_durs = [ffprobe_duration(sp)]
        print(f"sources: 1 (legacy single-source EDL, video_id={args.video_id})")

    voice = edl.get("voice", DEFAULT_VOICE)
    rate_pct = int(edl.get("rate_pct", DEFAULT_RATE_PCT))

    work_dir = job_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    print(f"voice: {voice}  rate: +{rate_pct}%  shots: {len(shots)}")

    parts: list[Path] = []
    shot_durations: list[float] = []
    overall_t0 = time.monotonic()

    for i, sh in enumerate(shots):
        narr_text = sh["narration"]
        src_idx = int(sh.get("source_idx", 0))
        if src_idx < 0 or src_idx >= len(source_paths):
            sys.exit(f"shot {i}: source_idx={src_idx} out of range (have {len(source_paths)} sources)")
        src_start = float(sh["source_start_sec"])

        label = stage(f"s{i:02d} tts ({len(narr_text)}c)")
        narr_audio = work_dir / f"s{i:02d}_narr.mp3"
        tts(narr_text, narr_audio, voice, rate_pct)
        narr_dur = ffprobe_duration(narr_audio)
        done(label)

        label = stage(f"s{i:02d} shot ({narr_dur:.1f}s, src{src_idx}@{src_start:.1f})")
        shot_mp4 = work_dir / f"s{i:02d}_shot.mp4"
        render_shot(
            source_paths[src_idx],
            src_start,
            narr_dur,
            narr_audio,
            shot_mp4,
            source_durs[src_idx],
        )
        done(label)
        parts.append(shot_mp4)
        shot_durations.append(narr_dur)

    label = stage("concat")
    concat_mp4 = work_dir / "concat.mp4"
    concat(parts, concat_mp4, work_dir)
    done(label)

    # Burn Chinese subtitles into the final mp4. The pre-sub concat is
    # kept under _work/ so a future debug pass can A/B compare; the
    # operator-facing artifact is render.mp4 (with subs).
    label = stage("subtitles")
    ass_path = work_dir / "subs.ass"
    write_ass_subs(shot_durations, shots, ass_path)
    out = job_dir / "render.mp4"
    burn_subs(concat_mp4, ass_path, out)
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
