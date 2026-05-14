"""Person image search — DuckDuckGo images.

Use case: when a shot's `visual_brief` involves a specific real-world
named person (Kevin Warsh, Powell, 习近平, 马斯克, ...), Pexels / CogView
can't produce the right face — Pexels returns random stock, CogView
text-to-image hallucinates wrong faces (and may be policy-blocked on
politicians). Real photos from search are the only honest path.
"""

from __future__ import annotations


def search_person_image(name: str, max_results: int = 5) -> dict:
    """Search for real photos of a named person via DuckDuckGo Images.

    Use this **only when the shot needs to show a specific real-world
    person** (Kevin Warsh, Jerome Powell, Elon Musk, 习近平, etc.). Pexels
    and CogView are not allowed substitutes for named individuals — they
    will produce wrong-looking visuals that confuse viewers and damage
    factual credibility.

    Args:
        name: The person's full name. English works best for international
              public figures; Chinese for Chinese figures.
        max_results: 1-10 result count (default 5).

    Returns:
        dict with `name`, `count`, and `results` (each: {title, image_url,
        thumbnail_url, source_url, width, height}). Empty results indicates
        no good match found; caller should fall back gracefully.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return {"name": name, "error": "ddgs not installed", "results": []}
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.images(name, max_results=max_results))
    except Exception as e:
        return {"name": name, "error": f"search failed: {e}", "results": []}

    results = []
    for r in raw:
        results.append({
            "title": (r.get("title") or "").strip(),
            "image_url": (r.get("image") or "").strip(),
            "thumbnail_url": (r.get("thumbnail") or "").strip(),
            "source_url": (r.get("url") or "").strip(),
            "width": r.get("width"),
            "height": r.get("height"),
        })
    return {"name": name, "count": len(results), "results": results}
