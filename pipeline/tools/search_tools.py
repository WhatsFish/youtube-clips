"""Web search tool — DuckDuckGo, no API key needed."""

from __future__ import annotations


def web_search(query: str, max_results: int = 8, region: str = "wt-wt") -> dict:
    """General-purpose web search via DuckDuckGo. Returns titles + URLs +
    short snippets ranked by relevance.

    Use to find any article / news / Wikipedia page / blog post on a
    topic. After finding a promising URL, call `fetch_url(url)` to read
    the full content.

    Args:
        query: Search query. Plain text, any language.
        max_results: 1-20 results (default 8).
        region: DuckDuckGo region code (default "wt-wt" = worldwide).
                Use "cn-zh" for Chinese-region bias, "us-en" for US-English bias.

    Returns:
        dict with `query` (echoed) and `results` (list of {title, url, snippet}).
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return {
            "query": query,
            "error": "ddgs package not installed; pip install ddgs",
            "results": [],
        }
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, region=region, max_results=max_results))
    except Exception as e:
        return {"query": query, "error": f"search failed: {e}", "results": []}

    results = []
    for r in raw:
        # DDGS returns mostly {title, href, body} shape
        snippet = (r.get("body") or "").strip()
        if len(snippet) > 240:
            snippet = snippet[:237] + "…"
        results.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("href") or "").strip(),
            "snippet": snippet,
        })
    return {"query": query, "results": results}
