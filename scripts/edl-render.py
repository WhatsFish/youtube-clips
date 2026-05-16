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
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Pipeline helpers live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import db, events
from pipeline.vad import speech_intervals, _has_audio_stream
from pipeline.bgm import pick_track

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
# Two source levels driven by VAD on the source audio:
#   - SOURCE_VOL_SPEECH: when the source is actively speaking English,
#     duck further so the narrator's Chinese stays clearly intelligible.
#     Not 0 because dropping the source completely sounds unnatural —
#     the picture suddenly feels muted; a small floor keeps the source
#     "present" without competing.
#   - SOURCE_VOL_AMBIENT: when the source is silent / music / room tone,
#     restore to the previous default; this is the ambience floor and
#     gives the rendered video a "still rolling" feel during cutaways.
# NARR_VOL boosts Azure TTS — its native level is around -16 LUFS which
# feels quiet against modern YouTube/Bilibili content.
SOURCE_VOL_SPEECH = 0.03
SOURCE_VOL_AMBIENT = 0.10
NARR_VOL = 1.6

# BGM levels. Three modes the EDL agent chooses from:
#   - off:      no BGM at all (severe / dense topics where music distracts)
#   - constant: fixed level under everything (vibe-forward content)
#   - dynamic:  ducks down during source speech, rises during silence —
#               mirrors the source-VAD envelope inverted, so BGM fills
#               the dead air left by source cutaways without competing
#               with source-on-camera speech.
# Levels picked low; narration at 1.6× still dominates by ~10×.
# Raised 2026-05-14 — operator reported BGM 听不见 in producer-mode renders.
# Old values (0.08/0.04/0.10) were calibrated for commentary mode where
# source vlogs have their own speech competing; in producer mode the
# sources are silent (Pexels/CogView/Doubao audio stripped), so BGM at
# 0.04 sat ~32 dB below narration (NARR_VOL=1.6 ≈ +4 dB) and was
# effectively inaudible.
BGM_VOL_CONSTANT = 0.18
BGM_VOL_SPEECH = 0.10   # while source is speaking, BGM ducks lower
BGM_VOL_AMBIENT = 0.22  # while source is silent, BGM fills the gap

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


def make_silent_mp3(out_path: Path, duration_sec: float) -> Path:
    """Generate a silent mp3 of the given duration. Used when a shot's
    narration is intentionally empty (lifestyle channels often let the
    picture + bgm carry — see edl-commentary.v2 prompt). Single-channel
    24kHz to match the Azure TTS output format so downstream mixing
    doesn't need a separate resample step.
    """
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
            "-t", f"{duration_sec:.3f}",
            "-c:a", "libmp3lame", "-b:a", "160k",
            str(out_path),
        ],
        check=True,
    )
    return out_path


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


def _build_volume_expr(
    speech_intervals_global: list[tuple[float, float]],
    shot_start: float,
    shot_dur: float,
) -> str:
    """Translate global speech intervals into an ffmpeg volume expression
    in shot-local time (post `-ss shot_start`, ffmpeg's `t` starts at 0).

    Returns either a constant (when no speech intersects the shot window)
    or a piecewise `if(or(...), SPEECH, AMBIENT)` expression. The
    `between(t,a,b)` primitives are summed (each returns 0 or 1) and the
    sum is treated as a boolean — non-zero means we're inside any speech
    window. Trim each interval to the shot window and skip degenerate
    ones (< 50 ms) so the expression doesn't bloat with no audible gain.
    """
    shot_end = shot_start + shot_dur
    local: list[tuple[float, float]] = []
    for vs, ve in speech_intervals_global:
        if ve <= shot_start or vs >= shot_end:
            continue
        ls = max(0.0, vs - shot_start)
        le = min(shot_dur, ve - shot_start)
        if le - ls >= 0.05:
            local.append((ls, le))
    if not local:
        return f"{SOURCE_VOL_AMBIENT:.3f}"
    # ffmpeg's expression evaluator has no `>` operator — `if(cond, a, b)`
    # itself treats any non-zero `cond` as true. Each `between` returns
    # 0 or 1, so the sum is 0 when no interval matches and ≥1 inside any
    # interval; passing the sum directly to `if` is the right shape.
    parts = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in local)
    return f"if({parts},{SOURCE_VOL_SPEECH:.3f},{SOURCE_VOL_AMBIENT:.3f})"


