#!/usr/bin/env python3
"""Topic discovery from Chinese RSS feeds (Phase B / TODO #3).

Reads `Profile.config.topic_discovery` for feed_ids + keyword filters,
fetches each rsshub feed, applies cheap keyword pre-filter, then asks
Claude (topic-discover.v1) to pick 5-10 best-fit topics for the channel.
Selected topics land in `topics` table with status='pending' for
operator approval.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/discover-topics.py --profile shanyang-cn

  # Run for every profile that has a topic_discovery block (cron mode)
  .venv/bin/python scripts/discover-topics.py --all

Profile schema (in channel.config.topic_discovery):
  {
    "feed_ids": ["zhihu_hot", "thepaper_featured", ...],
    "include_keywords": ["失业", "工厂", ...],
    "exclude_keywords": ["明星", "综艺", ...]
  }
A profile without `topic_discovery` is silently skipped under --all.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.prompts import load_prompt
from pipeline.profiles import fetch_profile, Profile
from pipeline.claude_io import call_claude, extract_json
from pipeline.news_sources import (
    fetch_feeds,
    fetch_youtube_topic_candidates,
    apply_keyword_filter,
    render_registry_block,
    FeedItem,
)
from pipeline import db


def _fmt_candidates(items: list[FeedItem]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        desc = (it.description or "").strip().replace("\n", " ")
        if len(desc) > 200:
            desc = desc[:197] + "…"
        lines.append(
            f"#{i}\n"
            f"  feed: {it.feed_id}\n"
            f"  title: {it.title}\n"
            f"  description: {desc}\n"
            f"  link: {it.link}\n"
            f"  published: {it.published or '(unknown)'}"
        )
    return "\n\n".join(lines)


def _discover_for_profile(profile: Profile, *, dry_run: bool = False) -> int:
    ch = (profile.config or {}).get("channel") or {}
    cfg = ch.get("topic_discovery") or {}
    if not cfg:
        print(f"[{profile.name}] no topic_discovery config; skipping")
        return 0
    feed_ids = cfg.get("feed_ids") or []
    youtube_queries = cfg.get("youtube_queries") or []
    if not feed_ids and not youtube_queries:
        print(
            f"[{profile.name}] topic_discovery has neither feed_ids nor "
            f"youtube_queries; skipping"
        )
        return 0
    include = cfg.get("include_keywords") or []
    exclude = cfg.get("exclude_keywords") or []
    max_picks = int(cfg.get("max_picks") or 10)

    print(f"\n========= {profile.name} =========")
    if feed_ids:
        print(f"rsshub feeds: {', '.join(feed_ids)}")
    if youtube_queries:
        print(f"youtube queries: {len(youtube_queries)} (" +
              ", ".join(q[:30] for q in youtube_queries[:3]) +
              ("..." if len(youtube_queries) > 3 else "") + ")")
    items: list[FeedItem] = []
    skipped: list[str] = []
    if feed_ids:
        rss_items, rss_skipped = fetch_feeds(feed_ids)
        items.extend(rss_items)
        skipped.extend(rss_skipped)
    if youtube_queries:
        yt_items, yt_skipped = fetch_youtube_topic_candidates(youtube_queries)
        items.extend(yt_items)
        skipped.extend(yt_skipped)
    print(f"fetched {len(items)} items total")
    for s in skipped:
        print(f"  SKIP: {s}")

    filtered = apply_keyword_filter(items, include=include, exclude=exclude)
    print(f"after keyword filter: {len(filtered)} items")
    if not filtered:
        print("nothing survived filter; check include/exclude lists")
        return 0

    # Cap to a sensible number for the prompt — even gpt-class context
    # gets noisy with 80+ items. Surface the diversity by keeping order
    # interleaved across feeds (already true since fetch_feeds appends
    # per-feed).
    short_list = filtered[:40]

    tmpl = load_prompt("topic-discover", version="latest")
    prompt = tmpl.render(
        profile_block=profile.render_block(),
        feed_registry_block=render_registry_block(),
        candidates_block=_fmt_candidates(short_list),
    )
    print(f"calling claude ({tmpl.stamp}; {len(prompt)} chars in)...")
    raw = call_claude(prompt)
    result = extract_json(raw)
    picks = result.get("picks") or []
    if not picks:
        print(f"claude picked nothing: {result.get('skipped_reason') or '(no reason)'}")
        return 0

    print(f"\nclaude picked {len(picks)} topics:")
    for i, p in enumerate(picks):
        print(f"  [{i+1}] {p.get('title')}")
        print(f"      angle: {p.get('suggested_angle')}")
        print(f"      ← {p.get('source_feed')}")

    if dry_run:
        print("\n[dry-run] not writing to DB")
        return len(picks)

    inserted = 0
    for p in picks[:max_picks]:
        # Skip if we already have this title pending or approved for this
        # profile — avoid duplicate inserts when cron runs daily.
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM topics
                WHERE profile_id = %s
                  AND title = %s
                  AND status IN ('pending','approved','done')
                LIMIT 1
                """,
                (profile.id, p.get("title")),
            )
            if cur.fetchone():
                print(f"  (dup) skipped: {p.get('title')}")
                continue
        topic_id = db.upsert_topic(
            profile_id=profile.id,
            title=p.get("title") or "(untitled)",
            description=p.get("description"),
            keywords=[p.get("source_feed")] if p.get("source_feed") else None,
            status="pending",
            source="agent",
        )
        # Attach the richer judge output as metadata so /topics web view
        # can show suggested_angle / source_link.
        meta = {
            "suggested_angle": p.get("suggested_angle"),
            "reasoning": p.get("reasoning"),
            "source_feed": p.get("source_feed"),
            "source_link": p.get("source_link"),
            "discovered_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        with db.cursor() as cur:
            cur.execute(
                "UPDATE topics SET metadata = %s::jsonb WHERE id = %s",
                (json.dumps(meta, ensure_ascii=False), topic_id),
            )
        print(f"  + topic_id={topic_id}  {p.get('title')}")
        inserted += 1
    print(f"\ninserted {inserted} new pending topics for {profile.name}")
    return inserted


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--profile", help="Run for a single profile")
    g.add_argument(
        "--all",
        action="store_true",
        help="Run for every profile with a topic_discovery block",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + filter + judge, but don't write to DB",
    )
    args = ap.parse_args()

    profiles: list[Profile] = []
    if args.profile:
        profiles.append(fetch_profile(args.profile))
    else:
        # Pull all active profiles; filter to those with topic_discovery
        with db.cursor() as cur:
            cur.execute("SELECT name FROM profiles WHERE active = TRUE ORDER BY id")
            names = [r["name"] for r in cur.fetchall()]
        for name in names:
            p = fetch_profile(name)
            if ((p.config or {}).get("channel") or {}).get("topic_discovery"):
                profiles.append(p)

    if not profiles:
        print("no profiles with topic_discovery config")
        return 0

    total = 0
    for p in profiles:
        total += _discover_for_profile(p, dry_run=args.dry_run)
    print(f"\n=== total inserted: {total} topics ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
