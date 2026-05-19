"""Archival source search + transcript fetch tools.

Used by `asset_strategy="archival"` in producer mode. Agent uses these to
find real footage of subjects / events (e.g., Jensen Huang holding up
Blackwell, OpenAI GPT-5 demo, DeepSeek interview) instead of generating
stock-y or fake AI visuals.

Two-source strategy: B 站 优先（中文 query + 中文 transcript 匹配性能好；
国际官方账号像 NVIDIA英伟达 / Apple 都会上中文翻译版），YouTube 兜底
（英文原始报道、技术 demo、独家访谈）。

The split between *_search and *_transcript lets the agent first sample
metadata cheaply (no transcript fetch), pick the best candidate, then
spend the transcript-fetch round-trip only on the one it wants. Aligns
with the Exp 2 finding that algorithmic PICK is unreliable but agent
two-pass review wins.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from ..bilibili import BilibiliClient, extract_bvid
from ..transcript import parse_vtt
from ..youtube_search import search as yt_search_raw


# Whitelisted official channels — when one of these owns a candidate, we
# mark `is_official=True` so the agent prefers them over搬运 / 二创 / 解说.
# Treated case-insensitive substring match against channel/owner field.
BILI_OFFICIAL_HINTS = [
    "NVIDIA英伟达", "Apple 官方", "Apple官方", "苹果官方",
    "微软", "Microsoft", "Google", "OpenAI",
    "央视", "CCTV", "新华社", "人民日报",
    "TED", "DeepSeek", "智谱", "百度", "阿里",
    "字节跳动", "腾讯",
]
YT_OFFICIAL_HINTS = [
    "NVIDIA", "Apple", "Microsoft", "Google", "Google DeepMind",
    "OpenAI", "Anthropic", "Meta", "DeepMind", "TED",
    "CNBC", "Bloomberg", "Reuters", "Associated Press", "CGTN",
    "Stanford", "MIT", "Caltech", "Carnegie Mellon",
]


def _is_official_bili(owner: str | None) -> bool:
    if not owner:
        return False
    o = owner.strip()
    return any(h.lower() in o.lower() for h in BILI_OFFICIAL_HINTS)


def _is_official_yt(channel: str | None) -> bool:
    if not channel:
        return False
    c = channel.strip()
    return any(h.lower() in c.lower() for h in YT_OFFICIAL_HINTS)


def search_youtube_archival(
    query: str,
    max_results: int = 10,
    relevance_language: str = "en",
    min_duration_sec: int = 60,
    min_views: int = 1_000,
) -> dict:
    """Search YouTube for archival source video candidates.

    Returns metadata-only candidates (no transcript fetch yet — that's
    `read_youtube_transcript`). Agent picks a candidate based on title /
    channel / view_count / duration / is_official, then fetches the
    transcript or jumps straight to localize_in_video.

    Args:
        query: English search query. Be specific — "Jensen Huang GTC 2024
               Blackwell keynote" gets you the right source faster than
               just "Jensen Huang".
        max_results: 5-30 candidates (default 10).
        relevance_language: "en" / "zh" / "any".
        min_duration_sec: Skip shorts (<60s) by default.
        min_views: Filter low-quality reuploads.

    Returns:
        dict with `query` echoed and `results` list of:
            {video_id, url, title, channel, duration_sec, view_count,
             has_captions, is_official, published_at}
        sorted by view_count desc.
    """
    try:
        raw = yt_search_raw(
            query, max_results=max_results, video_duration="any",
            relevance_language=relevance_language,
        )
    except Exception as e:
        return {"query": query, "error": f"search failed: {e}", "results": []}

    out = []
    for c in raw:
        if c.duration_sec < min_duration_sec:
            continue
        if c.view_count < min_views:
            continue
        out.append({
            "video_id": c.id,
            "url": c.url,
            "title": c.title,
            "channel": c.channel,
            "duration_sec": c.duration_sec,
            "view_count": c.view_count,
            "has_captions": c.has_captions,
            "is_official": _is_official_yt(c.channel),
            "published_at": c.published_at,
        })
    out.sort(key=lambda x: x["view_count"], reverse=True)
    return {"query": query, "results": out}


def search_bilibili_archival(
    query: str,
    max_results: int = 10,
    duration_band: str = "",
    min_duration_sec: int = 60,
    min_views: int = 5_000,
) -> dict:
    """Search Bilibili for archival source video candidates.

    Returns metadata-only. Per Exp 2: B 站 has Chinese-translated official
    versions of GTC/keynote that YouTube doesn't, plus dense AI-generated
    transcripts on most videos.

    Args:
        query: Chinese keyword string (5-15 chars best). Examples:
               "黄仁勋 GTC 主题演讲", "DeepSeek V3 发布", "Sam Altman 国会作证"
        max_results: 5-30 (default 10).
        duration_band: "" (any) / "1" (<5min) / "2" (5-10) / "3" (10-30) / "4" (>30).
        min_duration_sec: Skip very short (default 60s).
        min_views: Filter junk (default 5000).

    Returns:
        dict with `query` and `results`:
            {bvid, url, title, owner, duration_sec, view_count, is_official,
             pub_date, desc}
        sorted by view_count desc.
    """
    try:
        client = BilibiliClient()
        items = client.search(
            query, max_results=max_results,
            duration_band=duration_band or None, order="click",
        )
    except Exception as e:
        return {"query": query, "error": f"search failed: {e}", "results": []}

    out = []
    for it in items:
        bvid = it.get("bvid")
        if not bvid:
            continue
        dur = _dur_to_sec(it.get("duration"))
        if dur < min_duration_sec:
            continue
        view_count = int(it.get("play") or 0)
        if view_count < min_views:
            continue
        out.append({
            "bvid": bvid,
            "url": f"https://www.bilibili.com/video/{bvid}",
            "title": it.get("title"),
            "owner": it.get("author"),
            "duration_sec": dur,
            "view_count": view_count,
            "is_official": _is_official_bili(it.get("author")),
            "pub_date": _pub_to_iso(it.get("pubdate")),
            "desc": (it.get("description") or "")[:200],
        })
    out.sort(key=lambda x: x["view_count"], reverse=True)
    return {"query": query, "results": out}


def read_bilibili_transcript(bvid: str) -> dict:
    """Fetch the AI-generated timestamped transcript of a Bilibili video.

    Use after `search_bilibili_archival` returns a promising candidate
    to verify content + look for keywords matching a target moment. The
    transcript is the cheapest path to localization — see
    `localize_in_video` for the full Tier-A flow.

    Args:
        bvid: BV id like "BV1xxxxxxxxx" or full URL.

    Returns:
        dict with `bvid` / `title` / `duration_sec` / `transcript_lines`
        list of {start, end, text}. Empty / error → returns {} with `error`.
    """
    try:
        bvid_clean = extract_bvid(bvid)
        client = BilibiliClient()
        info = client.video_info(bvid_clean)
    except Exception as e:
        return {"bvid": bvid, "error": f"metadata fetch failed: {e}"}
    try:
        lines = client.transcript(info)
    except Exception as e:
        return {
            "bvid": info.bvid, "title": info.title,
            "duration_sec": info.duration,
            "transcript_lines": [], "error": f"transcript fetch failed: {e}",
        }
    return {
        "bvid": info.bvid,
        "title": info.title,
        "owner": info.owner,
        "duration_sec": info.duration,
        "transcript_lines": [
            {"start": s.start, "end": s.end, "text": s.text} for s in lines
        ],
    }


def read_youtube_transcript(video_id: str, language: str = "en") -> dict:
    """Fetch YouTube auto-captions as timestamped transcript.

    Uses yt-dlp + the project's existing cookies file. Returns a normalized
    structure matching `read_bilibili_transcript` so agents / pipeline can
    treat both sources uniformly.

    Args:
        video_id: YouTube video id (11-char).
        language: caption language code (default "en"; "zh-CN" / "zh-Hans" too).

    Returns:
        dict with `video_id` / `language` / `transcript_lines` (list of
        {start, end, text}). Error case includes `error` and empty lines.
    """
    YTDLP = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "yt-dlp"
    COOKIES = Path.home() / ".config" / "youtube-clips-cookies.txt"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        cmd = [
            str(YTDLP),
            "--skip-download",
            "--write-auto-subs",
            "--sub-lang", language,
            "--sub-format", "vtt",
            "-o", str(td_path / "%(id)s.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        if COOKIES.exists():
            cmd.extend(["--cookies", str(COOKIES)])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return {
                "video_id": video_id, "language": language,
                "transcript_lines": [],
                "error": "yt-dlp timed out (60s)",
            }
        if proc.returncode != 0:
            return {
                "video_id": video_id, "language": language,
                "transcript_lines": [],
                "error": f"yt-dlp exit {proc.returncode}: {proc.stderr[:200]}",
            }
        vtts = sorted(td_path.glob("*.vtt"))
        if not vtts:
            return {
                "video_id": video_id, "language": language,
                "transcript_lines": [],
                "error": "no caption file produced (video may not have captions in this language)",
            }
        # parse_vtt returns list[(start_sec, text)]; normalize to dict shape
        # to match the Bilibili tool.
        entries = parse_vtt(vtts[0])
        return {
            "video_id": video_id,
            "language": language,
            "transcript_lines": [
                {"start": s, "end": s, "text": t} for s, t in entries
            ],
        }


# Internal helpers ---------------------------------------------------------


def _dur_to_sec(d) -> int:
    """Normalize Bilibili duration: int seconds, or 'MM:SS' / 'HH:MM:SS' str."""
    if d is None:
        return 0
    if isinstance(d, (int, float)):
        return int(d)
    parts = str(d).split(":")
    try:
        if len(parts) == 1:
            return int(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def _pub_to_iso(ts) -> str | None:
    import datetime as dt
    if not ts:
        return None
    try:
        return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None
