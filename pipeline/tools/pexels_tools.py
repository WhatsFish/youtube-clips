"""Pexels preview tool — let the script agent verify stock availability
*before* writing visual_brief_en, so producer-mode shots don't end up
with no-match Pexels searches that fall through to AI generation.
"""

from __future__ import annotations

from ..pexels import PexelsClient


def preview_pexels(
    query: str,
    max_results: int = 5,
    min_duration_sec: int = 4,
) -> dict:
    """Search Pexels (free stock video) for a query and return what's
    actually available. Use BEFORE committing to a visual_brief_en in
    your shot — if Pexels has no good match, switch to `asset_strategy=ai`.

    Args:
        query: English search query, 3-8 words (e.g. "delivery rider city
               night neon"). Short and visual.
        max_results: 1-15 candidates to return (default 5).
        min_duration_sec: Skip clips shorter than this (default 4s).

    Returns:
        dict with `query`, `count`, and `results` (each: {id, duration_sec,
        width x height, page_url, preview_image, file_pick_height}).

        If `count == 0` or results look unrelated to the query, the
        script should emit `asset_strategy=ai` for this shot instead of
        relying on Pexels.
    """
    try:
        client = PexelsClient.from_env()
    except Exception as e:
        return {"query": query, "error": f"client init failed: {e}", "results": []}
    try:
        videos = client.search(query, per_page=max(max_results * 2, 8),
                               min_duration=min_duration_sec)
    except Exception as e:
        return {"query": query, "error": f"search failed: {e}", "results": []}

    results = []
    for v in videos[:max_results]:
        pick = v.pick_file()
        # The Pexels API also returns a `image` field at the video level
        # (a JPEG preview frame); we don't have it parsed yet, so just
        # surface dimensions + duration + page URL — enough for the agent
        # to judge match quality from page metadata.
        results.append({
            "id": v.id,
            "duration_sec": v.duration_sec,
            "width": v.width,
            "height": v.height,
            "page_url": v.page_url,
            "file_pick_height": pick.get("height") if pick else None,
        })
    return {"query": query, "count": len(results), "results": results}
