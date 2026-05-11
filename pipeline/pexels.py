"""Pexels Videos API client.

Used by producer mode to fetch stock B-roll matching each shot's
visual_brief_en. The API is free (sign up at https://www.pexels.com/api/),
license is "free for commercial + personal use, no attribution required"
(but attribution is appreciated — we can put a credits line in the EDL
description if we want, not now).

Usage:
    set PEXELS_API_KEY in env, then:
        client = PexelsClient.from_env()
        videos = client.search("city skyline at night", min_duration=8)
        path = client.download(videos[0], target_path)

Rate limit: 200 req/hr by default, 20K/mo. Way more than we need.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SEARCH_URL = "https://api.pexels.com/videos/search"


@dataclass(frozen=True)
class PexelsVideo:
    """One candidate from a Pexels search result.

    The `files` list contains the available download URLs at different
    resolutions. We pick the smallest one that's still ≥720p, balancing
    download time against quality.
    """
    id: int
    duration_sec: int
    width: int
    height: int
    files: list[dict]  # each: {link, quality, width, height, file_type}
    page_url: str

    def pick_file(self, max_height: int = 720) -> dict | None:
        """Return the highest-quality .mp4 file whose height ≤ max_height.

        Fall back to the lowest-resolution mp4 if everything is above the
        cap. Returns None if the entry has no usable mp4 (rare).
        """
        mp4s = [f for f in self.files if f.get("file_type") == "video/mp4"]
        if not mp4s:
            return None
        under_cap = [f for f in mp4s if (f.get("height") or 0) <= max_height]
        if under_cap:
            return max(under_cap, key=lambda f: f.get("height") or 0)
        return min(mp4s, key=lambda f: f.get("height") or 0)


class PexelsClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("PEXELS_API_KEY is empty")
        self.api_key = api_key

    @classmethod
    def from_env(cls) -> "PexelsClient":
        key = os.environ.get("PEXELS_API_KEY")
        if not key:
            raise RuntimeError(
                "PEXELS_API_KEY not set. Sign up at "
                "https://www.pexels.com/api/ (free) and add to "
                "~/.config/youtube-clips.env"
            )
        return cls(key)

    def search(
        self,
        query: str,
        *,
        per_page: int = 8,
        min_duration: int = 4,
        orientation: str = "landscape",
    ) -> list[PexelsVideo]:
        """Search Pexels Videos. Returns ranked candidates with duration ≥ min_duration."""
        params = urllib.parse.urlencode({
            "query": query,
            "per_page": per_page,
            "orientation": orientation,
        })
        # Pexels' edge layer rejects the default urllib User-Agent with
        # 403; curl works. Send an explicit UA so we look like a regular
        # client.
        req = urllib.request.Request(
            f"{SEARCH_URL}?{params}",
            headers={
                "Authorization": self.api_key,
                "User-Agent": "youtube-clips/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
        out: list[PexelsVideo] = []
        for v in payload.get("videos", []):
            dur = int(v.get("duration") or 0)
            if dur < min_duration:
                continue
            out.append(PexelsVideo(
                id=v["id"],
                duration_sec=dur,
                width=int(v.get("width") or 0),
                height=int(v.get("height") or 0),
                files=v.get("video_files") or [],
                page_url=v.get("url", ""),
            ))
        return out

    def download(self, video: PexelsVideo, target_path: Path, max_height: int = 720) -> Path:
        """Download the best-matching mp4 of `video` to `target_path`."""
        f = video.pick_file(max_height=max_height)
        if not f:
            raise RuntimeError(f"pexels video {video.id} has no usable mp4")
        link = f["link"]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Add a User-Agent because Pexels CDN occasionally rejects bare requests
        req = urllib.request.Request(link, headers={"User-Agent": "youtube-clips/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r:
            target_path.write_bytes(r.read())
        return target_path


def slugify_query(q: str) -> str:
    """Turn a multi-word query into a filesystem-safe tag for filenames."""
    s = "".join(c if c.isalnum() else "-" for c in q.lower())
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")[:40] or "asset"
