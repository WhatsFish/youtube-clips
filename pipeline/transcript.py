"""WebVTT parsing.

YouTube auto-captions ship as VTT with two quirks:
  * they interleave a previous-line + current-line "typing animation"
    pattern across consecutive cues, so a naïve dump produces lots of
    duplicates;
  * each typing cue has inline `<00:00:00.000><c>word</c>` annotations
    that need stripping.

`parse_vtt` returns one entry per unique caption line with the cue's
start timestamp; `format_transcript` renders that for inclusion in a
prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

TS_LINE_RE = re.compile(
    r"(\d+):(\d+):(\d+)\.(\d+)\s*-->\s*(\d+):(\d+):(\d+)\.(\d+)"
)
ANNOT_RE = re.compile(r"<\d+:\d+:\d+\.\d+>|</?c[^>]*>")


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(path: Path) -> list[tuple[float, str]]:
    """Return [(start_sec, line)] dedup'd to one entry per unique caption line."""
    text = path.read_text(encoding="utf-8")
    cues: list[tuple[float, list[str]]] = []
    cur_start: float | None = None
    cur_lines: list[str] = []
    for line in text.split("\n"):
        m = TS_LINE_RE.search(line)
        if m:
            if cur_start is not None:
                cues.append((cur_start, cur_lines))
            cur_start = _ts_to_sec(*m.groups()[:4])
            cur_lines = []
            continue
        if cur_start is None:
            continue
        cleaned = ANNOT_RE.sub("", line).strip()
        if cleaned:
            cur_lines.append(cleaned)
    if cur_start is not None:
        cues.append((cur_start, cur_lines))

    seen: set[str] = set()
    out: list[tuple[float, str]] = []
    for start, lines in cues:
        for ln in lines:
            if ln not in seen:
                out.append((start, ln))
                seen.add(ln)
    return out


def format_transcript(entries: list[tuple[float, str]]) -> str:
    """Render as `[mm:ss.s] text` lines for Claude to reference."""
    out = []
    for sec, line in entries:
        m, s = divmod(sec, 60)
        out.append(f"[{int(m):02d}:{s:05.2f}] {line}")
    return "\n".join(out)
