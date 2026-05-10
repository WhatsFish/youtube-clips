"""Voice-activity detection on a source audio track.

Used by the renderer to duck source audio further (≈0.03) when the source
is *actively speaking English*, while keeping a "still here" floor (≈0.10)
during music / silence / pure ambient. Going hard to 0 during English
speech sounds unnatural — the picture suddenly feels muted; a small floor
lets the source remain present without competing with the Chinese
narration.

Implementation notes:
  - WebRTC VAD operates on 16 kHz mono 16-bit PCM, in fixed-size frames
    (10 / 20 / 30 ms). We use 30 ms = 480 samples = 960 bytes per frame.
  - Aggressiveness 2 of {0,1,2,3}: balanced (3 is too eager and clips
    soft speech; 0 leaks too much ambient).
  - Raw frame-level decisions chatter every word boundary; we post-process
    by merging short silences (< 0.5 s) into surrounding speech and
    dropping isolated tiny speech blips (< 0.2 s). Result is a clean set
    of speech *windows* that map sensibly onto an ffmpeg volume envelope.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import webrtcvad

# webrtcvad's frame must be one of these sample sizes at 16 kHz.
_FRAME_MS = 30
_SAMPLE_RATE = 16_000
_FRAME_SAMPLES = _SAMPLE_RATE * _FRAME_MS // 1000   # 480
_FRAME_BYTES = _FRAME_SAMPLES * 2                   # 960 (16-bit)

# Smoothing thresholds (seconds). These are operator-tuned for narration
# B-roll context, not generic VAD use. Slightly favors over-recall (more
# speech-marked time) so we don't accidentally let a clear English line
# leak through at the higher 0.10 floor.
_MIN_SPEECH_RUN = 0.20
_MAX_SILENCE_GAP = 0.50

# WebRTC VAD aggressiveness 0..3. 2 = balanced.
_AGGRESSIVENESS = 2


def speech_intervals(audio_or_video: Path) -> list[tuple[float, float]]:
    """Return [(start_sec, end_sec)] for windows where the source is speaking.

    Accepts any file ffmpeg can read; we re-encode to a 16 kHz mono
    16-bit WAV in a temp file, run VAD over that, then drop the temp file.
    """
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "vad.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(audio_or_video),
                "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                "-acodec", "pcm_s16le",
                str(wav),
            ],
            check=True,
        )
        with contextlib.closing(wave.open(str(wav), "rb")) as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == _SAMPLE_RATE
            pcm = wf.readframes(wf.getnframes())

    vad = webrtcvad.Vad(_AGGRESSIVENESS)
    flags: list[bool] = []
    n = len(pcm) // _FRAME_BYTES
    for i in range(n):
        frame = pcm[i * _FRAME_BYTES:(i + 1) * _FRAME_BYTES]
        flags.append(vad.is_speech(frame, _SAMPLE_RATE))

    # Frame-level → coalesce into contiguous runs.
    runs: list[tuple[bool, int, int]] = []  # (is_speech, start_frame, end_frame_exclusive)
    if flags:
        cur = flags[0]
        start = 0
        for i in range(1, len(flags)):
            if flags[i] != cur:
                runs.append((cur, start, i))
                cur, start = flags[i], i
        runs.append((cur, start, len(flags)))

    # Smooth: any silence run < _MAX_SILENCE_GAP sandwiched between speech
    # runs gets flipped to speech (real conversational pauses are short).
    frames_per_sec = 1000 / _FRAME_MS
    max_gap_frames = int(_MAX_SILENCE_GAP * frames_per_sec)
    min_speech_frames = int(_MIN_SPEECH_RUN * frames_per_sec)

    smoothed = list(runs)
    i = 0
    while i < len(smoothed):
        is_speech, s, e = smoothed[i]
        if not is_speech and 0 < i < len(smoothed) - 1:
            prev_speech, _, _ = smoothed[i - 1]
            next_speech, _, _ = smoothed[i + 1]
            if prev_speech and next_speech and (e - s) <= max_gap_frames:
                # Merge prev + this + next into one speech run.
                _, ps, _ = smoothed[i - 1]
                _, _, ne = smoothed[i + 1]
                smoothed[i - 1: i + 2] = [(True, ps, ne)]
                continue  # don't advance — re-examine new merged run
        i += 1

    # Drop tiny speech blips (< _MIN_SPEECH_RUN). Convert them to silence.
    smoothed = [
        (False, s, e) if is_speech and (e - s) < min_speech_frames else (is_speech, s, e)
        for is_speech, s, e in smoothed
    ]

    # Re-coalesce after blip drop.
    coalesced: list[tuple[bool, int, int]] = []
    for is_speech, s, e in smoothed:
        if coalesced and coalesced[-1][0] == is_speech:
            _, ps, _ = coalesced[-1]
            coalesced[-1] = (is_speech, ps, e)
        else:
            coalesced.append((is_speech, s, e))

    # Emit only speech intervals as wall-clock seconds.
    out: list[tuple[float, float]] = []
    for is_speech, s, e in coalesced:
        if is_speech:
            out.append((s / frames_per_sec, e / frames_per_sec))
    return out
