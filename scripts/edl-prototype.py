#!/usr/bin/env python3
"""
EDL prototype: take a downloaded YouTube video + its English VTT subtitle
file, ask Claude (via the `claude` CLI) to filter + select clips + write
Chinese commentary, and emit an EDL JSON.

This is the LLM-heavy core of the youtube-clips pipeline (PLAN.md Phase
2.6 + 2.7). Hardcoded Profile + single-source assumption keep the surface
area small while we iterate on prompt quality.

Usage:
  .venv/bin/python scripts/edl-prototype.py <video_id>

Inputs:
  /video/youtube-clips/raw/<video_id>/source.mp4
  /video/youtube-clips/raw/<video_id>/source.en.vtt

Output:
  /video/youtube-clips/outputs/edl-prototype/<video_id>/edl.json
  /video/youtube-clips/outputs/edl-prototype/<video_id>/prompt.txt   (kept for review)
  /video/youtube-clips/outputs/edl-prototype/<video_id>/raw-claude.txt (kept for debugging)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_BASE = Path("/video/youtube-clips/raw")
OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")

CLAUDE_BIN = "/home/liharr/.nvm/versions/node/v24.15.0/bin/claude"

# Hardcoded Profile mirroring the seed in db/schema.sql. The real pipeline
# fetches this from Postgres; we hardcode here to keep the prototype free
# of DB dependencies while we iterate.
PROFILE = {
    "name": "tech-insights-cn",
    "source": {
        "platforms": ["youtube"],
        "language": "en",
        "content_hints": ["tech review", "AI news", "developer tools"],
    },
    "output": {
        "platforms": ["bilibili_long"],
        "language": "zh",
        "tts_voice": "zh-CN-XiaoxiaoNeural",
        "aspect_ratio": "16:9",
    },
    "style": {
        "template": "commentary",
        "pacing": "medium",
        "audio_strategy": "ducked_original",
        "caption_strategy": "burn_zh",
    },
    "edit_style_prompt": (
        "你写 commentary 风格的剪辑决策列表：从英文素材里挑出最有信息量的 5-10 个片段（每段 8-25 秒），"
        "用中文重新串讲。原片音轨压低做衬底（ducked_original），中文配音做主轨。"
        "语气专业但不刻板，可以有观点。"
    ),
}

# ---- VTT parsing ------------------------------------------------------------

TS_LINE_RE = re.compile(
    r"(\d+):(\d+):(\d+)\.(\d+)\s*-->\s*(\d+):(\d+):(\d+)\.(\d+)"
)
ANNOT_RE = re.compile(r"<\d+:\d+:\d+\.\d+>|</?c[^>]*>")


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(path: Path) -> list[tuple[float, str]]:
    """Return [(start_sec, line)] dedup'd to one entry per unique caption line.

    YouTube auto-captions interleave a "previous line + next line typing word
    by word" pattern; we strip the inline word-timestamp annotations and
    only keep the first appearance of each line.
    """
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


# ---- Prompt -----------------------------------------------------------------

PROMPT_TEMPLATE = """你是一个面向中文受众的科技频道剪辑师。频道定位与风格在 PROFILE 中。

任务：基于下面这一支英文科技 YouTube 视频的字幕，做三件事：
  1. **过滤判断**：这支视频是否值得做成中文 commentary 视频？理由是什么？
  2. **选段**：如果值得做，从字幕里挑出 5-10 个最有信息量、最适合做素材的片段。每段 8-25 秒。可以跳着挑，不必按顺序。
  3. **中文解说**：在每个片段之间写一段中文 narration，把英文素材"串"起来——既翻译关键信息，又加你自己的解读和观点。还需要写片头开场白和片尾收尾。

输出约束：
  - 中文 narration 语速按 ~4 字/秒 估算 est_duration_sec，单段建议 4-12 秒，对应 16-48 字
  - 总成片时长（所有 clip 时长 + 所有 narration 时长之和）目标 3-6 分钟
  - clip 的 start_sec / end_sec 必须从下面字幕里出现过的时间戳取值
  - 不要逐字翻译，commentary 风格要有自己的观点（比如"这其实意味着…""值得注意的是…""这个对比很有趣…"）
  - 风格：专业但不刻板，可以有观点

只输出一个 JSON，包在 ```json ... ``` 代码块里。其它任何说明文字都不要。

