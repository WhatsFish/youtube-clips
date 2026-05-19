#!/usr/bin/env python3
"""Experiment 3: vision-based localization in a long source video.

Exp 1 failure case: NVIDIA's GTC March 2025 keynote (vif8NQcjVf0, 2h11m).
Caption-fuzzy matcher couldn't find the visually distinctive moment when
Jensen holds up a Blackwell GPU because Jensen himself doesn't say
"holding up" — the action is visual, not transcribed.

This experiment uses coarse-to-fine vision search:
  1. Download the source (yt-dlp, cached)
  2. Sample frames every 60s (coarse) — ~130 frames for 2h11m
  3. Ask Claude to identify candidates matching target_desc (single call,
     all frames attached)
  4. For top 2-3 candidates, sample every 5s around them (fine)
  5. Single Claude call to pick the exact best second

Measures: did vision find the moment? at what cost / latency?

Run:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/experiment-archival-vision.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.claude_io import call_claude, extract_json
from pipeline.frames import sample_frames


PROJECT_ROOT = Path(__file__).resolve().parent.parent
YTDLP = PROJECT_ROOT / ".venv" / "bin" / "yt-dlp"
COOKIES = Path.home() / ".config" / "youtube-clips-cookies.txt"
# Bulk video working data goes on /video per CLAUDE.md (Standard SSD,
# isolated from /data which holds Docker state on the Premium SSD).
WORK_DIR = Path("/video/youtube-clips/experiments/archival-vision")
WORK_DIR.mkdir(parents=True, exist_ok=True)


def download_source(video_id: str) -> Path:
    """Download with yt-dlp at 480p (saves bandwidth/disk for sampling)."""
    out = WORK_DIR / f"{video_id}.mp4"
    if out.exists() and out.stat().st_size > 1_000_000:
        print(f"  cached: {out}")
        return out
    print(f"  downloading {video_id} (480p)...")
    cmd = [
        str(YTDLP), "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "-o", str(out),
        "--merge-output-format", "mp4",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    if COOKIES.exists():
        cmd.extend(["--cookies", str(COOKIES)])
    t0 = time.monotonic()
    subprocess.run(cmd, check=True)
    print(f"  ✓ downloaded in {time.monotonic() - t0:.0f}s: {out.stat().st_size / 1024 / 1024:.1f} MB")
    return out


def sample_at(src: Path, video_id: str, interval_sec: int, label: str) -> list[Path]:
    """Sample frames at `interval_sec` and return paths sorted by t."""
    out_dir = WORK_DIR / f"{video_id}-frames-{label}"
    out_dir.mkdir(exist_ok=True)
    existing = sorted(out_dir.glob("frame-*.jpg"))
    if existing:
        print(f"  cached {len(existing)} frames @ {interval_sec}s ({label}): {out_dir}")
        return existing
    print(f"  sampling frames every {interval_sec}s ({label})...")
    paths = sample_frames(src, out_dir, interval_sec=interval_sec)
    print(f"  ✓ extracted {len(paths)} frames")
    return paths


def frame_index_to_sec(frame_path: Path, interval_sec: int) -> int:
    """frame-NNN.jpg → (NNN-1) * interval_sec."""
    n = int(frame_path.stem.split("-")[-1])
    return (n - 1) * interval_sec


def claude_coarse_pick(frame_paths: list[Path], interval_sec: int, target_desc: str, *, batch_size: int = 30) -> list[dict]:
    """Coarse scan in batches. 136 frames in one Claude call overwhelms
    the agent (context bloat, partial-Read laziness); batches of 20-30
    are tractable and let us still consolidate at the end.

    Saves each batch's raw output to disk for debugging.
    """
    out_dir = frame_paths[0].parent if frame_paths else Path("/tmp")
    debug_dir = out_dir.parent / f"{out_dir.name}-claude-raw"
    debug_dir.mkdir(exist_ok=True)

    all_candidates: list[dict] = []
    n_batches = (len(frame_paths) + batch_size - 1) // batch_size
    for b in range(n_batches):
        batch = frame_paths[b * batch_size : (b + 1) * batch_size]
        frame_lines = []
        for p in batch:
            t = frame_index_to_sec(p, interval_sec)
            frame_lines.append(f"  {p.name}  →  t={t}s  →  {p}")
        prompt = f"""你帮我从一段视频的帧采样里找**视觉时刻**。

