"""Chinese hot-topic feed adapters.

Wraps the locally-deployed rsshub instance (ai-feed-rsshub-1, exposed at
127.0.0.1:3007). Each feed is identified by a short id used in Profile
configs; the registry below maps id → URL + descriptive metadata.

Scalability point: adding a feed is one entry in FEED_REGISTRY; profiles
opt in via `Profile.config.topic_discovery.feed_ids`. To swap rsshub for
a different aggregator, edit RSSHUB_BASE in one place.

Some rsshub routes (weibo/hot, baidu/realtime, tophub aggregators) need
Playwright Chromium inside the rsshub container. The shared rsshub
deployment doesn't have it installed; affected feeds are flagged
`requires_browser=True` and skipped at fetch time with a warning until
chromium is added (one-off `docker exec ai-feed-rsshub-1 npx playwright
install chromium`).
"""

from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

RSSHUB_BASE = "http://127.0.0.1:3007"
USER_AGENT = "youtube-clips/0.1 (+https://github.com/WhatsFish/youtube-clips)"

# RSS namespace handling: rsshub's output uses standard RSS 2.0; we treat
# nodes as namespace-free for ElementTree convenience.


@dataclass
class FeedSpec:
    feed_id: str
    url: str
    label: str
    description: str
    language: str = "zh"
    requires_browser: bool = False
    topic_areas: list[str] = field(default_factory=list)


FEED_REGISTRY: dict[str, FeedSpec] = {
    "zhihu_hot": FeedSpec(
        feed_id="zhihu_hot",
        url=f"{RSSHUB_BASE}/zhihu/hot",
        label="知乎热榜",
        description="知乎当前热门讨论 — 偏深度社会议题、解释性话题",
        topic_areas=["social", "explainer", "tech", "policy"],
    ),
    "thepaper_featured": FeedSpec(
        feed_id="thepaper_featured",
        url=f"{RSSHUB_BASE}/thepaper/featured",
        label="澎湃 featured",
        description="澎湃新闻精选 — 严肃媒体视角，社会与时政深度",
        topic_areas=["social", "policy", "news"],
    ),
    "36kr_latest": FeedSpec(
        feed_id="36kr_latest",
        url=f"{RSSHUB_BASE}/36kr/news/latest",
        label="36氪",
        description="36氪科技商业新闻 — 创投、新经济、产业链动态",
        topic_areas=["tech", "business", "economy"],
    ),
    "weibo_hot": FeedSpec(
        feed_id="weibo_hot",
        url=f"{RSSHUB_BASE}/weibo/search/hot",
        label="微博热搜",
        description="微博热搜榜 — 实时大众舆论流向；娱乐与社会议题混合",
        topic_areas=["social", "entertainment", "news"],
        requires_browser=True,  # rsshub route needs Playwright
    ),
}


@dataclass
class FeedItem:
    feed_id: str
    feed_label: str
    title: str
    description: str   # plain text, may be empty
    link: str          # source URL (may be paywall / not always usable)
    published: str | None  # ISO-8601 string from RSS pubDate, or None

    def as_dict(self) -> dict[str, Any]:
        return {
            "feed_id": self.feed_id,
            "feed_label": self.feed_label,
            "title": self.title,
            "description": self.description,
            "link": self.link,
            "published": self.published,
        }


def _strip_cdata(s: str | None) -> str:
    if not s:
        return ""
    return s.strip()