JSON schema:
{{
  "decision": "make" | "skip",
  "decision_reason": "中文一两句话",
  "title_zh": "中文标题，12-25 字，带钩子",
  "description_zh": "中文简介 1-2 句",
  "tags_zh": ["标签1", "标签2", ...],
  "narration_intro": {{"text": "片头中文，10-30 字", "est_duration_sec": 数字}},
  "segments": [
    {{
      "clip": {{"start_sec": 数字, "end_sec": 数字, "purpose": "为什么用这段，中文一句话"}},
      "narration_after": {{"text": "本段后面的中文解说", "est_duration_sec": 数字}}
    }}
  ],
  "narration_outro": {{"text": "片尾中文", "est_duration_sec": 数字}}
}}

如果 decision = "skip"，可省略其它字段。

================ PROFILE ================
{profile_json}

================ 视频元数据 ================
title: {title}
channel: {channel}
duration_sec: {duration}

================ 英文字幕（带时间戳） ================
{transcript}
"""


def build_prompt(
    profile: dict,
    title: str,
    channel: str,
    duration: float,
    entries: list[tuple[float, str]],
) -> str:
    return PROMPT_TEMPLATE.format(
        profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
        title=title,
        channel=channel,
        duration=int(duration),
        transcript=format_transcript(entries),
    )


# ---- Claude ----------------------------------------------------------------

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def call_claude(prompt: str) -> str:
    """Run `claude -p` with the prompt on stdin via a temp file. Returns stdout."""
    proc = subprocess.run(
        [
            CLAUDE_BIN,
            "-p", prompt,
            "--dangerously-skip-permissions",
            "--max-turns", "1",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"claude exited {proc.returncode}\n")
        sys.stderr.write(proc.stderr)
        sys.exit(2)
    return proc.stdout


def extract_json(s: str) -> dict:
    m = JSON_BLOCK_RE.search(s)
    if not m:
        # Fallback: try to find a top-level {...} block.
        m2 = re.search(r"(\{.*\})", s, re.DOTALL)
        if not m2:
            raise ValueError("no JSON found in claude output")
        return json.loads(m2.group(1))
    return json.loads(m.group(1))


# ---- Driver ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id", help="YouTube video id (11 chars)")
    ap.add_argument("--title", default="(unknown)")
    ap.add_argument("--channel", default="(unknown)")
    args = ap.parse_args()

    raw_dir = RAW_BASE / args.video_id
    vtt = raw_dir / "source.en.vtt"
    mp4 = raw_dir / "source.mp4"
    if not vtt.exists():
        sys.exit(f"missing transcript: {vtt}")
    if not mp4.exists():
        sys.exit(f"missing video: {mp4}")

    # Get duration from ffprobe (avoids hardcoding).
    dur_str = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(mp4),
        ],
        text=True,
    ).strip()
    duration = float(dur_str)

    entries = parse_vtt(vtt)
    print(f"transcript: {len(entries)} unique lines, video duration {duration:.1f}s")

    job_dir = OUT_BASE / args.video_id
    job_dir.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt(PROFILE, args.title, args.channel, duration, entries)
    (job_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"prompt: {len(prompt)} chars → {job_dir / 'prompt.txt'}")

    print("calling claude...", flush=True)
    t0 = time.monotonic()
    raw = call_claude(prompt)
    elapsed = time.monotonic() - t0
    (job_dir / "raw-claude.txt").write_text(raw, encoding="utf-8")
    print(f"claude returned in {elapsed:.1f}s, {len(raw)} chars")

    edl = extract_json(raw)
    edl_path = job_dir / "edl.json"
    edl_path.write_text(
        json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nedl saved: {edl_path}")

    # Compact summary.
    print()
    print("=" * 60)
    print(f"  decision: {edl.get('decision')}")
    print(f"  reason:   {edl.get('decision_reason', '')[:100]}")
    if edl.get("decision") == "make":
        segs = edl.get("segments", [])
        print(f"  title_zh: {edl.get('title_zh', '')}")
        print(f"  segments: {len(segs)}")
        clip_total = sum(s["clip"]["end_sec"] - s["clip"]["start_sec"] for s in segs)
        nar_total = (
            edl["narration_intro"]["est_duration_sec"]
            + sum(s["narration_after"]["est_duration_sec"] for s in segs)
            + edl["narration_outro"]["est_duration_sec"]
        )
        print(f"  clip time:      {clip_total:.1f}s")
        print(f"  narration time: {nar_total:.1f}s")
        print(f"  est. total:     {clip_total + nar_total:.1f}s ({(clip_total + nar_total)/60:.1f} min)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
