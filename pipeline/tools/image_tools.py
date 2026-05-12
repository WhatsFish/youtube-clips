"""Visual verification tools — let the agent see images inline.

Both tools return an MCP `Image` content block. The Claude CLI's MCP
client surfaces this in the conversation so the agent can reason about
what's actually in the image, not just the URL string.

Use cases:
  - source-pick / edl-commentary: see what a YouTube candidate actually
    looks like before committing to it
  - producer / commentary: verify an image source surfaced via
    web_search / preview_pexels really shows the intended content
  - world-watching: peek at a thumbnail to confirm a vlog is genuine
    daily-life vs reaction / compilation
"""

from __future__ import annotations

import urllib.request
import urllib.parse

from mcp.server.fastmcp import Image

UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
)


def _fetch_image_bytes(url: str, max_bytes: int = 5 * 1024 * 1024) -> tuple[bytes, str]:
    """Fetch up to max_bytes of an image. Returns (bytes, format).

    `format` is inferred from Content-Type then file extension; defaults
    to 'png' when unknown.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "image/*",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        body = resp.read(max_bytes)
    if "jpeg" in ctype or "jpg" in ctype:
        fmt = "jpeg"
    elif "png" in ctype:
        fmt = "png"
    elif "webp" in ctype:
        fmt = "webp"
    elif "gif" in ctype:
        fmt = "gif"
    else:
        # Fallback by extension
        path = urllib.parse.urlparse(url).path.lower()
        if path.endswith((".jpg", ".jpeg")):
            fmt = "jpeg"
        elif path.endswith(".webp"):
            fmt = "webp"
        elif path.endswith(".gif"):
            fmt = "gif"
        else:
            fmt = "png"
    return body, fmt


def read_image(url: str) -> Image | dict:
    """Fetch a public image URL and return it as an inline image the agent
    can see and reason about.

    Use after `web_search` / `preview_pexels` / `search_bilibili` returns
    a URL/thumbnail that you want to actually look at before deciding.
    Image is loaded into the conversation as a real Image, not just an
    URL string.

    Args:
        url: http(s) URL pointing at a JPEG / PNG / WebP / GIF. Capped at 5 MB.

    Returns:
        An MCP Image (success), or a dict {"error": ...} (failure).
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"error": "only http(s) URLs allowed"}
    try:
        data, fmt = _fetch_image_bytes(url)
    except Exception as e:
        return {"error": f"fetch failed: {e}"}
    return Image(data=data, format=fmt)


def read_youtube_thumbnail(video_id: str) -> Image | dict:
    """Fetch a YouTube video's thumbnail (maxresdefault, falling back to
    hqdefault) and return it as an inline image. No video download needed.

    Use during source picking / commentary planning to actually see what
    a candidate video looks like — title + description alone misses
    visual cues like "this is a compilation", "this is a face-cam
    reaction", "this is a thumbnail with red arrows".

    Args:
        video_id: An 11-character YouTube video id (e.g. "dQw4w9WgXcQ").

    Returns:
        An MCP Image (success), or a dict {"error": ...} (failure).
    """
    vid = (video_id or "").strip()
    if len(vid) != 11:
        return {"error": f"video_id should be 11 chars, got {len(vid)}"}
    # Try max-res first; falls back to hqdefault if the video has no
    # max-res thumbnail (rare for modern uploads).
    for tier in ("maxresdefault", "hqdefault", "default"):
        url = f"https://i.ytimg.com/vi/{vid}/{tier}.jpg"
        try:
            data, _ = _fetch_image_bytes(url)
        except Exception:
            continue
        return Image(data=data, format="jpeg")
    return {"error": f"no thumbnail tier resolved for {vid}"}
