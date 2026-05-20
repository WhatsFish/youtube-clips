"""Heavy-lift archival operations: source download, frame sampling,
vision-based localization. Kept separate from the lightweight MCP
wrappers in `pipeline.tools.archival_tools` because this module pulls
in ffmpeg / yt-dlp / Claude vision.

Used by `localize_in_video` (MCP tool) and `_acquire_one_archival` (in
produce-original.py).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .claude_io import call_claude, extract_json
from .frames import sample_frames


PROJECT_ROOT = Path(__file__).resolve().parent.parent
YTDLP = PROJECT_ROOT / ".venv" / "bin" / "yt-dlp"
COOKIES = Path.home() / ".config" / "youtube-clips-cookies.txt"
ARCHIVAL_BASE = Path("/video/youtube-clips/archival-sources")


# Confidence threshold to trust caption fuzzy. Below this, fall through
# to vision. Picked from experiment data: B站 0.65 was correct, YouTube
# 0.55 was wrong but at correct source level. 0.5 is the boundary where
# matches start being reliable within a known-good source.
CAPTION_CONF_THRESHOLD = 0.50

# Frame sampling intervals
COARSE_INTERVAL_SEC = 60
FINE_INTERVAL_SEC = 5
FINE_WINDOW_SEC = 60   # ±30s around the coarse hit

# Batch size for Claude vision coarse scan — larger batches save calls
# but degrade attention; 30 frames is the sweet spot from Exp 3.
VISION_BATCH_SIZE = 30

# Strength → numeric confidence mapping for vision outputs.
_STRENGTH_TO_CONF = {"high": 0.85, "medium": 0.6, "low": 0.35}


@dataclass
class LocalizeResult:
    start_sec: float
    end_sec: float
    confidence: float
    method: str             # "caption" | "vision" | "vision_coarse_only" | "none"
    excerpt: str            # transcript line or vision frame description
    source_url: str         # canonical url for this clip
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "start_sec": round(self.start_sec, 2),
            "end_sec": round(self.end_sec, 2),
            "confidence": round(self.confidence, 2),
            "method": self.method,
            "excerpt": self.excerpt,
            "source_url": self.source_url,
            "error": self.error,
        }


def localize_in_video(
    video_id: str,
    source: str,
    target_desc: str,
    target_dur_sec: float = 7.0,
    *,
    skip_caption: bool = False,
    skip_vision: bool = False,
) -> dict:
    """Find the best timestamp range in a video matching target_desc.

    Two-tier:
      Tier A — caption / transcript fuzzy match (cheap, works for
        concept-rich content like speeches).
      Tier B — coarse 60s vision scan + fine 5s vision scan (expensive
        but reliable for visual moments where captions don't describe
        the action).

    Args:
        video_id: B 站 BVid (e.g. "BV1xx...") or YouTube id (11-char).
        source: "bilibili" or "youtube".
        target_desc: what to find — a sentence describing the visual /
            content moment. Detailed > terse ("Jensen holds up a
            Blackwell motherboard" > "Blackwell unveil").
        target_dur_sec: how long the resulting clip should be (default 7).
        skip_caption: bypass Tier A (only use vision).
        skip_vision: bypass Tier B (only use captions; will return
            low-confidence result if captions don't match well).

    Returns:
        dict with start_sec / end_sec / confidence / method / excerpt /
        source_url. `error` populated when localization failed entirely.
    """
    if source not in ("bilibili", "youtube"):
        return LocalizeResult(
            0, 0, 0, "none", "", "",
            error=f"unknown source {source!r}",
        ).to_dict()

    source_url = _url_for(video_id, source)
    # Visual targets ("Jensen holds up Blackwell") can't be reliably found
    # via captions because the subject doesn't say "I'm holding it up";
    # raise the bar so we go to vision instead of trusting a high-conf
    # caption hit that's actually unrelated (just shares keywords).
    is_visual = _is_visual_target(target_desc)
    caption_threshold = 0.80 if is_visual else CAPTION_CONF_THRESHOLD

    caption_result: LocalizeResult | None = None
    if not skip_caption:
        caption_result = _try_caption(video_id, source, target_desc, target_dur_sec, source_url)
        if caption_result and caption_result.confidence >= caption_threshold:
            return caption_result.to_dict()

    if skip_vision:
        if caption_result:
            return caption_result.to_dict()
        return LocalizeResult(
            0, 0, 0, "none", "", source_url,
            error="no caption match and skip_vision=True",
        ).to_dict()

    # Tier B: vision
    try:
        vision = _try_vision(video_id, source, target_desc, target_dur_sec, source_url)
        if vision and vision.method != "none":
            return vision.to_dict()
    except Exception as e:
        # Fall back to caption (even low conf) if vision blows up
        if caption_result:
            caption_result.method = "caption_fallback_after_vision_error"
            caption_result.error = f"vision failed: {e}"
            return caption_result.to_dict()
        return LocalizeResult(
            0, 0, 0, "none", "", source_url,
            error=f"vision failed: {e}",
        ).to_dict()

    if caption_result:
        # Vision found nothing but we have a low-conf caption hit
        caption_result.method = "caption_low_conf"
        return caption_result.to_dict()
    return LocalizeResult(
        0, 0, 0, "none", "", source_url,
        error="no caption hit and vision found no candidates",
    ).to_dict()


# ---------------------------------------------------------------------------
# Tier A — caption / transcript fuzzy match
# ---------------------------------------------------------------------------


def _try_caption(
    video_id: str, source: str, target_desc: str, target_dur_sec: float,
    source_url: str,
) -> LocalizeResult | None:
    from .tools.archival_tools import (
        read_bilibili_transcript, read_youtube_transcript,
    )
    if source == "bilibili":
        txt = read_bilibili_transcript(video_id)
    else:
        txt = read_youtube_transcript(video_id, language="en")
    lines = txt.get("transcript_lines") or []
    if not lines:
        return None
    return _fuzzy_match(lines, target_desc, target_dur_sec, source_url)


# Visual-action verbs / nouns that signal "captions probably won't
# describe this — go to vision". When any of these appear in target_desc,
# we apply a stricter caption threshold (or skip caption entirely).
_VISUAL_CUE_RE = re.compile(
    r"holding up|holds up|lifting|lifts|showing|displays|unveils|"
    r"walks on stage|points to|gestures|holds out|"
    r"举起|拿起|展示|揭幕|上台|走上台|手持|捧着|对着镜头",
    re.IGNORECASE,
)


def _is_visual_target(target_desc: str) -> bool:
    return bool(_VISUAL_CUE_RE.search(target_desc))


def _fuzzy_match(
    lines: list[dict], target_desc: str, target_dur_sec: float,
    source_url: str,
) -> LocalizeResult | None:
    target_norm = re.sub(r"\s+", " ", target_desc.lower()).strip()
    items = [(float(l["start"]), str(l.get("text", "")).lower()) for l in lines]
    if not items:
        return None

    # Reduce keyword-hit boost (was 0.10) — with high-frequency keywords
    # like "Blackwell" appearing 50+ times in a 2h keynote, every window
    # picks up the boost and ranking devolves to "longest window with
    # the keyword". Cap total keyword contribution at 0.15 so the
    # SequenceMatcher base ratio remains the dominant signal.
    KW_BOOST_PER_HIT = 0.04
    MAX_KW_BOOST = 0.15

    best = None
    for i, (start, _) in enumerate(items):
        parts = []
        j = i
        while j < len(items) and items[j][0] < start + target_dur_sec:
            parts.append(items[j][1])
            j += 1
        if not parts:
            continue
        window = " ".join(parts).strip()
        if not window:
            continue
        base = SequenceMatcher(None, target_norm, window).ratio()
        keywords = [t for t in re.findall(r"[一-鿿]{2,}|\w{3,}", target_norm) if t]
        kw_hits = sum(1 for k in keywords if k in window)
        score = base + min(MAX_KW_BOOST, KW_BOOST_PER_HIT * kw_hits)
        end = items[j - 1][0] if j > i else start + target_dur_sec
        if best is None or score > best[0]:
            best = (score, start, end, window)
    if best is None:
        return None
    score, st, en, tx = best
    end = min(en, st + target_dur_sec)
    return LocalizeResult(
        start_sec=st,
        end_sec=end,
        confidence=min(1.0, score),
        method="caption",
        excerpt=tx[:200],
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# Tier B — coarse-to-fine vision
# ---------------------------------------------------------------------------


def _try_vision(
    video_id: str, source: str, target_desc: str, target_dur_sec: float,
    source_url: str,
) -> LocalizeResult | None:
    src = ensure_downloaded(video_id, source)
    coarse_dir = src.parent / "frames-60s"
    coarse_paths = (
        sorted(coarse_dir.glob("frame-*.jpg"))
        or sample_frames(src, coarse_dir, interval_sec=COARSE_INTERVAL_SEC)
    )
    if not coarse_paths:
        return None

    coarse_candidates = _claude_vision_coarse(
        coarse_paths, COARSE_INTERVAL_SEC, target_desc,
    )
    if not coarse_candidates:
        return LocalizeResult(0, 0, 0, "none", "", source_url)

    # Take top candidate by strength
    top = sorted(
        coarse_candidates,
        key=lambda c: {"high": 0, "medium": 1, "low": 2}.get(
            c.get("match_strength", "low"), 3,
        ),
    )[0]
    t_center = int(top["t_sec"])

    fine_paths = _sample_fine(src, t_center)
    if not fine_paths:
        # Only the coarse pick; clip around t_center
        return LocalizeResult(
            start_sec=max(0, t_center - 1),
            end_sec=t_center + target_dur_sec - 1,
            confidence=_STRENGTH_TO_CONF.get(top.get("match_strength", "low"), 0.3),
            method="vision_coarse_only",
            excerpt=top.get("what_i_see", "")[:200],
            source_url=source_url,
        )

    fine = _claude_vision_fine(fine_paths, t_center, target_desc)
    if not fine or "best_t_sec" not in fine:
        return LocalizeResult(
            start_sec=max(0, t_center - 1),
            end_sec=t_center + target_dur_sec - 1,
            confidence=_STRENGTH_TO_CONF.get(top.get("match_strength", "low"), 0.3),
            method="vision_coarse_only",
            excerpt=top.get("what_i_see", "")[:200],
            source_url=source_url,
        )
    start = float(fine.get("suggested_clip_start_sec") or max(0, fine["best_t_sec"] - 1))
    dur = float(fine.get("suggested_clip_dur_sec") or target_dur_sec)
    return LocalizeResult(
        start_sec=start,
        end_sec=start + dur,
        confidence=_STRENGTH_TO_CONF.get(fine.get("confidence", "medium"), 0.6),
        method="vision",
        excerpt=fine.get("what_i_see", "")[:200],
        source_url=source_url,
    )


def _frame_t(frame_path: Path, interval_sec: int) -> int:
    n = int(frame_path.stem.split("-")[-1])
    return (n - 1) * interval_sec


def _claude_vision_coarse(
    frame_paths: list[Path], interval_sec: int, target_desc: str,
) -> list[dict]:
    all_candidates: list[dict] = []
    n_batches = (len(frame_paths) + VISION_BATCH_SIZE - 1) // VISION_BATCH_SIZE
    debug_dir = frame_paths[0].parent.parent / f"{frame_paths[0].parent.name}-claude-raw"
    debug_dir.mkdir(exist_ok=True)
    for b in range(n_batches):
        batch = frame_paths[b * VISION_BATCH_SIZE : (b + 1) * VISION_BATCH_SIZE]
        frame_lines = "\n".join(
            f"  {p.name}  →  t={_frame_t(p, interval_sec)}s  →  {p}"
            for p in batch
        )
        prompt = f"""你从一段视频的帧采样里找**视觉时刻**。

目标描述（target_desc）：
  {target_desc}

下面是第 {b+1}/{n_batches} 批，{len(batch)} 张帧（每 {interval_sec}s 一张）。
**用 Read 工具逐帧看**，然后输出候选。

挑选标准：
- 画面内容跟 target_desc 描述相符（具体物体 / 动作 / 场景）
- 宁少勿错——只挑你确定看见的
- 没找到就 emit `candidates: []`，不要硬猜

**额外要求**：notes 字段里简短描述你扫过的画面总体内容
（让我知道你确实看了帧而不是空手返回）。

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
{frame_lines}
"""
        raw = call_claude(
            prompt, timeout=600,
            max_turns=max(15, 2 * len(batch) + 5),
            tools=["Read"],
            add_dirs=[batch[0].parent],
        )
        (debug_dir / f"coarse-batch-{b+1:02d}.txt").write_text(raw, encoding="utf-8")
        try:
            data = extract_json(raw)
        except Exception:
            data = {"candidates": []}
        all_candidates.extend(data.get("candidates") or [])
    return all_candidates


def _sample_fine(src: Path, t_center: int) -> list[Path]:
    fine_dir = src.parent / f"frames-5s-{t_center}"
    fine_dir.mkdir(exist_ok=True)
    existing = sorted(fine_dir.glob("frame-*.jpg"))
    if existing:
        return existing
    fine_start = max(0, t_center - FINE_WINDOW_SEC // 2)
    fine_end = t_center + FINE_WINDOW_SEC // 2
    paths: list[Path] = []
    for i, t in enumerate(range(fine_start, fine_end + 1, FINE_INTERVAL_SEC)):
        out = fine_dir / f"frame-{i+1:03d}.jpg"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(t), "-i", str(src),
            "-frames:v", "1", "-q:v", "3",
            str(out),
        ], check=True)
        paths.append(out)
    # Sidecar txt with t_offset so _claude_vision_fine knows the absolute t.
    (fine_dir / "_meta.txt").write_text(f"start_sec={fine_start}\ninterval_sec={FINE_INTERVAL_SEC}\n")
    return paths


def _claude_vision_fine(
    frame_paths: list[Path], t_center: int, target_desc: str,
) -> dict | None:
    meta = (frame_paths[0].parent / "_meta.txt").read_text()
    start_sec = int(re.search(r"start_sec=(\d+)", meta).group(1))
    interval_sec = int(re.search(r"interval_sec=(\d+)", meta).group(1))
    frame_lines = "\n".join(
        f"  {p.name}  →  t={start_sec + i * interval_sec}s  →  {p}"
        for i, p in enumerate(frame_paths)
    )
    prompt = f"""你已经定位到 t≈{t_center}s 附近。这里有精细帧（每 {interval_sec}s 一张）。

target_desc：
  {target_desc}

从下面 {len(frame_paths)} 张帧里挑**最佳一帧**：

{frame_lines}

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
    raw = call_claude(
        prompt, timeout=600,
        max_turns=max(15, 2 * len(frame_paths) + 5),
        tools=["Read"],
        add_dirs=[frame_paths[0].parent],
    )
    (frame_paths[0].parent / "_claude-fine-raw.txt").write_text(raw, encoding="utf-8")
    try:
        return extract_json(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Source download (yt-dlp wrapper) — shared between localize + acquire
# ---------------------------------------------------------------------------


def ensure_downloaded(video_id: str, source: str, *, profile_name: str | None = None) -> Path:
    """Download the source video (if not already cached) and return path.

    Cached under /video/youtube-clips/archival-sources/<source>/<id>/source.mp4.
    480p saves bandwidth/disk — quality is fine for sampling + final clip
    at 1280x720 bilibili / 720x1280 douyin targets.

    On first download, also writes meta.json with title/channel/duration so
    later runs can search the archival pool via search_archival_cache.
    """
    if source not in ("bilibili", "youtube"):
        raise ValueError(f"unknown source {source!r}")
    cache_dir = ARCHIVAL_BASE / source / video_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / "source.mp4"
    if out.exists() and out.stat().st_size > 1_000_000:
        meta_path = cache_dir / "meta.json"
        if not meta_path.exists():
            _backfill_meta_json(cache_dir, video_id, source, profile_name=profile_name)
        return out

    url = _url_for(video_id, source)
    cmd = [
        str(YTDLP),
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "-o", str(out),
        "--merge-output-format", "mp4",
        "--write-info-json",
        url,
    ]
    if source == "youtube":
        if COOKIES.exists():
            cmd.extend(["--cookies", str(COOKIES)])
    elif source == "bilibili":
        bili_cookies = Path.home() / ".config" / "youtube-clips-bili-cookies.txt"
        if bili_cookies.exists():
            cmd.extend(["--cookies", str(bili_cookies)])
        cmd.extend([
            "--user-agent",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--add-header", "Referer:https://www.bilibili.com/",
        ])
    subprocess.run(cmd, check=True)
    if not out.exists():
        candidates = sorted(cache_dir.glob("source*.mp4"))
        if candidates:
            candidates[0].rename(out)
    _write_meta_from_info_json(cache_dir, video_id, source, profile_name=profile_name)
    return out


def _write_meta_from_info_json(
    cache_dir: Path, video_id: str, source: str, *, profile_name: str | None
) -> None:
    """After yt-dlp --write-info-json, distill the verbose info.json into
    a slim meta.json we control, then delete the info.json."""
    info_candidates = sorted(cache_dir.glob("*.info.json"))
    info: dict = {}
    if info_candidates:
        try:
            info = json.loads(info_candidates[0].read_text())
        except Exception:
            info = {}
    meta = {
        "video_id": video_id,
        "source": source,
        "url": _url_for(video_id, source),
        "title": info.get("title") or info.get("fulltitle"),
        "channel": info.get("channel") or info.get("uploader") or info.get("uploader_id"),
        "duration_sec": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile_name": profile_name,
    }
    (cache_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    for p in info_candidates:
        try:
            p.unlink()
        except OSError:
            pass


def _backfill_meta_json(
    cache_dir: Path, video_id: str, source: str, *, profile_name: str | None
) -> None:
    """Best-effort metadata for already-cached entries that predate
    meta.json. Calls yt-dlp --skip-download --dump-json; if that fails
    (video deleted, network), writes a minimal stub so later searches at
    least see the video_id exists."""
    url = _url_for(video_id, source)
    cmd = [str(YTDLP), "--skip-download", "--dump-json", url]
    if source == "youtube" and COOKIES.exists():
        cmd.extend(["--cookies", str(COOKIES)])
    elif source == "bilibili":
        cmd.extend([
            "--user-agent",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--add-header", "Referer:https://www.bilibili.com/",
        ])
    info: dict = {}
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        info = json.loads(proc.stdout.splitlines()[0]) if proc.stdout.strip() else {}
    except Exception:
        info = {}
    meta = {
        "video_id": video_id,
        "source": source,
        "url": url,
        "title": info.get("title") or info.get("fulltitle"),
        "channel": info.get("channel") or info.get("uploader") or info.get("uploader_id"),
        "duration_sec": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile_name": profile_name,
        "backfilled": True,
    }
    (cache_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def _url_for(video_id: str, source: str) -> str:
    if source == "bilibili":
        return f"https://www.bilibili.com/video/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"