def render_shot(
    source: Path,
    source_start: float,
    narr_dur: float,
    narration_audio: Path,
    out: Path,
    source_total_dur: float,
    *,
    speech_intervals_global: list[tuple[float, float]] | None = None,
    tail_sec: float = 0.0,
    source_has_audio: bool = True,
) -> None:
    """Render one shot to a self-contained mp4.

    Visual: source[source_start .. source_start + narr_dur + tail_sec].
    If the source range runs short, pad the visual with a frozen last
    frame.

    Audio:
      - `source_has_audio=True` (commentary / synthesis on YouTube
        sources): mix source audio (ducked via VAD envelope, AMBIENT
        during tail) with narration @ NARR_VOL.
      - `source_has_audio=False` (producer mode on Pexels stock —
        video-only files): no source audio mix; the only audio is
        narration, then silence during the tail (BGM at the concat
        layer will still fill the tail if mode != off).

    A `tail_sec` of 0 collapses to pre-pacing-aware behaviour exactly.
    """
    duration = narr_dur + tail_sec
    available = max(0.0, source_total_dur - source_start)
    visual_take = min(duration, available)
    pad_dur = max(0.0, duration - visual_take)

    # When the source can't cover the full narration (typically a Doubao
    # AI-video capped at 10s playing under a 13-18s narration), we used
    # to freeze the last frame via tpad=stop_mode=clone — operator
    # perceived as "后面长时间静止". For producer-mode shots (source_start=0,
    # source has no audio to align) we instead loop the source and cross-
    # fade between iterations so motion stays alive AND the loop seam is
    # hidden.
    #
    # Loop branch only kicks in when (a) gap >0.3s, (b) source_start=0
    # (producer mode; commentary uses a mid-source slice), (c) no source
    # audio to keep in sync.
    XFADE_SEC = 1.0
    will_loop_source = (
        pad_dur > 0.3 and source_start < 0.001 and not source_has_audio
    )
    # Crossfade only feasible when each loop iteration has enough visible
    # content beyond the fade itself (else the whole iteration is just a
    # fade in/out). Sub-1.5s sources fall back to a plain -stream_loop.
    use_xfade_loop = will_loop_source and source_total_dur > XFADE_SEC + 0.5

    if use_xfade_loop:
        # Each extra iteration past the first contributes
        # (source_total_dur - XFADE_SEC) of visible time (the last XFADE_SEC
        # of iter N overlaps with the first XFADE_SEC of iter N+1).
        # Total visible = src + (n-1)*(src - xfade). Solve for n:
        visible_per_extra = source_total_dur - XFADE_SEC
        n_iter = math.ceil((duration - source_total_dur) / visible_per_extra) + 1
        n_iter = max(2, n_iter)
        # vf applied AFTER xfade chain, not per-iteration (all iterations
        # are the same source so all the same resolution already).
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1"
        )
    elif will_loop_source:
        n_iter = 1  # naive stream_loop, no xfade chain
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1"
        )
    else:
        n_iter = 1
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
            f"tpad=stop_mode=clone:stop_duration={pad_dur:.3f},"
            f"setsar=1"
        )

    # Pad audio to exactly `duration` (= narr_dur + tail_sec). Without
    # this, audio ends at narration's end (and concat at -c copy treats
    # the short audio frame as the shot's full audio length), so the
    # next shot's audio "leaks" into the previous shot's tail —
    # accumulating A/V drift across shots that the operator observed as
    # "声音先出来，画面后切". apad with whole_dur extends the audio
    # stream with silence up to exactly `duration`; -t duration then
    # truncates so video and audio are guaranteed equal length.
    apad = f"apad=whole_dur={duration:.3f}"

    # Video filter graph head: in xfade-loop mode, we feed N inputs of
    # the same source file and crossfade between them; otherwise the
    # single [0:v] gets vf directly. After the head, the final label is
    # [v] regardless of branch — downstream audio logic doesn't change.
    if use_xfade_loop:
        # Chain xfade across the N iterations. accum is the offset (s)
        # into the cumulative timeline at which each xfade begins; it
        # advances by visible_per_extra (= src_dur - xfade) per step.
        visible_per_extra = source_total_dur - XFADE_SEC
        xfade_parts: list[str] = []
        prev_label = "0:v"
        accum = source_total_dur - XFADE_SEC
        for j in range(1, n_iter):
            out_label = "vxfade" if j == n_iter - 1 else f"vx{j:02d}"
            xfade_parts.append(
                f"[{prev_label}][{j}:v]xfade=transition=fade:"
                f"duration={XFADE_SEC}:offset={accum:.3f}[{out_label}]"
            )
            prev_label = out_label
            accum += visible_per_extra
        video_head = ";".join(xfade_parts) + f";[vxfade]{vf}[v]"
        narration_idx = n_iter
    else:
        video_head = f"[0:v]{vf}[v]"
        narration_idx = 1

    if source_has_audio:
        intervals = speech_intervals_global or []
        vad_expr = _build_volume_expr(intervals, source_start, visual_take)
        if tail_sec > 0:
            vol_expr = f"if(lt(t,{narr_dur:.3f}),{vad_expr},{SOURCE_VOL_AMBIENT:.3f})"
            bg_filter = f"[0:a]volume=volume='{vol_expr}':eval=frame[bg]"
        else:
            vol_expr = vad_expr
            bg_filter = (
                f"[0:a]volume=volume='{vol_expr}':eval=frame[bg]"
                if "if(" in vol_expr
                else f"[0:a]volume={vol_expr}[bg]"
            )
        # amix normalize=0 keeps each input at its pre-filter level. Default
        # normalize=1 attenuates by 1/N (~6 dB for two inputs), which made
        # narration audibly quieter on shots where the source carried an
        # audio track (even a silent -91 dB one from Pexels, or Doubao's
        # AI-generated track) vs shots whose source had no audio stream at
        # all — operator perceived as 解说忽大忽小. Source levels are already
        # 0.03-0.10 via vad_expr, so no clipping risk when summed with
        # narration at 1.6.
        filter_complex = (
            f"{video_head};"
            f"{bg_filter};"
            f"[{narration_idx}:a]volume={NARR_VOL}[fg];"
            f"[bg][fg]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
            f"{apad},aresample=48000[a]"
        )
    else:
        # No source audio (typical Pexels stock / Doubao stripped). Narration
        # alone, padded with silence to span the full shot duration so the
        # post-tail silence is real silence frames.
        filter_complex = (
            f"{video_head};"
            f"[{narration_idx}:a]volume={NARR_VOL},{apad},aresample=48000[a]"
        )

    # Input args:
    #   - xfade-loop mode: N -i source repeated (each gets indep xfade input)
    #   - naive stream_loop: -stream_loop -1 -i source
    #   - normal: -ss / -t pre-input trim + single -i
    if use_xfade_loop:
        input_v_args: list[str] = []
        for _ in range(n_iter):
            input_v_args += ["-i", str(source)]
    elif will_loop_source:
        input_v_args = ["-stream_loop", "-1", "-i", str(source)]
    else:
        input_v_args = [
            "-ss", f"{source_start:.3f}", "-t", f"{visual_take:.3f}",
            "-i", str(source),
        ]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        *input_v_args,
        "-i", str(narration_audio),
        "-filter_complex",
        filter_complex,
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


