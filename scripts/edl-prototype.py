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

PROMPT_TEMPLATE = """你是一个面向中文受众的 Bilibili 科技频道 UP 主。频道定位与风格在 PROFILE 中。

输出格式：**连续中文解说**，源视频做 B-roll（视觉素材）。**不是**"放一段源视频，然后中文解说一段，再放一段源视频"——那种格式没意义。正确的格式是：
  - 中文解说不间断，从头到尾流畅连贯，像 UP 主在镜头外讲解
  - 源视频画面按解说内容选段，作为视觉支撑（你解说什么，画面就给什么）
  - 源视频的英文原声会被压到 ~10% 做背景气氛，中文解说是主音轨
  - 视频是分镜（shots）的序列：每个 shot = 一句中文解说 + 对应的源视频时间段；shot 切换 = 解说推进到下一个意思

任务：基于下面这支英文科技 YouTube 视频的字幕：
  1. **过滤判断**：这支视频是否值得做成中文 commentary？理由是什么？
  2. **写解说脚本**：把整支视频的精华提炼成一篇连贯的中文解说，像在跟观众讲一个故事。**不要逐句翻译**——挑重点、加你自己的解读和观点。语气：年轻、专业、有态度，可以用"划重点""反常识的是""值得注意的是""这就有意思了"这种连接词。
  3. **拆分成 shots**：把解说脚本按"换一个意思"切成 8-15 个 shot。每个 shot 包含一句话（建议 15-50 个中文字，对应 4-12 秒朗读时长），以及它对应的源视频时间段——观众听到这句话时画面应该在讲什么。

输出约束：
  - **解说连贯不断**：把所有 shot 的 narration 拼起来读出来应该是一篇通顺的中文，过渡自然
  - **shot 数量 8-15 个**，第一个 shot 是 hook（钩子开场），最后一个 shot 是收尾观点
  - **source_start_sec 必须从下面字幕里出现过的时间戳里取**——你要"指"着源视频的某个时间点说"看这里"
  - 总时长（所有 narration 朗读时间之和）目标 3-5 分钟
  - 不要片头黑屏、不要片尾黑屏——所有时间都有源视频画面在播

只输出一个 JSON，包在 ```json ... ``` 代码块里。其它任何说明文字都不要。

**重要：JSON 字符串内部如果要用引号做强调，必须用中文引号「」或弯引号""，不要用 ASCII 双引号 `"`，否则会破坏 JSON 语法。**

JSON schema:
{{
  "decision": "make" | "skip",
  "decision_reason": "中文一两句话",
  "title_zh": "中文标题，12-25 字，带钩子",
  "description_zh": "中文简介 1-2 句",
  "tags_zh": ["标签1", "标签2", ...],
  "shots": [
    {{
      "narration": "本 shot 的中文解说（15-50 字）",
      "source_start_sec": 数字,
      "purpose": "选这段画面的原因，中文一句话"
    }}
  ]
}}

如果 decision = "skip"，可省略 shots 等字段。

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


def _escape_embedded_quotes(s: str) -> str:
    """Walk a JSON-ish blob and escape any ASCII double-quote that appears
    inside a string value but isn't the actual string terminator. Claude
    routinely embeds ASCII `"..."` for emphasis inside Chinese narration,
    which lands in a JSON string and breaks json.loads.

    A `"` is a legitimate string terminator iff the next non-whitespace
    char is one of ,:}] (or end-of-input). Anything else means the `"` is
    embedded literally and we must escape it as \\".
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
        # Also escape raw newlines inside strings — JSON forbids them.
        if c == "\n":
            out.append("\\n")
            i += 1
            continue
        if c == "\r":
            out.append("\\r")
            i += 1
            continue
        if c == "\t":
            out.append("\\t")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


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
        m2 = re.search(r"(\{.*\})", s, re.DOTALL)
        if not m2:
            raise ValueError("no JSON found in claude output")
        body = m2.group(1)
    else:
        body = m.group(1)
    body = _escape_embedded_quotes(body)
    return json.loads(body)


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
    # Stamp the Profile name into the EDL so downstream tooling (web UI,
    # render module) can group / filter without consulting the DB.
    edl.setdefault("profile_name", PROFILE["name"])
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
        shots = edl.get("shots", [])
        print(f"  title_zh: {edl.get('title_zh', '')}")
        print(f"  shots:    {len(shots)}")
        total_chars = sum(len(s["narration"]) for s in shots)
        # ~4 chars/sec at ~+15% rate is ~4.6 chars/sec; conservatively 4.
        est_sec = total_chars / 4.0
        print(f"  narration: {total_chars} chars (~{est_sec:.0f}s @ 4chars/sec, ~{est_sec/60:.1f} min)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
