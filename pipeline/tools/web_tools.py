"""Web tools — fetch URL plain text + read RSS feed items.

Deliberately minimal: no headless browser, no JS execution. Targets
news-article style pages (澎湃 / 36氪 / 知乎专栏 / 新浪) where the
content lives in static HTML. For sites that require JS-rendered
content, agent gets an empty extraction and can move on.
"""

from __future__ import annotations

import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser

UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
)


class _TextExtractor(HTMLParser):
    """Strip HTML to plain text. Keeps content inside common article
    containers; drops script/style/nav noise."""

    SKIP_TAGS = {"script", "style", "noscript", "iframe", "svg",
                 "header", "footer", "nav", "aside", "form"}
    BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "blockquote", "tr", "br", "div"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        # Collapse runs of whitespace; keep paragraph breaks.
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def fetch_url(url: str, max_chars: int = 20000) -> dict:
    """Fetch a public URL and extract its main text content.

    Best for static-HTML news article pages (澎湃 / 36氪 / 新闻 sites).
    Returns plain text with HTML stripped. Does NOT execute JavaScript;
    pages that require JS to render won't give useful content.

    Args:
        url: An http(s) URL. Private IPs and non-http schemes rejected.
        max_chars: Truncate extracted text to this length (default 20k).

    Returns:
        dict with `url`, `status_code`, `content_type`, `text` (extracted),
        and `truncated` (bool).
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"url": url, "error": "only http(s) URLs allowed"}
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.startswith("10.") \
            or host.startswith("192.168.") or host.startswith("172."):
        return {"url": url, "error": "private hostnames rejected"}

    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read(2 * 1024 * 1024)  # cap raw fetch at 2 MB
            status = resp.status
    except Exception as e:
        return {"url": url, "error": f"fetch failed: {e}"}

    encoding = "utf-8"
    if "charset=" in ctype:
        encoding = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
    try:
        html = body.decode(encoding, errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")

    parser = _TextExtractor()
    parser.feed(html)
    text = parser.text()
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + "\n…[truncated]"

    return {
        "url": url,
        "status_code": status,
        "content_type": ctype,
        "text": text,
        "truncated": truncated,
    }


def fetch_rss_feed(feed_id: str, max_items: int = 30) -> dict:
    """Read latest items from a registered rsshub feed.

    Use to find recent same-genre topics or to ground writing in 时事.
    Feeds are registered in `pipeline.news_sources.FEED_REGISTRY`.

    Args:
        feed_id: One of `zhihu_hot`, `thepaper_featured`, `36kr_latest`,
                 `weibo_hot` (weibo currently requires chromium in rsshub).
        max_items: Cap returned items.

    Returns:
        dict with `feed_id`, `feed_label`, `items` (list of {title, description,
        link, published}).
    """
    from ..news_sources import fetch_feed, FEED_REGISTRY

    spec = FEED_REGISTRY.get(feed_id)
    if spec is None:
        return {
            "feed_id": feed_id,
            "error": f"unknown feed; available: {list(FEED_REGISTRY)}",
        }
    if spec.requires_browser:
        return {
            "feed_id": feed_id,
            "feed_label": spec.label,
            "error": "feed requires Playwright chromium in rsshub container",
        }
    try:
        items = fetch_feed(feed_id)
    except Exception as e:
        return {"feed_id": feed_id, "feed_label": spec.label,
                "error": f"fetch failed: {e}"}
    return {
        "feed_id": feed_id,
        "feed_label": spec.label,
        "items": [it.as_dict() for it in items[:max_items]],
    }
