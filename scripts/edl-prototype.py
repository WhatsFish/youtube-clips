#!/usr/bin/env python3
"""
EDL prototype: take a downloaded YouTube video + its English VTT subtitle
file, ask Claude (via the `claude` CLI) to filter + select clips + write
Chinese commentary, and emit an EDL JSON.

This is the LLM-heavy core of the youtube-clips pipeline (PLAN.md Phase
2.6 + 2.7). Reads the Profile from Postgres and the prompt template from
`prompts/edl-continuous.v<n>.md` so prompt iteration and channel-style
tweaks don't require code changes.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/edl-prototype.py <video_id>
                  [--profile tech-insights-cn]
                  [--prompt-version latest]

Inputs (filesystem):
  /video/youtube-clips/raw/<video_id>/source.mp4
  /video/youtube-clips/raw/<video_id>/source.en.vtt

Inputs (DB):
  profiles row matching --profile

Inputs (repo):
  prompts/edl-continuous.v<N>.md

Output:
  /video/youtube-clips/outputs/edl-prototype/<video_id>/edl.json
  /video/youtube-clips/outputs/edl-prototype/<video_id>/prompt.txt   (kept for review)
  /video/youtube-clips/outputs/edl-prototype/<video_id>/raw-claude.txt (kept for debug)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Pipeline helpers live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.prompts import load_prompt
from pipeline.profiles import fetch_profile

RAW_BASE = Path("/video/youtube-clips/raw")
OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")
CLAUDE_BIN = "/home/liharr/.nvm/versions/node/v24.15.0/bin/claude"

# ---- VTT parsing -----------------------------------------------------------

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


# ---- Claude IO -------------------------------------------------------------

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _escape_embedded_quotes(s: str) -> str:
    """Walk a JSON-ish blob and escape any ASCII double-quote that appears
    inside a string value but isn't the actual string terminator. Claude
    routinely embeds ASCII `"..."` for emphasis inside Chinese narration,
    which lands in a JSON string and breaks json.loads.

    A `"` is a legitimate string terminator iff the next non-whitespace
    char is one of ,:}] (or end-of-input). Anything else means the `"` is
    embedded literally and we must escape it as \\". Also escapes raw
    \\n, \\r, \\t inside string values.
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


def call_claude(prompt: str) -> str:
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


# ---- Driver ---------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id", help="YouTube video id (11 chars)")
    ap.add_argument("--title", default="(unknown)")
    ap.add_argument("--channel", default="(unknown)")
    ap.add_argument(
        "--profile",
        default="tech-insights-cn",
        help="Profile name (DB row in profiles.name)",
    )
    ap.add_argument(
        "--prompt-version",
        default="latest",
        help='Prompt template version, "latest" or an integer (default: latest)',
    )
    args = ap.parse_args()

    raw_dir = RAW_BASE / args.video_id
    vtt = raw_dir / "source.en.vtt"
    mp4 = raw_dir / "source.mp4"
    if not vtt.exists():
        sys.exit(f"missing transcript: {vtt}")
    if not mp4.exists():
        sys.exit(f"missing video: {mp4}")

    # Load Profile + prompt template.
    profile = fetch_profile(args.profile)
    print(f"profile: {profile.name} (id={profile.id}, active={profile.active})")
    pv = args.prompt_version
    prompt_tmpl = load_prompt(
        "edl-continuous", version=int(pv) if pv != "latest" else "latest"
    )
    print(f"prompt:  {prompt_tmpl.stamp}  ({prompt_tmpl.source_path.name})")

    # Get duration from ffprobe.
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

    prompt = prompt_tmpl.render(
        profile_block=profile.render_block(),
        title=args.title,
        channel=args.channel,
        duration=int(duration),
        transcript=format_transcript(entries),
    )
    (job_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"prompt: {len(prompt)} chars → {job_dir / 'prompt.txt'}")

    print("calling claude...", flush=True)
    t0 = time.monotonic()
    raw = call_claude(prompt)
    elapsed = time.monotonic() - t0
    (job_dir / "raw-claude.txt").write_text(raw, encoding="utf-8")
    print(f"claude returned in {elapsed:.1f}s, {len(raw)} chars")

    edl = extract_json(raw)
    # Stamp identity into the output so a future reader knows exactly
    # which profile row + which prompt version produced this EDL.
    edl["profile_name"] = profile.name
    edl["prompt_template_version"] = prompt_tmpl.stamp
    edl["rendered_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
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
        est_sec = total_chars / 4.0
        print(
            f"  narration: {total_chars} chars (~{est_sec:.0f}s @ 4 chars/sec, "
            f"~{est_sec/60:.1f} min)"
        )
        print(f"  stamp:    profile={profile.name}  prompt={prompt_tmpl.stamp}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