# ---- BGM mix --------------------------------------------------------------


def project_speech_to_concat(
    shots: list[dict],
    source_speech: list[list[tuple[float, float]]],
    shot_durations: list[float],
) -> list[tuple[float, float]]:
    """Map per-source speech intervals onto the concat timeline.

    For each shot, look up its (source_idx, source_start_sec, dur). Find
    the speech intervals from that source overlapping the shot's source
    window, clip them to the window, shift by the shot's offset on the
    concat timeline. Then merge any neighbouring spans (a tiny gap from
    rounding shouldn't fragment the BGM envelope).
    """
    intervals: list[tuple[float, float]] = []
    concat_t = 0.0
    for sh, dur in zip(shots, shot_durations):
        idx = int(sh.get("source_idx", 0))
        s_start = float(sh["source_start_sec"])
        s_end = s_start + dur
        if 0 <= idx < len(source_speech):
            for vs, ve in source_speech[idx]:
                if ve <= s_start or vs >= s_end:
                    continue
                local_s = max(0.0, vs - s_start)
                local_e = min(dur, ve - s_start)
                intervals.append((concat_t + local_s, concat_t + local_e))
        concat_t += dur
    intervals.sort()
    merged: list[tuple[float, float]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


def _bgm_volume_expr(
    mode: str,
    speech_concat: list[tuple[float, float]],
) -> str:
    """ffmpeg `volume` expression for the BGM mix, in concat-timeline `t`."""
    if mode == "constant":
        return f"{BGM_VOL_CONSTANT:.3f}"
    # mode == "dynamic": ducked during source speech, raised during ambient.
    # Same `between(t,a,b)` summation trick as the source ducker — non-zero
    # sum (ffmpeg eval treats as true) means we're inside speech.
    if not speech_concat:
        # No speech detected anywhere → behave like constant at the
        # ambient level (BGM fills everything).
        return f"{BGM_VOL_AMBIENT:.3f}"
    parts = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in speech_concat)
    return f"if({parts},{BGM_VOL_SPEECH:.3f},{BGM_VOL_AMBIENT:.3f})"


