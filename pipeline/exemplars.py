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

Two modes:
- **Static** (default): use the BV ids in `Profile.channel.style_exemplars.ref_bvids`.
- **Dynamic per topic**: when `Profile.channel.style_exemplars.dynamic = true`,
  search Bilibili for same-topic viral videos at produce time, harvest the
  top N, return their BV ids. Falls back to static `ref_bvids` if dynamic
  returns fewer than 2 results. See `harvest_for_topic()`.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
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


def _parse_duration(s: str) -> int:
    """Bilibili search API returns duration as 'MM:SS' (or 'H:MM:SS'). Return seconds."""
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0
    if len(nums) == 2:
        m, s = nums
        return m * 60 + s
    if len(nums) == 3:
        h, m, s = nums
        return h * 3600 + m * 60 + s
    return 0


def _harvest_one_bv(bvid: str, client) -> bool:
    """Harvest a single BV's metadata + transcript into the per-BV JSON cache.

    Returns True if the cache file exists at the end (success or already
    present), False if harvest failed and we have nothing.
    """
    cache_path = EXEMPLARS_BASE / f"{bvid}.json"
    if cache_path.exists():
        return True
    EXEMPLARS_BASE.mkdir(parents=True, exist_ok=True)
    # Import here so this module stays importable when pipeline.bilibili
    # isn't on the path (e.g. unit tests for render_exemplars_block alone).
    from .bilibili import format_transcript_lines
    try:
        info = client.video_info(bvid)
        lines = client.transcript(info)
    except Exception as e:
        print(f"  [exemplars] harvest {bvid} failed: {e}", file=sys.stderr)
        return False
    per_video = {
        "bvid": info.bvid,
        "url": info.url,
        "title": info.title,
        "desc": info.desc,
        "owner": info.owner,
        "duration_sec": info.duration,
        "pubdate": info.pubdate,
        "stat": info.stat,
        "tname": info.tname,
        "transcript_lines": [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in lines
        ],
        "transcript_text": format_transcript_lines(lines),
        "harvested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    cache_path.write_text(
        json.dumps(per_video, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def _derive_search_queries(topic_title: str, profile) -> list[str]:
    """Use Claude to extract 2-4 Bilibili-friendly search queries from a
    narrative topic title. Topic titles like 「马斯洛塌方：当AI能满足前四层」
    don't surface anything via literal search — they're crafted hooks, not
    keyword sets. We ask Claude to pull out the underlying topic domain
    (e.g. 「AI 失业」「中年 意义感」) which DO match viral 同题材 videos.

    Returns the original title as the first query (no-op for cases where
    the title is already a good search) plus Claude-derived alternatives.
    Best-effort: any failure falls back to [topic_title] only.
    """
    from .claude_io import call_claude, extract_json
    channel = ((profile.config or {}).get("channel") or {})
    position = channel.get("channel_position") or "Chinese commentary channel"
    prompt = f"""你是 B 站搜索助手。给定一个中文视频选题标题（叙事性、有钩子），
为它生成 3 个 Bilibili 搜索关键词组合，能搜到**同题材**的其他视频（学习风格用）。

要求：
- 每个 query 5-12 个汉字，**就是关键词组合，不是完整句子**
- 抽出标题里的核心主题（场景 / 人群 / 现象），扔掉修饰和悬念
- 三个 query 角度不同：一个偏现象、一个偏人群、一个偏关键词
- 不要含标点

频道定位：{position}

选题标题：{topic_title}

输出格式（纯 JSON，包在 ```json 块里）：
```json
{{"queries": ["...", "...", "..."]}}
```"""
    try:
        raw = call_claude(prompt, timeout=60)
        data = extract_json(raw)
        qs = [q for q in (data.get("queries") or []) if q and isinstance(q, str)]
        return qs[:4]
    except Exception as e:
        print(f"  [exemplars] query derivation failed: {e}", file=sys.stderr)
        return []


def harvest_for_topic(
    topic_title: str,
    profile,
    *,
    target_count: int = 3,
    min_views: int = 100_000,
    duration_band: str | None = "3",  # 10-30 min videos
    max_age_days: int | None = 730,   # exemplars within last 2 years
) -> list[str]:
    """Return up to `target_count` BV ids to use as exemplars for `topic_title`.

    If `Profile.channel.style_exemplars.dynamic` is truthy, do a Bilibili
    search keyed off the topic title, filter by views / duration / age,
    harvest the top N into the on-disk cache, and return their BV ids.

    Otherwise (or when dynamic returns too few), fall back to the
    Profile's static `ref_bvids`. Always returns a non-None list — never
    breaks the call site if Bilibili is unreachable.
    """
    cfg = ((profile.config or {}).get("channel") or {}).get("style_exemplars") or {}
    static_bvids: list[str] = cfg.get("ref_bvids") or []
    dynamic_cfg = cfg.get("dynamic")
    if not dynamic_cfg:
        return static_bvids
    # Allow either `"dynamic": true` (use defaults) or `"dynamic": {...}` (overrides).
    if isinstance(dynamic_cfg, dict):
        target_count = int(dynamic_cfg.get("target_count") or target_count)
        min_views = int(dynamic_cfg.get("min_views") or min_views)
        duration_band = dynamic_cfg.get("duration_band", duration_band)
        max_age_days = dynamic_cfg.get("max_age_days", max_age_days)

    from .bilibili import BilibiliClient
    try:
        client = BilibiliClient()
    except Exception as e:
        print(f"  [exemplars] BilibiliClient init failed; using static: {e}",
              file=sys.stderr)
        return static_bvids

    # Build a query list. Start with Claude-derived keyword combos (the
    # original narrative title rarely matches anything literally), then
    # the title itself as a longshot fallback.
    queries = _derive_search_queries(topic_title, profile)
    if topic_title and topic_title not in queries:
        queries.append(topic_title)
    print(f"  [exemplars] search queries: {queries}")
    seen_bvids: set[str] = set()
    items: list[dict] = []
    for q in queries:
        try:
            hits = client.search(
                q, max_results=30,
                duration_band=duration_band, order="click",
            )
        except Exception as e:
            print(f"  [exemplars] search {q!r} failed: {e}", file=sys.stderr)
            continue
        for h in hits:
            bvid = h.get("bvid")
            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                items.append(h)
        time.sleep(0.2)
    if not items:
        print("  [exemplars] no search hits; using static")
        return static_bvids

    now_ts = time.time()
    age_cutoff_ts = now_ts - max_age_days * 86400 if max_age_days else 0
    picked: list[dict] = []
    for it in items:
        views = int(it.get("play") or 0)
        if views < min_views:
            continue
        pub = int(it.get("pubdate") or 0)
        if age_cutoff_ts and pub and pub < age_cutoff_ts:
            continue
        dur_str = it.get("duration") or ""
        if duration_band and _parse_duration(dur_str) > 60 * 60:
            # extreme outliers — Bilibili's `duration=3` band caps at 30min
            # but the API sometimes lets longer ones through; cap defensively.
            continue
        picked.append(it)
        if len(picked) >= target_count:
            break

    if len(picked) < 2:
        print(
            f"  [exemplars] only {len(picked)} candidate(s) passed filters; "
            f"using static instead"
        )
        return static_bvids

    dynamic_bvids: list[str] = []
    for it in picked:
        bvid = it.get("bvid")
        if not bvid:
            continue
        ok = _harvest_one_bv(bvid, client)
        if ok:
            dynamic_bvids.append(bvid)
            print(
                f"  [exemplars] + {bvid}  views={int(it.get('play') or 0):,}"
                f"  {it.get('title','')[:50]}"
            )
            # Polite spacing between API calls
            time.sleep(0.3)
        else:
            print(f"  [exemplars] - {bvid} failed harvest, skipping")

    if len(dynamic_bvids) < 2:
        print("  [exemplars] dynamic harvest yielded < 2 usable; using static")
        return static_bvids
    return dynamic_bvids


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
