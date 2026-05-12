"""Bilibili tool surface — search + read transcript."""

from __future__ import annotations

import datetime as dt

from ..bilibili import BilibiliClient, extract_bvid


def search_bilibili(
    query: str,
    max_results: int = 10,
    duration_band: str = "3",
) -> dict:
    """Search Bilibili for videos matching a Chinese keyword query.

    Returns the top results sorted by view count. Use this to find
    same-topic videos for style reference, current discourse, or factual
    grounding.

    Args:
        query: Chinese keyword combination (5-15 chars works best;
               narrative video titles often return 0 results — extract
               domain keywords like 「县城便利店」instead).
        max_results: 1-30 results to return (default 10).
        duration_band: Bilibili duration filter:
            "1" = <5min, "2" = 5-10min, "3" = 10-30min (default),
            "4" = >30min, "" = any.

    Returns:
        dict with `query` (echoed), `results` (list of items each with
        bvid / title / owner / view_count / duration / pub_date / desc).
    """
    try:
        client = BilibiliClient()
        items = client.search(
            query, max_results=max_results,
            duration_band=duration_band or None, order="click",
        )
    except Exception as e:
        return {"query": query, "error": f"search failed: {e}", "results": []}

    results = []
    for it in items:
        pub = it.get("pubdate")
        pub_str = (
            dt.datetime.fromtimestamp(int(pub), tz=dt.timezone.utc).date().isoformat()
            if pub else None
        )
        desc = (it.get("description") or "").strip()
        if len(desc) > 200:
            desc = desc[:197] + "…"
        results.append({
            "bvid": it.get("bvid"),
            "title": it.get("title"),
            "owner": it.get("author"),
            "view_count": int(it.get("play") or 0),
            "duration": it.get("duration"),
            "pub_date": pub_str,
            "desc": desc,
        })
    return {"query": query, "results": results}


def read_bilibili_video(bvid: str, include_transcript: bool = True) -> dict:
    """Read a Bilibili video's metadata and AI-generated transcript.

    Use to study how a same-topic viral video structured its narrative —
    opening hook, mid-section pacing, closing takeaway. The transcript
    is Bilibili's auto-generated subtitle; quality varies but generally
    captures the spoken script accurately.

    Args:
        bvid: A Bilibili BV id like "BV1xxxxxxxxx". URLs accepted too.
        include_transcript: If False, only return metadata (fast). Default True.

    Returns:
        dict with bvid / title / owner / desc / duration_sec / view_count /
        like_count / reply_count / pub_date / transcript_text /
        transcript_lines (list of {start, end, text}).
    """
    try:
        bvid_clean = extract_bvid(bvid)
        client = BilibiliClient()
        info = client.video_info(bvid_clean)
    except Exception as e:
        return {"bvid": bvid, "error": f"metadata fetch failed: {e}"}

    out: dict = {
        "bvid": info.bvid,
        "url": info.url,
        "title": info.title,
        "owner": info.owner,
        "desc": info.desc,
        "duration_sec": info.duration,
        "view_count": int(info.stat.get("view") or 0),
        "like_count": int(info.stat.get("like") or 0),
        "reply_count": int(info.stat.get("reply") or 0),
        "pub_date": (
            dt.datetime.fromtimestamp(info.pubdate, tz=dt.timezone.utc).date().isoformat()
            if info.pubdate else None
        ),
    }
    if include_transcript:
        try:
            lines = client.transcript(info)
            out["transcript_lines"] = [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in lines
            ]
            out["transcript_text"] = "\n".join(s.text for s in lines)
        except Exception as e:
            out["transcript_error"] = f"transcript fetch failed: {e}"
    return out
