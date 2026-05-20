"""Render an agent-written HTML doc → mp4 via headless Chromium.

Architecture: every shot's HTML is written from scratch by the agent
(no template registry). The renderer just provides infrastructure:
  - copies shared design tokens (_styles.css) + fonts next to the HTML
  - opens it in headless Chromium at 1280x720
  - waits 300ms preroll, then calls window.startAnimation()
  - screenshots one frame per (1/FPS) seconds for `duration_sec`
  - ffmpeg encodes to 30fps yuv420p H.264 mp4

The agent must follow DESIGN.md (templates/html/DESIGN.md) — link to
_styles.css, expose window.startAnimation(), respect palette + pacing.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "pipeline" / "templates" / "html"

W, H = 1280, 720
FPS = 30
PREROLL_SEC = 0.3
MAX_DURATION_SEC = 20.0


def render_html_clip(
    html: str,
    out_mp4: Path,
    duration_sec: float,
    *,
    work_dir: Path | None = None,
) -> Path:
    """Render `html` string → mp4 at out_mp4.

    Args:
        html: full HTML document. MUST link to _styles.css and expose
              window.startAnimation. Validated only loosely (substring
              checks) — bad HTML produces a dark frame, not a crash.
        out_mp4: where to write the final mp4.
        duration_sec: how long the clip should be. Clamped to [1, 20]s.
        work_dir: tmp directory; one is created if not given.

    Returns the mp4 Path.
    """
    duration_sec = max(1.0, min(MAX_DURATION_SEC, float(duration_sec)))
    if "_styles.css" not in html:
        raise ValueError("agent HTML must <link rel=\"stylesheet\" href=\"_styles.css\">")
    if "startAnimation" not in html:
        raise ValueError("agent HTML must expose window.startAnimation()")

    if work_dir is None:
        work_ctx = tempfile.TemporaryDirectory(prefix="html-clip-")
        work_dir = Path(work_ctx.name)
    else:
        work_dir.mkdir(parents=True, exist_ok=True)
        work_ctx = None

    try:
        # Stage HTML + share assets so file:// resolves relative paths.
        html_path = work_dir / "shot.html"
        html_path.write_text(html, encoding="utf-8")
        for f in ("_styles.css", "NotoSansSC-Regular.otf", "NotoSansSC-Bold.otf"):
            shutil.copy(TEMPLATE_DIR / f, work_dir / f)

        frames_dir = work_dir / "frames"
        frames_dir.mkdir(exist_ok=True)
        _capture_frames(html_path, frames_dir, duration_sec)
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        _encode_mp4(frames_dir, out_mp4)
        return out_mp4
    finally:
        if work_ctx is not None:
            work_ctx.cleanup()


def _capture_frames(html_path: Path, frames_dir: Path, duration_sec: float) -> None:
    total = int(FPS * duration_sec)
    preroll = int(FPS * PREROLL_SEC)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": W, "height": H})
            page.set_default_timeout(30_000)
            page.goto(f"file://{html_path.resolve()}")
            page.wait_for_load_state("networkidle")
            time.sleep(0.25)
            for i in range(preroll):
                page.screenshot(path=str(frames_dir / f"f{i:04d}.png"))
            page.evaluate("window.startAnimation && window.startAnimation()")
            for j in range(total - preroll):
                idx = preroll + j
                page.screenshot(path=str(frames_dir / f"f{idx:04d}.png"))
        finally:
            browser.close()


def _encode_mp4(frames_dir: Path, out_mp4: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "f%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", f"fps={FPS},scale={W}:{H}:flags=lanczos",
        "-crf", "20",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)