def fetch_feed(feed_id: str, *, timeout: int = 15) -> list[FeedItem]:
    """Fetch a single feed and return its items. Raises on HTTP / parse error."""
    spec = FEED_REGISTRY.get(feed_id)
    if spec is None:
        raise ValueError(f"unknown feed_id: {feed_id!r}")
    if spec.requires_browser:
        # Caller should branch before this; we still raise so we don't
        # silently lie about the data we have.
        raise RuntimeError(
            f"feed {feed_id!r} requires Playwright chromium in the rsshub "
            f"container; install with `docker exec ai-feed-rsshub-1 npx "
            f"playwright install chromium` then retry"
        )
    req = urllib.request.Request(spec.url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    root = ET.fromstring(body)
    # rsshub emits RSS 2.0 — items live at /rss/channel/item
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[FeedItem] = []
    for it in channel.findall("item"):
        items.append(
            FeedItem(
                feed_id=spec.feed_id,
                feed_label=spec.label,
                title=_strip_cdata(it.findtext("title")),
                description=_strip_cdata(it.findtext("description")),
                link=_strip_cdata(it.findtext("link")),
                published=_strip_cdata(it.findtext("pubDate")) or None,
            )
        )
    return items


def fetch_feeds(feed_ids: list[str]) -> tuple[list[FeedItem], list[str]]:
    """Fetch every feed in the list; return (items, skipped_with_reason).

    Best-effort: one feed failing doesn't kill the rest. The caller logs
    `skipped` so the operator knows which sources weren't included.
    """
    items: list[FeedItem] = []
    skipped: list[str] = []
    for fid in feed_ids:
        spec = FEED_REGISTRY.get(fid)
        if spec is None:
            skipped.append(f"{fid}: unknown feed_id")
            continue
        if spec.requires_browser:
            skipped.append(
                f"{fid} ({spec.label}): requires_browser; install chromium "
                f"in rsshub container to enable"
            )
            continue
        try:
            items.extend(fetch_feed(fid))
        except Exception as e:
            skipped.append(f"{fid} ({spec.label}): {type(e).__name__}: {e}")
    return items, skipped


def apply_keyword_filter(
    items: list[FeedItem],
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[FeedItem]:
    """Cheap pre-filter before the (expensive) Claude judge call.

    - exclude: any match against title+description drops the item
      (used to kill the entertainment-tier noise that 微博/百度 dump in)
    - include: if non-empty, at least one keyword must appear in
      title+description; if empty, every item that survived exclude passes
    """
    out: list[FeedItem] = []
    inc = [w.lower() for w in (include or []) if w]
    exc = [w.lower() for w in (exclude or []) if w]
    for it in items:
        hay = (it.title + " " + it.description).lower()
        if any(w in hay for w in exc):
            continue
        if inc and not any(w in hay for w in inc):
            continue
        out.append(it)
    return out


def fetch_youtube_topic_candidates(
    queries: list[str],
    *,
    max_per_query: int = 5,
    published_within_weeks: int = 4,
) -> tuple[list[FeedItem], list[str]]:
    """Use YouTube Search to surface vlog candidates as `FeedItem`s.

    For channels whose topic ground-truth lives on YouTube (world-watching-cn
    needs English daily-life vlogs from diverse countries), not RSS. Each
    query (e.g. "Vietnam day in the life vlog") returns the top
    `max_per_query` mid-length results; deduped across queries.

    Output shape matches `fetch_feeds()` so the rest of discover-topics
    treats both backends identically.
    """
    import datetime as _dt
    from .youtube_search import search

    cutoff = (
        _dt.datetime.now(_dt.timezone.utc)
        - _dt.timedelta(weeks=published_within_weeks)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")

    items: list[FeedItem] = []
    skipped: list[str] = []
    seen_ids: set[str] = set()
    for q in queries:
        try:
            hits = search(
                q, max_results=max_per_query,
                published_after=cutoff, video_duration="medium",
                order="viewCount",
            )
        except Exception as e:
            skipped.append(f"youtube_search {q!r}: {type(e).__name__}: {e}")
            continue
        for h in hits:
            if h.id in seen_ids:
                continue
            seen_ids.add(h.id)
            desc = (h.description or "").strip()
            items.append(
                FeedItem(
                    feed_id=f"youtube:{q}",
                    feed_label=f"YouTube «{q}»",
                    title=h.title,
                    description=desc,
                    link=h.url,
                    published=h.published_at,
                )
            )
    return items, skipped


def render_registry_block() -> str:
    """Render the feed registry as a human-readable description block —
    useful for embedding in agent prompts so the Claude judge knows
    where each candidate came from."""
    lines = []
    for spec in FEED_REGISTRY.values():
        marker = " (requires_browser)" if spec.requires_browser else ""
        lines.append(f"- {spec.feed_id}: {spec.label}{marker} — {spec.description}")
    return "\n".join(lines)
