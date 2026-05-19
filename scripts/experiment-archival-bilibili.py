#!/usr/bin/env python3
"""Experiment 2: same Jensen scenarios but search Bilibili (not YouTube).

Tests whether Bilibili is a useful archival source for:
- US-tech subjects (Jensen) — likely a lot of 二创 / commentary, less原片
- China-relevant subjects (访华) — likely STRONG, original Chinese coverage
- Visual moments (拿 GPU) — needs to see if B 站 transcripts cover that

Run:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/experiment-archival-bilibili.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.tools.bilibili_tools import search_bilibili, read_bilibili_video


@dataclass
class BiliMatch:
    bvid: str
    url: str
    title: str
    owner: str
    start_sec: float
    end_sec: float
    matched_text: str
    confidence: float


def _dur_to_sec(d) -> int:
    """Bilibili search returns duration as 'MM:SS' or 'HH:MM:SS' string,
    sometimes int seconds. Normalize."""
    if d is None:
        return 0
    if isinstance(d, (int, float)):
        return int(d)
    parts = str(d).split(":")
    try:
        if len(parts) == 1:
            return int(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def filter_candidates(items: list[dict], *, min_views: int = 10_000, min_dur: int = 60):
    """Filter out clear junk before fetching transcripts (cost saver)."""
    out = []
    for it in items:
        if not it.get("bvid") or not it.get("title"):
            continue
        if int(it.get("view_count") or 0) < min_views:
            continue
        if _dur_to_sec(it.get("duration")) < min_dur:
            continue
        title = (it.get("title") or "").lower()
        if any(b in title for b in ["反应", "speedrun", "高能合集"]):
            continue
        out.append(it)
    return out


def find_match_in_transcript(
    lines: list[dict],
    target_desc: str,
    *,
    target_dur_sec: float = 7.0,
) -> tuple[float, float, str, float] | None:
    """Sliding-window fuzzy match. Same logic as YT experiment but on
    Bilibili's transcript_lines [{start,end,text}]."""
    if not lines:
        return None
    target_norm = re.sub(r"\s+", " ", target_desc.lower()).strip()
    items = [(float(l["start"]), str(l.get("text", "")).lower()) for l in lines]
    if not items:
        return None
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
        score = SequenceMatcher(None, target_norm, window).ratio()
        keywords = [t for t in re.findall(r"[一-鿿]{2,}|\w{3,}", target_norm) if t]
        kw_hits = sum(1 for k in keywords if k in window)
        score += 0.10 * kw_hits
        end = items[j - 1][0] if j > i else start + target_dur_sec
        if best is None or score > best[0]:
            best = (score, start, end, window)
    if best is None:
        return None
    s, st, en, tx = best
    return (st, min(en, st + target_dur_sec), tx, min(1.0, s))


def find_archival_clip_bili(
    query: str,
    target_desc: str,
    *,
    target_dur_sec: float = 7.0,
    duration_band: str = "",   # "" = any, "2"=5-10m, "3"=10-30m
    n_candidates: int = 5,
) -> BiliMatch | None:
    print(f"\n[scenario] B站 query={query!r}")
    print(f"           target_desc={target_desc!r}, target_dur={target_dur_sec}s")
    res = search_bilibili(query, max_results=15, duration_band=duration_band)
    items = res.get("results") or []
    if "error" in res:
        print(f"  ✗ search error: {res['error']}")
        return None
    print(f"  bili search: {len(items)} raw hits")
    candidates = filter_candidates(items)
    print(f"  after filter (views≥10k, dur≥60s, no_react_compilation): {len(candidates)}")
    candidates = candidates[:n_candidates]

    best_global = None
    for i, c in enumerate(candidates):
        title = c["title"]
        print(f"  [{i}] {title[:60]!r} · {c['owner']} · {c['duration']}s · {c['view_count']:,}")
        info = read_bilibili_video(c["bvid"], include_transcript=True)
        if "transcript_error" in info or not info.get("transcript_lines"):
            print(f"      no transcript ({info.get('transcript_error','')})")
            continue
        lines = info["transcript_lines"]
        print(f"      {len(lines)} transcript lines")
        m = find_match_in_transcript(lines, target_desc, target_dur_sec=target_dur_sec)
        if not m:
            print(f"      no match window")
            continue
        st, en, tx, conf = m
        print(f"      best: {st:.1f}s-{en:.1f}s  conf={conf:.2f}  text={tx[:80]!r}")
        if best_global is None or conf > best_global[0]:
            best_global = (conf, c, st, en, tx, info["url"])

    if best_global is None:
        print("  ✗ no usable archival match")
        return None
    conf, c, st, en, tx, url = best_global
    print(f"  ✓ PICK: {url} @ {st:.1f}-{en:.1f}s  conf={conf:.2f}")
    return BiliMatch(
        bvid=c["bvid"], url=url, title=c["title"], owner=c["owner"],
        start_sec=st, end_sec=en, matched_text=tx, confidence=conf,
    )


def main():
    scenarios = [
        ("黄仁勋 加州理工 演讲",         "黄仁勋给毕业生关于运气和挫折的建议",                       8.0),
        ("黄仁勋 GTC 主题演讲",          "黄仁勋在台上举起 Blackwell GPU",                             6.0),
        ("黄仁勋 访华 北京",             "黄仁勋在北京跟记者交谈关于中国",                             7.0),
        ("黄仁勋 皮夹克",                "黄仁勋解释为什么总穿皮夹克",                                 6.0),
    ]
    results = []
    for q, d, dur in scenarios:
        m = find_archival_clip_bili(q, d, target_dur_sec=dur)
        results.append(m)
    print("\n" + "=" * 72)
    print("SUMMARY · B 站")
    print("=" * 72)
    for (q, _, _), m in zip(scenarios, results):
        if m:
            print(f"  ✓  {q:<30}  conf={m.confidence:.2f}  → {m.bvid} @ {m.start_sec:.0f}s")
        else:
            print(f"  ✗  {q:<30}  no match")


if __name__ == "__main__":
    main()
