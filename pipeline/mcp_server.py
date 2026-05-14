"""MCP server exposing youtube-clips atomic tools to Claude.

Run as a stdio server. Claude CLI connects via `--mcp-config <json>`;
the config points at this script as the command, and Claude proxies
tool calls over stdio.

Currently registers:
  - search_bilibili         (Bilibili search API)
  - read_bilibili_video     (Bilibili video info + AI transcript)
  - fetch_url               (Plain-text extract from a URL)
  - fetch_rss_feed          (One of the registered rsshub feeds)

Add a new tool: decorate a function with `@mcp.tool()` and write its
docstring carefully — Claude reads the docstring + arg annotations as
the tool's user-facing contract.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `pipeline.*` importable when launched as `python -m pipeline.mcp_server`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from pipeline.tools.bilibili_tools import search_bilibili, read_bilibili_video
from pipeline.tools.web_tools import fetch_url, fetch_rss_feed
from pipeline.tools.search_tools import web_search
from pipeline.tools.channel_tools import list_recent_videos
from pipeline.tools.pexels_tools import preview_pexels
from pipeline.tools.image_tools import read_image, read_youtube_thumbnail
from pipeline.tools.person_search import search_person_image


mcp = FastMCP(
    name="youtube-clips-tools",
    instructions=(
        "Atomic capabilities for the youtube-clips video pipeline. Use "
        "these to look up real-world same-topic videos, read source "
        "articles, and ground your writing in current discourse before "
        "producing the final script."
    ),
)

# Register each tool. FastMCP introspects the function's type hints +
# docstring to build the tool schema sent to Claude.
mcp.tool()(search_bilibili)
mcp.tool()(read_bilibili_video)
mcp.tool()(fetch_url)
mcp.tool()(fetch_rss_feed)
mcp.tool()(web_search)
mcp.tool()(list_recent_videos)
mcp.tool()(preview_pexels)
# Image-returning tools need structured_output=False so FastMCP doesn't try
# to build a Pydantic schema for the `Image | dict` union (it chokes on the
# `Image` helper class).
mcp.add_tool(read_image, structured_output=False)
mcp.add_tool(read_youtube_thumbnail, structured_output=False)
mcp.tool()(search_person_image)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
