"""Style-exemplar loader for Bilibili reference videos.

Each Profile's `channel.style_exemplars.ref_bvids` list names BV ids
that were harvested into `/video/youtube-clips/exemplars/<BV>.json`
(see `scripts/harvest-bili-exemplars.py`). At prompt-build time we
load those JSON files and render a compact "study these for hook +
rhythm" block to inject into Stage 2 prompts (edl-synthesis.v1 and
producer-script.v1).

Per-exemplar block format:
  - title (the hook)
  - uper + view count (so the agent sees this is a validated viral pick)
  - first ~30s of transcript (where the opening hook lives)
  - last ~20s of transcript (where the takeaway lives)

That's ~500-800 chars per exemplar; with 2-3 exemplars per Profile,
total exemplar overhead is ~1.5-2.5 KB on top of the existing prompt
— acceptable given the writing-quality lift.
"""

from __future__ import annotations

import json
from pathlib import Path

EXEMPLARS_BASE = Path("/video/youtube-clips/exemplars")

OPENING_WINDOW_SEC = 30
CLOSING_WINDOW_SEC = 20


def _format_seconds(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    return f"{m:02d}:{s:02d}"


def _opening_text(lines: list[dict], window_sec: int = OPENING_WINDOW_SEC) -> str:
    """Concatenate transcript lines that fall within the first `window_sec`."""
    chosen = [l["text"] for l in lines if (l.get("start") or 0) <= window_sec]
    return "".join(chosen).strip()


def _closing_text(lines: list[dict], window_sec: int = CLOSING_WINDOW_SEC) -> str:
    """Concatenate transcript lines from the last `window_sec` of the video.

    We use the max start timestamp as the video's end approximation —
    accurate enough since trailing lines in an AI subtitle usually cover
    the entire monologue.
    """
    if not lines:
        return ""
    end = max((l.get("end") or l.get("start") or 0) for l in lines)
    cutoff = end - window_sec
    chosen = [l["text"] for l in lines if (l.get("start") or 0) >= cutoff]
    return "".join(chosen).strip()


def load_exemplar(bvid: str) -> dict | None:
    """Read one harvested exemplar from disk. Returns None on missing."""
    path = EXEMPLARS_BASE / f"{bvid}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_exemplars_block(ref_bvids: list[str]) -> str:
    """Build the prompt-ready Markdown block for the given exemplars.

    Returns an empty string when no exemplars resolve, so the prompt
    template's `{style_exemplars_block}` cleanly degrades to nothing.
    """
    if not ref_bvids:
        return ""
    chunks: list[str] = []
    for bv in ref_bvids:
        ex = load_exemplar(bv)
        if not ex:
            continue
        opening = _opening_text(ex.get("transcript_lines") or [])
        closing = _closing_text(ex.get("transcript_lines") or [])
        stat = ex.get("stat") or {}
        view = stat.get("view") or 0
        like = stat.get("like") or 0
        reply = stat.get("reply") or 0
        head = (
            f"—— 范例《{ex.get('title','')}》 ——\n"
            f"  UP 主: {ex.get('owner','')}\n"
            f"  数据:  view={view:,}  like={like:,}  reply={reply:,}\n"
        )
        if opening:
            head += f"  开场 (0-{OPENING_WINDOW_SEC}s):\n    {opening}\n"
        if closing:
            head += f"  收尾 (最后 {CLOSING_WINDOW_SEC}s):\n    {closing}\n"
        chunks.append(head)
    if not chunks:
        return ""
    intro = (
        "下面是几支同类高表现 Bilibili 视频的开场和收尾节选 —— **学这些**：\n"
        "1) 标题怎么挂钩 (数字 / 反差 / 情绪词 / 群体点名)\n"
        "2) 第一句话怎么进入 (先抛冲突 / 先说反常识 / 先点观众痛处)\n"
        "3) 收尾怎么留 takeaway (可带走的判断 / 留余韵的画面)\n"
        "**不要照抄具体内容**，只学结构 / 节奏 / 句式偏好。\n\n"
    )
    return intro + "\n".join(chunks)
