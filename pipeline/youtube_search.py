"""YouTube Data API v3 wrapper.

Two endpoints are involved per discovery call:
  - search.list  → 100 quota units, returns ~25 video IDs
  - videos.list  → 1 unit per call (up to 50 IDs/batch), enriches with
                   duration / view count / caption flag

Reads `YT_API_KEY` from the environment.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable

import requests

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


@dataclass(frozen=True)
class VideoCandidate:
    id: str
    title: str
    channel: str
    description: str
    published_at: str
    duration_sec: int
    view_count: int
    has_captions: bool

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["url"] = self.url
        return d


def _parse_iso8601_duration(s: str) -> int:
    m = _DUR_RE.match(s or "")
    if not m:
        return 0
    h, mn, sec = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mn * 60 + sec


def _api_key() -> str:
    key = os.environ.get("YT_API_KEY")
    if not key:
        raise RuntimeError("YT_API_KEY not set in env")
    return key


def search(
    query: str,
    *,
    max_results: int = 25,
    published_after: str | None = None,
    video_duration: str = "medium",  # short | medium | long | any
    relevance_language: str = "en",
    order: str = "relevance",  # relevance | date | viewCount | rating
) -> list[VideoCandidate]:
    """Single-page search + immediate enrichment with videos.list."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "videoDuration": video_duration,
        "order": order,
        "relevanceLanguage": relevance_language,
        "maxResults": max_results,
        "key": _api_key(),
    }
    if published_after:
        params["publishedAfter"] = published_after
    r = requests.get(SEARCH_URL, params=params, timeout=15)
    r.raise_for_status()
    items = r.json().get("items", [])
    ids = [it["id"]["videoId"] for it in items if "videoId" in it.get("id", {})]
    if not ids:
        return []
    return enrich(ids)


def enrich(ids: Iterable[str]) -> list[VideoCandidate]:
    """videos.list call to pick up duration / views / caption-flag."""
    ids = list(ids)
    if not ids:
        return []
    r = requests.get(
        VIDEOS_URL,
        params={
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(ids),
            "key": _api_key(),
        },
        timeout=15,
    )
    r.raise_for_status()
    out: list[VideoCandidate] = []
    for v in r.json().get("items", []):
        sn = v.get("snippet", {})
        cd = v.get("contentDetails", {})
        st = v.get("statistics", {})
        out.append(
            VideoCandidate(
                id=v["id"],
                title=sn.get("title", ""),
                channel=sn.get("channelTitle", ""),
                description=sn.get("description", ""),
                published_at=sn.get("publishedAt", ""),
                duration_sec=_parse_iso8601_duration(cd.get("duration", "")),
                view_count=int(st.get("viewCount", 0)),
                has_captions=str(cd.get("caption", "")).lower() == "true",
            )
        )
    return out