def mix_bgm(
    in_path: Path,
    bgm_path: Path,
    out_path: Path,
    *,
    mode: str,
    speech_concat: list[tuple[float, float]],
) -> None:
    """Mix `bgm_path` into `in_path`'s audio under `mode` rules, write to
    `out_path`. Loops BGM with `-stream_loop -1` so a short BGM track
    survives a long concat. `amix duration=first` truncates to the
    concat's length (ignoring any trailing BGM tail).

    Video is copied; only audio re-encodes. The subsequent subtitle-burn
    step then re-encodes video once. Net: each codec gets re-encoded
    exactly once across the full pipeline.
    """
    expr = _bgm_volume_expr(mode, speech_concat)
    bgm_filter = (
        f"[1:a]volume=volume='{expr}':eval=frame[bgm]"
        if "if(" in expr
        else f"[1:a]volume={expr}[bgm]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_path),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex",
        # normalize=0 keeps each input at its pre-filter level. Without it,
        # ffmpeg's default amix normalize=1 averages inputs (each ÷ 2),
        # silently squashing BGM to half the level we set in BGM_VOL_*.
        # Same fix we applied to the per-shot amix in render_shot.
        f"{bgm_filter};"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


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


# Max Chinese characters per subtitle line before we auto-wrap. ASS's
# native WrapStyle=0 (word-balance) fails on CJK because there are no
# word boundaries — long sentences just overflow off-screen. We split
# at Chinese punctuation as the natural breath beat.
SUBTITLE_MAX_CHARS_PER_LINE = 26
SUBTITLE_BREAK_CHARS = "，。；：、？！"


def _wrap_chinese_subtitle(text: str, max_chars: int = SUBTITLE_MAX_CHARS_PER_LINE) -> str:
    """Insert `\\N` line breaks into long Chinese narration at punctuation.

    Strategy: walk the string; once we've passed `max_chars` since the
    last break, the next punctuation char becomes a break point. Yields
    1-3 lines for any reasonable shanyang-class deep-mode narration
    (50-90 chars). Falls back to a hard split if no punctuation found.
    """
    if len(text) <= max_chars:
        return text
    parts: list[str] = []
    line_start = 0
    i = 0
    while i < len(text):
        # Check if we've crossed the soft threshold and hit a punct char
        if (i - line_start) >= max_chars and text[i] in SUBTITLE_BREAK_CHARS:
            parts.append(text[line_start : i + 1])
            line_start = i + 1
        i += 1
    tail = text[line_start:]
    # If no punctuation triggered a break (rare with shanyang content
    # since narration always has commas), force a hard split.
    if not parts:
        mid = max_chars
        return text[:mid] + "\\N" + text[mid:]
    if tail:
        parts.append(tail)
    return "\\N".join(s.lstrip() for s in parts)


def write_ass_subs(
    shot_durations: list[float],
    shots: list[dict],
    out_path: Path,
    play_w: int = W,
    play_h: int = H,
    *,
    narration_durations: list[float] | None = None,
    margin_v: int = SUBTITLE_MARGIN_V,
    max_chars_per_line: int = SUBTITLE_MAX_CHARS_PER_LINE,
    font_size: int = SUBTITLE_SIZE,
) -> None:
    """Generate an ASS subtitle file aligned to the concatenated render's
    timeline. Each shot becomes one Dialogue event.

    When `narration_durations` is supplied (pacing-aware path), each
    subtitle event spans only the narration audio's actual length — the
    subtitle disappears during the post-narration tail pause, matching
    what the viewer is hearing instead of staying on screen through
    silence. Without it, falls back to spanning the full shot duration
    (legacy behaviour for shots with no tail).
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
        f"Style: Default,{SUBTITLE_FONT},{font_size},"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,"
        "1,0,0,0,100,100,0,0,3,1.5,0,2,"
        f"60,60,{margin_v},1"
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
    nds = narration_durations if narration_durations is not None else shot_durations
    for sh, shot_dur, narr_dur in zip(shots, shot_durations, nds):
        # Subtitle timing tracks narration (what the viewer is hearing),
        # not the full shot. With pacing.inter_shot_pause_sec > 0 these
        # diverge and the subtitle correctly disappears during the
        # breathing pause.
        sub_end = t + narr_dur
        # Order matters: escape first (turns each `\` into `\\`), then
        # inject `\N` line breaks. If we wrapped first, our `\N` markers
        # would get doubled to `\\N` by escape and stop working as newlines.
        raw_narration = (sh.get("narration") or "").strip()
        # Silent shots: emit no Dialogue event at all — an empty Dialogue
        # line would render as a transparent 0-text overlay but it still
        # takes a slot in the ASS file and isn't useful.
        if raw_narration:
            text = _wrap_chinese_subtitle(
                _ass_escape(raw_narration),
                max_chars=max_chars_per_line,
            )
            events.append(
                f"Dialogue: 0,{_ass_timestamp(t)},{_ass_timestamp(sub_end)},"
                f"Default,,0,0,0,,{text}"
            )
        # Shot timeline still advances by the FULL shot duration so the
        # next subtitle starts at the right concat-time offset.
        t += shot_dur
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


# Final fade-out length on the entire concat — gives the video a clean
# audible "we're done" beat. Applied in burn_subs since that's the only
# pass guaranteed to run on every render (BGM mix is conditional).
FINAL_FADE_OUT_SEC = 1.5


# ----- multi-platform aspect support ------------------------------------
# Per-platform render spec. `aspect` = (w, h) target dimensions of the
# final file. `subtitle_*` overrides scale font / margin / line-wrap for
# narrower vertical canvases. Add a new platform = add a row here.
PLATFORM_SPEC: dict[str, dict] = {
    "bilibili_long": {
        "aspect": (1280, 720),
        "subtitle_font_size": 38,
        "subtitle_margin_v": 110,
        "subtitle_max_chars": 26,
        "output_name": "render.mp4",  # back-compat with existing slug-level path
    },
    "douyin": {
        "aspect": (720, 1280),  # 9:16
        "subtitle_font_size": 42,        # bigger for phone screens
        "subtitle_margin_v": 260,        # higher off bottom (above Douyin UI)
        "subtitle_max_chars": 14,        # narrower canvas
        "output_name": "render-douyin.mp4",
    },
    "tiktok": {
        "aspect": (720, 1280),
        "subtitle_font_size": 42,
        "subtitle_margin_v": 260,
        "subtitle_max_chars": 14,
        "output_name": "render-tiktok.mp4",
    },
    "youtube_long": {
        "aspect": (1280, 720),
        "subtitle_font_size": 38,
        "subtitle_margin_v": 110,
        "subtitle_max_chars": 26,
        "output_name": "render-youtube.mp4",
    },
    "youtube_shorts": {
        "aspect": (720, 1280),
        "subtitle_font_size": 42,
        "subtitle_margin_v": 260,
        "subtitle_max_chars": 14,
        "output_name": "render-shorts.mp4",
    },
}


def transform_to_vertical(in_path: Path, out_path: Path,
                          target_w: int = 720, target_h: int = 1280) -> None:
    """Letterbox transform 16:9 → 9:16 with blurred background fill.

    Background: source scaled to cover target_w×target_h, then heavily
    blurred — provides a frame-aware backdrop. Foreground: source scaled
    to target_w wide (keep aspect → ~target_w × 9·target_w/16 tall),
    centered. The TikTok / Douyin standard layout for repurposed
    horizontal content; visually clean and lossless of horizontal info.
    """
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_path),
        "-filter_complex",
        f"[0:v]split=2[bg_in][fg_in];"
        f"[bg_in]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},boxblur=30:2[bg];"
        f"[fg_in]scale={target_w}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]",
        "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def burn_subs(in_path: Path, ass_path: Path, out_path: Path) -> None:
    """Re-encode `in_path` with `ass_path` baked in, write to `out_path`.

    Also applies an audio fade-out over the last `FINAL_FADE_OUT_SEC`
    seconds so the render ends with a proper outro beat instead of
    cutting on a syllable. The audio re-encode is cheap (AAC, just a
    short tail) and consistent across BGM-on / BGM-off paths.

    Uses ffmpeg's libass-backed `subtitles` filter. The path is passed
    through filter-graph quoting, which means single quotes wrap and
    `:` / `\\` need escaping if they appear in the path. We control the
    work_dir so this is always under a clean directory; the assertion
    catches a future regression that might place subs.ass in a hostile
    path.
    """
    sp = str(ass_path)
    assert ":" not in sp and "'" not in sp and "\\" not in sp, sp
    in_dur = ffprobe_duration(in_path)
    fade_dur = min(FINAL_FADE_OUT_SEC, max(0.5, in_dur * 0.1))
    fade_start = max(0.0, in_dur - fade_dur)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_path),
        "-vf", f"subtitles={sp}",
        "-af", f"afade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        # AAC re-encode for the fade — fade filter requires PCM internally
        # and we're paying the audio re-encode cost here once.
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id", help="primary source's video_id (matches the EDL output dir)")
    ap.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Run id to attach events to (set by produce.py / produce-original.py)",
    )
    ap.add_argument(
        "--platforms",
        default="bilibili_long",
        help=(
            "Comma-separated list of platforms to render variants for. "
            "Each must be a key in PLATFORM_SPEC. Default: bilibili_long. "
            "Example: --platforms bilibili_long,douyin"
        ),
    )
    args = ap.parse_args()
    run_id = args.run_id
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    for p in platforms:
        if p not in PLATFORM_SPEC:
            sys.exit(f"unknown platform {p!r}; available: {list(PLATFORM_SPEC)}")

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
    # Producer-mode EDLs (Phase 2) carry sources[i].path pointing at
    # locally-downloaded Pexels stock clips — when present, that path
    # is authoritative and overrides the RAW_BASE convention.
    sources_meta = edl.get("sources")
    if sources_meta:
        source_paths: list[Path] = []
        source_durs: list[float] = []
        for i, s in enumerate(sources_meta):
            sp = Path(s["path"]) if s.get("path") else (RAW_BASE / s["video_id"] / "source.mp4")
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

    # Pre-compute, for each source: (a) whether it has an audio track at
    # all, and (b) VAD speech intervals if so. Pexels stock clips usually
    # ship video-only — VAD short-circuits to [] for those, and the
    # per-shot render skips the source-audio mix entirely.
    source_speech: list[list[tuple[float, float]]] = []
    source_has_audio: list[bool] = []
    for i, sp in enumerate(source_paths):
        has_aud = _has_audio_stream(sp)
        source_has_audio.append(has_aud)
        if not has_aud:
            print(f"  src{i}: no audio stream (Pexels stock?) — skipping VAD")
            source_speech.append([])
            continue
        label = stage(f"vad src{i}")
        ivs = speech_intervals(sp)
        speech_total = sum(e - s for s, e in ivs)
        print(
            f"  src{i}: {len(ivs)} speech intervals, "
            f"{speech_total:.1f}s of {source_durs[i]:.1f}s "
            f"({100 * speech_total / source_durs[i]:.0f}%)"
        )
        source_speech.append(ivs)
        done(label)

    voice = edl.get("voice", DEFAULT_VOICE)
    rate_pct = int(edl.get("rate_pct", DEFAULT_RATE_PCT))

    # Stage 2 (v7+) emits a `pacing` block; older EDLs don't and get a
    # zero pause = v6 behaviour exactly. Clamp [0, 3] for sanity.
    pacing_cfg = edl.get("pacing") or {}
    inter_shot_pause = float(pacing_cfg.get("inter_shot_pause_sec") or 0.0)
    inter_shot_pause = max(0.0, min(3.0, inter_shot_pause))
    pacing_tier = pacing_cfg.get("tier") or ("legacy" if not pacing_cfg else "unknown")

    work_dir = job_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    print(f"voice: {voice}  rate: +{rate_pct}%  shots: {len(shots)}")
    print(f"pacing: {pacing_tier}  inter_shot_pause: {inter_shot_pause:.1f}s")
    events.emit(run_id, "render_setup", "done",
                f"voice={voice} pacing={pacing_tier} shots={len(shots)}",
                voice=voice, rate_pct=rate_pct, shots=len(shots),
                pacing_tier=pacing_tier)

    parts: list[Path] = []
    shot_durations: list[float] = []
    narration_durations: list[float] = []
    overall_t0 = time.monotonic()

    for i, sh in enumerate(shots):
        narr_text = (sh.get("narration") or "").strip()
        src_idx = int(sh.get("source_idx", 0))
        if src_idx < 0 or src_idx >= len(source_paths):
            sys.exit(f"shot {i}: source_idx={src_idx} out of range (have {len(source_paths)} sources)")
        src_start = float(sh["source_start_sec"])

        events.emit(run_id, "render_shot", "start",
                    f"s{i:02d}: {narr_text[:50] or '(silent)'}",
                    shot_idx=i, chars=len(narr_text))
        narr_audio = work_dir / f"s{i:02d}_narr.mp3"
        if narr_text:
            label = stage(f"s{i:02d} tts ({len(narr_text)}c)")
            tts(narr_text, narr_audio, voice, rate_pct)
            narr_dur = ffprobe_duration(narr_audio)
            done(label)
        else:
            # Silent shot — lifestyle channels can let picture + bgm carry.
            # Duration: shot.silent_duration_sec if set, else 5s default
            # (long enough to hold a beat without dragging).
            narr_dur = float(sh.get("silent_duration_sec") or 5.0)
            label = stage(f"s{i:02d} silent ({narr_dur:.1f}s)")
            make_silent_mp3(narr_audio, narr_dur)
            done(label)

        # Every shot — including the last — gets the trailing pause.
        # Earlier we suppressed it on the final shot fearing the video
        # would feel stalled; in practice the operator reported the
        # opposite ("结束得有点突兀"), and a clean tail + audio fade-out
        # at the very end gives a proper "video's over" beat instead of
        # cutting on a syllable.
        tail = inter_shot_pause
        shot_dur = narr_dur + tail

        label = stage(
            f"s{i:02d} shot ({narr_dur:.1f}s narr + {tail:.1f}s tail, "
            f"src{src_idx}@{src_start:.1f})"
        )
        shot_mp4 = work_dir / f"s{i:02d}_shot.mp4"
        render_shot(
            source_paths[src_idx],
            src_start,
            narr_dur,
            narr_audio,
            shot_mp4,
            source_durs[src_idx],
            speech_intervals_global=source_speech[src_idx],
            source_has_audio=source_has_audio[src_idx],
            tail_sec=tail,
        )
        done(label)
        parts.append(shot_mp4)
        shot_durations.append(shot_dur)
        narration_durations.append(narr_dur)
        events.emit(run_id, "render_shot", "done",
                    f"s{i:02d} {shot_dur:.1f}s",
                    shot_idx=i, duration_sec=round(shot_dur, 2))

    label = stage("concat")
    events.emit(run_id, "render_concat", "start", f"{len(parts)} parts")
    concat_mp4 = work_dir / "concat.mp4"
    concat(parts, concat_mp4, work_dir)
    done(label)

    # BGM mix (if EDL says so and a track exists for the requested mood).
    # Done at the concat level rather than per-shot — one ffmpeg pass
    # over the entire timeline is simpler than juggling BGM offsets per
    # shot, and the dynamic-volume expression naturally tracks
    # concat-time speech windows projected from per-source VAD.
    bgm_cfg = edl.get("bgm") or {}
    bgm_mode = (bgm_cfg.get("mode") or "off").lower()
    bgm_mood = (bgm_cfg.get("mood") or "neutral").lower()
    bgm_input = concat_mp4
    if bgm_mode in ("constant", "dynamic"):
        track = pick_track(bgm_mood)
        if track is None:
            print(
                f"[bgm]  mode={bgm_mode} mood={bgm_mood} → "
                f"no tracks under bgm/{bgm_mood}/, skipping"
            )
        else:
            label = stage(f"bgm ({bgm_mode}, {bgm_mood}: {track.name})")
            speech_concat = (
                project_speech_to_concat(shots, source_speech, shot_durations)
                if bgm_mode == "dynamic"
                else []
            )
            bgm_mixed = work_dir / "concat-with-bgm.mp4"
            mix_bgm(
                concat_mp4,
                track,
                bgm_mixed,
                mode=bgm_mode,
                speech_concat=speech_concat,
            )
            bgm_input = bgm_mixed
            done(label)
    else:
        if bgm_mode != "off":
            print(f"[bgm]  unknown mode={bgm_mode!r}, treating as off")

    events.emit(run_id, "render_concat", "done", "concat.mp4 written")

    # --- Multi-platform fan-out: one bgm_input → N final renders ---------
    # Each platform in --platforms gets its own aspect transform (no-op for
    # 16:9 platforms; letterbox-blur for 9:16) + its own ASS file (different
    # margin/font/wrap) + its own outputs DB row. Doesn't re-render shots.
    job_id = edl.get("job_id")
    output_ids: list[tuple[str, int | None, Path, float, int]] = []
    for platform in platforms:
        spec = PLATFORM_SPEC[platform]
        tgt_w, tgt_h = spec["aspect"]
        is_vertical = tgt_h > tgt_w
        out = job_dir / spec["output_name"]
        # 1. (vertical only) Transform concat-with-bgm to 9:16 with blur fill
        if is_vertical:
            label = stage(f"{platform} vertical transform → {tgt_w}x{tgt_h}")
            events.emit(run_id, "render_transform", "start", f"{platform} → vertical")
            vert_pre_subs = work_dir / f"vert-{platform}.mp4"
            transform_to_vertical(bgm_input, vert_pre_subs, tgt_w, tgt_h)
            done(label)
            events.emit(run_id, "render_transform", "done", platform)
            burn_input = vert_pre_subs
        else:
            burn_input = bgm_input
        # 2. ASS subtitles sized for the platform's canvas
        label = stage(f"{platform} subtitles")
        events.emit(run_id, "render_subs", "start", f"burn subs {platform}")
        ass_path = work_dir / f"subs-{platform}.ass"
        write_ass_subs(
            shot_durations, shots, ass_path,
            play_w=tgt_w, play_h=tgt_h,
            narration_durations=narration_durations,
            margin_v=spec["subtitle_margin_v"],
            max_chars_per_line=spec["subtitle_max_chars"],
            font_size=spec["subtitle_font_size"],
        )
        burn_subs(burn_input, ass_path, out)
        done(label)
        events.emit(run_id, "render_subs", "done", f"{platform}: {out.name}")
        # 3. Persist outputs row per platform
        out_dur = ffprobe_duration(out)
        out_size = out.stat().st_size
        output_id: int | None = None
        if job_id:
            output_id = db.insert_output(
                job_id=job_id,
                platform=platform,
                aspect_ratio=f"{tgt_w}:{tgt_h}",
                language="zh",
                path=str(out),
                duration_sec=out_dur,
                file_size_bytes=out_size,
                title=edl.get("title_zh"),
                description=edl.get("description_zh"),
                tags=edl.get("tags_zh"),
                status="ready",
            )
        output_ids.append((platform, output_id, out, out_dur, out_size))

    if job_id:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = 'completed', completed_at = NOW() "
                "WHERE id = %s",
                (job_id,),
            )

    overall = time.monotonic() - overall_t0
    print()
    print("=" * 60)
    for platform, output_id, out, out_dur, out_size in output_ids:
        size_mb = out_size / 1024 / 1024
        print(f"  [{platform}] {out}  {out_dur:.1f}s  {size_mb:.1f} MB"
              + (f"  output_id={output_id}" if output_id else ""))
    print(f"  shots:     {len(shots)}")
    print(f"  total:     {overall:.1f}s")
    if job_id:
        print(f"  db:        job_id={job_id}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
