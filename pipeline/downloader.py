"""yt-dlp wrapper.

Centralized so every script downloads with the same flags — cookies,
EJS remote-components for the JS challenge, format spec, and the two
sub-language tags YouTube auto-captions actually appear under (`en`
and `en-US`).

Idempotent: if `source.mp4` already exists for the requested video_id,
this is a no-op (the user can pass `force=True` to re-download).

Captures the well-known cloud-VM failure mode: when YouTube's anti-bot
rejects the cookies, yt-dlp surfaces "Sign in to confirm you're not a
bot" — we re-raise it as `BotWallError` so callers can handle it
distinctly from a generic transient failure.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
YT_DLP = str(PROJECT_ROOT / ".venv" / "bin" / "yt-dlp")
COOKIES_FILE = Path.home() / ".config" / "youtube-clips-cookies.txt"
RAW_BASE = Path("/video/youtube-clips/raw")

_BOT_WALL_RE = re.compile(r"sign in to confirm you'?re not a bot", re.IGNORECASE)


class BotWallError(RuntimeError):
    """yt-dlp got the YouTube anti-bot wall; cookies need refreshing.

    On this VM (Azure datacenter IP), this can happen within hours of
    a cookie refresh — the underlying issue is IP reputation, not cookie
    expiry. Caller should bubble a clear "refresh cookies" message up
    to the operator.
    """


class CookiesMissingError(RuntimeError):
    """`~/.config/youtube-clips-cookies.txt` is missing entirely."""


@dataclass(frozen=True)
class DownloadResult:
    video_id: str
    video_path: Path
    vtt_path: Path | None  # None if no English captions could be fetched


def _vtt_for(video_id: str) -> Path | None:
    """yt-dlp picks one of these names depending on which sub track exists."""
    raw_dir = RAW_BASE / video_id
    for name in ("source.en.vtt", "source.en-US.vtt"):
        p = raw_dir / name
        if p.exists():
            return p
    return None


def download(
    video_id: str,
    *,
    force: bool = False,
    max_height: int = 720,
) -> DownloadResult:
    """Download `video_id` (video + English captions) to RAW_BASE.

    Returns paths even on a cache hit.
    """
    raw_dir = RAW_BASE / video_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_video = raw_dir / "source.mp4"

    if out_video.exists() and not force:
        return DownloadResult(
            video_id=video_id,
            video_path=out_video,
            vtt_path=_vtt_for(video_id),
        )

    if not COOKIES_FILE.exists():
        raise CookiesMissingError(
            f"cookies file missing at {COOKIES_FILE}. Export from a logged-in "
            f"browser (cookies.txt extension) and copy it there with mode 600."
        )

    proc = subprocess.run(
        [
            YT_DLP,
            "--cookies", str(COOKIES_FILE),
            "--remote-components", "ejs:github",
            "-f",
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/best[height<={max_height}][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "en,en-US",
            "--sub-format", "vtt",
            "-o", str(raw_dir / "source.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        combined = (proc.stderr or "") + (proc.stdout or "")
        if _BOT_WALL_RE.search(combined):
            raise BotWallError(
                "YouTube anti-bot rejected cookies. Re-export from a logged-in "
                "browser (the IP-reputation issue means this can recur within "
                "hours on this VM)."
            )
        raise RuntimeError(
            f"yt-dlp exited {proc.returncode}\n"
            f"stderr: {proc.stderr.strip()[:500]}"
        )

    return DownloadResult(
        video_id=video_id,
        video_path=out_video,
        vtt_path=_vtt_for(video_id),
    )