目标描述（target_desc）：
  {target_desc}

下面这批有 {len(batch)} 张帧（每 {interval_sec}s 一张，这是第 {b+1}/{n_batches} 批）。
**用 Read 工具逐帧看**，然后输出候选。

挑选标准：
- 画面内容跟 target_desc 描述相符（具体物体 / 动作 / 场景）
- 宁少勿错——只挑你确定看见的
- 没找到就 emit `candidates: []`，不要硬猜

**额外要求（调试用）**：在 JSON `notes` 字段里**简短描述你扫过的画面总体内容**
（比如「都是 Jensen 在台上讲话 + 几张图表，没看到他举起芯片」），让我知道
你确实看了帧而不是空手返回。

JSON schema（包在 ```json ... ``` 里）：
{{
  "candidates": [
    {{
      "frame_n": 数字,
      "t_sec": 数字,
      "what_i_see": "一句话",
      "match_strength": "high" | "medium" | "low"
    }}
  ],
  "scanned_all": true,
  "notes": "整体扫描观察（必填）"
}}

帧列表：
{chr(10).join(frame_lines)}
"""
        print(f"  → batch {b+1}/{n_batches} ({len(batch)} frames)...")
        t0 = time.monotonic()
        raw = call_claude(
            prompt,
            timeout=600,
            max_turns=max(15, 2 * len(batch) + 5),
            tools=["Read"],
            add_dirs=[batch[0].parent],
        )
        elapsed = time.monotonic() - t0
        (debug_dir / f"batch-{b+1:02d}-raw.txt").write_text(raw, encoding="utf-8")
        try:
            data = extract_json(raw)
        except Exception as e:
            print(f"    [warn] extract_json failed: {e}; raw saved")
            data = {"candidates": [], "notes": f"parse error: {e}"}
        cands = data.get("candidates") or []
        notes = data.get("notes", "(no notes)")
        print(f"    {elapsed:.0f}s  →  {len(cands)} cand  ·  notes: {notes[:90]}")
        for c in cands:
            print(f"       · t={c.get('t_sec')}s  ({c.get('match_strength', '?')})  — {c.get('what_i_see', '')[:80]}")
        all_candidates.extend(cands)

    print(f"  → total: {len(all_candidates)} candidates across {n_batches} batches")
    return all_candidates


def claude_fine_pick(frame_paths: list[Path], interval_sec: int, target_desc: str) -> dict | None:
    """Same idea but on fine-grained frames around a coarse hit."""
    frame_lines = []
    for p in frame_paths:
        t = frame_index_to_sec(p, interval_sec)
        frame_lines.append(f"  {p.name}  →  t={t}s  →  {p}")
    prompt = f"""你已经定位到一个大概范围。现在我给你**精细帧**（每 {interval_sec}s 一张），
你要找出**最精准**的那一刻。

target_desc：
  {target_desc}

从下面 {len(frame_paths)} 张帧里挑**最佳一帧**（target_desc 描述最显著的那一刻）：

{chr(10).join(frame_lines)}

输出 JSON：
```json
{{
  "best_frame_n": 数字,
  "best_t_sec": 数字,
  "what_i_see": "一句话",
  "confidence": "high" | "medium" | "low",
  "suggested_clip_start_sec": 数字（建议的剪辑起点，best_t 前 1-2s）,
  "suggested_clip_dur_sec": 数字（建议时长 4-8s）
}}
```

