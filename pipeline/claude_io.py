"""Claude CLI wrapper + JSON extraction.

Every script in this project that talks to Claude does the same three
things: invoke `claude -p`, capture stdout, fish a JSON block out of the
response. Centralized here so a fix in one place benefits everywhere.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CLAUDE_BIN = "/home/liharr/.nvm/versions/node/v24.15.0/bin/claude"

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

# Project-local MCP server registry. Stage 2 prompts pass `mcp_config=DEFAULT_MCP_CONFIG`
# to enable tool-use of the youtube-clips atomic capability set
# (search_bilibili / read_bilibili_video / fetch_url / fetch_rss_feed).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MCP_CONFIG = PROJECT_ROOT / ".mcp-config.json"
DEFAULT_MCP_TOOLS = [
    "mcp__ytclips__search_bilibili",
    "mcp__ytclips__read_bilibili_video",
    "mcp__ytclips__fetch_url",
    "mcp__ytclips__fetch_rss_feed",
    "mcp__ytclips__web_search",
    "mcp__ytclips__list_recent_videos",
    "mcp__ytclips__preview_pexels",
    "mcp__ytclips__read_image",
    "mcp__ytclips__read_youtube_thumbnail",
]


def _escape_embedded_quotes(s: str) -> str:
    """Walk a JSON-ish blob and escape any ASCII double-quote that appears
    inside a string value but isn't the actual string terminator. Claude
    routinely embeds ASCII `"..."` for emphasis inside Chinese narration,
    which lands in a JSON string and breaks json.loads.

    A `"` is a legitimate string terminator iff the next non-whitespace
    char is one of ,:}] (or end-of-input). Anything else means the `"` is
    embedded literally and we must escape it as \\". Also escapes raw
    \\n / \\r / \\t inside string values.
    """
    out: list[str] = []
    i = 0
    n = len(s)
    in_str = False
    while i < n:
        c = s[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c)
            out.append(s[i + 1])
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in ",:}]":
                out.append(c)
                in_str = False
                i += 1
            else:
                out.append('\\"')
                i += 1
            continue
        if c == "\n":
            out.append("\\n"); i += 1; continue
        if c == "\r":
            out.append("\\r"); i += 1; continue
        if c == "\t":
            out.append("\\t"); i += 1; continue
        out.append(c)
        i += 1
    return "".join(out)


def call_claude(
    prompt: str,
    *,
    timeout: int = 300,
    max_turns: int = 1,
    tools: list[str] | None = None,
    add_dirs: list[str | Path] | None = None,
    mcp_config: Path | str | None = None,
    mcp_tools: list[str] | None = None,
) -> str:
    """Run `claude -p`, return stdout. Aborts the process on non-zero exit.

    For vision-aware calls (Stage 1 reading frame jpgs out-of-band),
    pass `tools=["Read"]` and `add_dirs=[<frames_dir>]` so the agent can
    Read the images. Bumps `max_turns` accordingly is the caller's
    responsibility — one Read per frame plus one final answer turn.
    Without those args the function behaves exactly like before
    (single-turn, no tool access), preserving the cheap text-only path.

    For MCP-tool-augmented calls (Stage 2 prompts that benefit from
    looking up same-topic Bilibili videos, fetching source URLs, etc.),
    pass `mcp_config=DEFAULT_MCP_CONFIG` and `mcp_tools=DEFAULT_MCP_TOOLS`
    (or a subset). `max_turns` should be bumped to allow exploration —
    typically 8-15 covers most tool-use patterns.
    """
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--max-turns", str(max_turns),
    ]
    # Compose tools list: built-ins (Read, etc) + MCP tools (mcp__*).
    all_tools: list[str] = list(tools or [])
    if mcp_tools:
        all_tools.extend(mcp_tools)
    if all_tools:
        # `--tools` accepts a space-separated list per CLI help. Passing as
        # a single token preserves shell-safe quoting (subprocess.run with a
        # list arg doesn't shell-interpret anyway, but keep tokens clean).
        cmd.extend(["--tools", " ".join(all_tools)])
    if mcp_config:
        cmd.extend(["--mcp-config", str(mcp_config)])
    if add_dirs:
        cmd.append("--add-dir")
        cmd.extend(str(p) for p in add_dirs)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"claude exited {proc.returncode}\n")
        sys.stderr.write(proc.stderr)
        sys.exit(2)
    return proc.stdout


def extract_json(s: str) -> dict:
    """Pull a JSON object out of a Claude response. Prefer a fenced
    ```json ... ``` block; fall back to the first balanced {...}. Runs
    the embedded-quote sanitizer before json.loads.
    """
    m = JSON_BLOCK_RE.search(s)
    if m:
        body = m.group(1)
    else:
        m2 = re.search(r"(\{.*\})", s, re.DOTALL)
        if not m2:
            raise ValueError("no JSON found in claude output")
        body = m2.group(1)
    body = _escape_embedded_quotes(body)
    return json.loads(body)
