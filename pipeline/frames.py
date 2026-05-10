"""Frame sampling for vision-aware Stage 1.

Used when a source has no usable English captions (manual or auto). We
sample one frame every `interval_sec` seconds at 480p jpg q80, then
hand the directory to `claude -p --tools Read --add-dir <frames>` so
the agent can `Read` each frame as a visual input.

Why these choices:
  - 30 s sampling: catches scene changes without overwhelming the agent.
    A 10-min vlog → 20 frames; reading 20 images sequentially via the
    Read tool takes ~30-60 s of agent wall time, well under our cost
    budget.
  - 480p (854x480): preserves text/UI legibility (timestamps, sub-titles
    from source, app overlays, signage) while keeping each jpg under
    ~80 KB.
  - q4 (≈ q80 in conventional terms): better than YouTube thumbnail
    quality, smaller than full HD. Visual content is dominated by
    edge/contrast — quality 4 is enough.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_INTERVAL_SEC = 30
DEFAULT_HEIGHT = 480


def sample_frames(
    source_mp4: Path,
    out_dir: Path,
    *,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
    height: int = DEFAULT_HEIGHT,
) -> list[Path]:
    """Extract one jpg every `interval_sec` from `source_mp4` into `out_dir`.

    Returns the sorted list of frame paths in chronological order.
    Idempotent: if the directory already has frame-001.jpg the call
    re-extracts and overwrites — this is cheap (under 5 s for typical
    vlog length) and the file naming makes accidental staleness easy
    to spot. The width is computed from the source's aspect ratio so
    a 16:9 480p source becomes 854x480; ffmpeg's `-2` keeps the math
    even-numbered for libx264 friendliness.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # `fps=1/N` keeps one frame per N seconds. `scale=-2:H` preserves
    # aspect ratio (the -2 forces width to be even). q:v 4 is a
    # quality knob (lower=better, 2-5 is the sweet spot for jpg).
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source_mp4),
            "-vf", f"fps=1/{interval_sec},scale=-2:{height}",
            "-q:v", "4",
            str(out_dir / "frame-%03d.jpg"),
        ],
        check=True,
    )
    return sorted(out_dir.glob("frame-*.jpg"))


def frame_timestamps(frames: list[Path], *, interval_sec: int = DEFAULT_INTERVAL_SEC) -> list[tuple[int, int]]:
    """Return [(frame_idx_1based, approx_sec)] for the sampled frames.

    Each frame N corresponds to source time (N-1) * interval_sec — frame-001
    is at t=0, frame-002 at t=30, etc. This mapping is what Stage 1's
    vision prompt reports to Claude so its `evidence.approx_sec` field
    can stay in source-time even though the agent is reading frames.
    """
    out: list[tuple[int, int]] = []
    for f in frames:
        # Filename pattern: frame-NNN.jpg
        n = int(f.stem.split("-")[-1])
        out.append((n, (n - 1) * interval_sec))
    return out