逐帧 Read 后再做判断。"""
    print(f"  → claude fine pick ({len(frame_paths)} frames)...")
    t0 = time.monotonic()
    raw = call_claude(
        prompt,
        timeout=600,
        max_turns=max(15, 2 * len(frame_paths) + 5),
        tools=["Read"],
        add_dirs=[frame_paths[0].parent] if frame_paths else None,
    )
    print(f"  claude returned in {time.monotonic() - t0:.0f}s, {len(raw)} chars")
    return extract_json(raw)


def main():
    # First Exp 1 failure was a misidentified source (Lex Fridman podcast).
    # Switch to the actual GTC March 2024 keynote, where Jensen first held
    # up the Blackwell motherboard ~30 min in — verified iconic moment.
    video_id = "Y2F8yisiS6E"  # NVIDIA GTC 2024 Keynote
    target_desc = (
        "Jensen Huang on stage holding up / showing the Blackwell GPU "
        "(a physical chip / motherboard / silicon wafer) to the audience. "
        "Visible Blackwell hardware in hand or being unveiled on stage."
    )
    print(f"=== Vision experiment ===")
    print(f"video_id: {video_id}")
    print(f"target_desc: {target_desc}")

    src = download_source(video_id)
    coarse = sample_at(src, video_id, interval_sec=60, label="60s")
    print(f"\n--- COARSE pass (every 60s, {len(coarse)} frames) ---")
    coarse_picks = claude_coarse_pick(coarse, 60, target_desc)
    if not coarse_picks:
        print("✗ no coarse candidates")
        return
    print(f"\ncoarse candidates ({len(coarse_picks)}):")
    for p in coarse_picks:
        print(f"  · t={p['t_sec']}s  ({p.get('match_strength', '?')})  — {p.get('what_i_see','')}")

    # Take the highest-confidence candidate. Sample fine-grained around it.
    top = sorted(
        coarse_picks,
        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("match_strength", "low"), 3),
    )[0]
    t_center = int(top["t_sec"])
    fine_window = 60  # ±30s around the coarse hit
    fine_start = max(0, t_center - fine_window // 2)
    fine_end = t_center + fine_window // 2
    print(f"\n--- FINE pass: focus on t={t_center}s, ±30s window ---")

    fine_dir = WORK_DIR / f"{video_id}-fine-{t_center}"
    fine_dir.mkdir(exist_ok=True)
    fine_paths = sorted(fine_dir.glob("frame-*.jpg"))
    if not fine_paths:
        # Sample manually using ffmpeg at 5s interval within the window
        for i, t in enumerate(range(fine_start, fine_end + 1, 5)):
            out = fine_dir / f"frame-{i+1:03d}.jpg"
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(t), "-i", str(src), "-frames:v", "1", "-q:v", "3",
                str(out),
            ], check=True)
        fine_paths = sorted(fine_dir.glob("frame-*.jpg"))
        print(f"  sampled {len(fine_paths)} fine frames @ 5s")

    # In fine pass, the "interval" is 5s but we need to label each frame with
    # actual t_sec for the prompt. Patch by renaming the frame_index_to_sec
    # call site — actually pass a custom offset/interval.
    fine_lines = []
    for i, p in enumerate(fine_paths):
        t = fine_start + i * 5
        fine_lines.append(f"  {p.name}  →  t={t}s  →  {p}")
    prompt = f"""你已经定位到 t≈{t_center}s 附近。这里有精细帧（每 5s 一张）。

target_desc：
  {target_desc}

从下面 {len(fine_paths)} 张帧里挑**最佳一帧**：

{chr(10).join(fine_lines)}

输出 JSON：
```json
{{
  "best_frame_n": 数字,
  "best_t_sec": 数字（对应秒数）,
  "what_i_see": "一句话",
  "confidence": "high" | "medium" | "low",
  "suggested_clip_start_sec": 数字,
  "suggested_clip_dur_sec": 数字（4-8s）
}}
```

逐帧 Read。"""
    t0 = time.monotonic()
    raw = call_claude(
        prompt, timeout=600,
        max_turns=max(15, 2 * len(fine_paths) + 5),
        tools=["Read"], add_dirs=[fine_dir],
    )
    print(f"  claude returned in {time.monotonic() - t0:.0f}s")
    fine = extract_json(raw)
    print(f"\n=== RESULT ===")
    print(f"  best_t_sec: {fine.get('best_t_sec')}")
    print(f"  what_i_see: {fine.get('what_i_see')}")
    print(f"  confidence: {fine.get('confidence')}")
    print(f"  suggest clip: t={fine.get('suggested_clip_start_sec')}s for {fine.get('suggested_clip_dur_sec')}s")
    print(f"  YouTube link: https://youtu.be/{video_id}?t={fine.get('best_t_sec', 0)}")


if __name__ == "__main__":
    main()
