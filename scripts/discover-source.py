#!/usr/bin/env python3
"""
Source discovery agent (PLAN.md Phase 2.3).

Given a topic + a Profile, search YouTube for candidate videos, filter
by hard rules (captions present, sensible duration), then ask Claude to
pick the best fit. Produces a discovery JSON with the picked video_id
plus alternatives — feed that id into the existing render pipeline.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/discover-source.py \\
      --topic "Anthropic Claude release"
      [--profile tech-insights-cn]
      [--query "alternative search query"]
      [--max-candidates 15]
      [--published-since 6w | 30d | YYYY-MM-DD]

Output:
  /video/youtube-clips/outputs/discovered/<profile>/<topic-slug>.json
  /video/youtube-clips/outputs/discovered/<profile>/<topic-slug>.prompt.txt
  /video/youtube-clips/outputs/discovered/<profile>/<topic-slug>.raw-claude.txt
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

# Pipeline helpers live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.prompts import load_prompt
from pipeline.profiles import fetch_profile
from pipeline.claude_io import call_claude, extract_json
from pipeline.youtube_search import search, VideoCandidate
from pipeline import db

OUT_BASE = Path("/video/youtube-clips/outputs/discovered")

# Hard-rule filter: a video must fit these to be passed to Claude.
MIN_DURATION_SEC = 4 * 60
MAX_DURATION_SEC = 15 * 60


def slugify(s: str) -> str:
    s = re.sub(r"[^\w一-鿿\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:60] or "topic"


def parse_published_since(spec: str) -> str:
    """Accepts '6w' / '30d' / 'YYYY-MM-DD' → ISO 8601 timestamp."""
    m = re.fullmatch(r"(\d+)([wd])", spec)
    if m:
        n = int(m.group(1))
        delta = dt.timedelta(weeks=n) if m.group(2) == "w" else dt.timedelta(days=n)
        return (dt.datetime.now(dt.timezone.utc) - delta).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    # Try plain date.
    try:
        d = dt.date.fromisoformat(spec)
        return dt.datetime.combine(d, dt.time.min, tzinfo=dt.timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
    except ValueError:
        sys.exit(f"unrecognized --published-since: {spec!r}")


def format_candidates(cands: list[VideoCandidate]) -> str:
    lines = []
    for i, c in enumerate(cands, 1):
        m, s = divmod(c.duration_sec, 60)
        desc = (c.description or "").replace("\n", " ").strip()
        if len(desc) > 120:
            desc = desc[:117] + "…"
        lines.append(
            f"#{i}\n"
            f"  id: {c.id}\n"
            f"  title: {c.title}\n"
            f"  channel: {c.channel}\n"
            f"  duration: {m}:{s:02d}\n"
            f"  views: {c.view_count:,}\n"
            f"  has_captions: {c.has_captions}\n"
            f"  published: {c.published_at[:10]}\n"
            f"  description: {desc}\n"
            f"  url: {c.url}"
        )
    return "\n\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="What this episode is about")
    ap.add_argument("--profile", default="tech-insights-cn")
    ap.add_argument(
        "--query",
        help="YouTube search query (defaults to --topic verbatim)",
    )
    ap.add_argument("--max-candidates", type=int, default=15)
    ap.add_argument(
        "--published-since",
        default="6w",
        help="Recency window: '6w', '30d', or 'YYYY-MM-DD' (default 6w)",
    )
    ap.add_argument("--prompt-version", default="latest")
    args = ap.parse_args()

    profile = fetch_profile(args.profile)
    print(f"profile: {profile.name}")

    query = args.query or args.topic
    cutoff = parse_published_since(args.published_since)
    print(f"search:  {query!r}  since {cutoff[:10]}")

    raw_candidates = search(
        query,
        max_results=args.max_candidates,
        published_after=cutoff,
        video_duration="medium",
    )
    print(f"got:     {len(raw_candidates)} raw candidates")

    # Hard-rule filter.
    filtered = [
        c
        for c in raw_candidates
        if c.has_captions
        and MIN_DURATION_SEC <= c.duration_sec <= MAX_DURATION_SEC
    ]
    print(
        f"filter:  {len(filtered)} pass (captions=true, "
        f"duration {MIN_DURATION_SEC // 60}-{MAX_DURATION_SEC // 60}m)"
    )
    if not filtered:
        sys.exit("no candidates pass the hard-rule filter")

    # Sort by view count desc; cap to top 10 sent to Claude (more is noise).
    filtered.sort(key=lambda c: -c.view_count)
    short_list = filtered[:10]

    pt = load_prompt(
        "source-pick",
        version=int(args.prompt_version)
        if args.prompt_version != "latest"
        else "latest",
    )
    print(f"prompt:  {pt.stamp}")

    prompt = pt.render(
        profile_block=profile.render_block(),
        topic=args.topic,
        candidates=format_candidates(short_list),
    )

    out_dir = OUT_BASE / profile.name
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(args.topic)
    prompt_path = out_dir / f"{slug}.prompt.txt"
    raw_path = out_dir / f"{slug}.raw-claude.txt"
    out_path = out_dir / f"{slug}.json"
    prompt_path.write_text(prompt, encoding="utf-8")

    print(f"calling claude... ({len(prompt)} chars in)")
    raw = call_claude(prompt)
    raw_path.write_text(raw, encoding="utf-8")
    pick = extract_json(raw)

    pick["topic"] = args.topic
    pick["profile_name"] = profile.name
    pick["prompt_template_version"] = pt.stamp
    pick["query"] = query
    pick["published_since"] = cutoff
    pick["candidates_considered"] = len(short_list)
    pick["discovered_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    out_path.write_text(json.dumps(pick, ensure_ascii=False, indent=2), encoding="utf-8")

    # Persist to Postgres so the rest of the pipeline (and the web UI)
    # can find this discovery without scanning the filesystem.
    if pick.get("picked_id"):
        topic_id = db.upsert_topic(
            profile_id=profile.id,
            title=args.topic,
            keywords=[query] if query != args.topic else None,
            status="approved",
            source="agent",
        )
        # Find the picked candidate's full metadata to feed into the source row.
        picked_meta = next(
            (c for c in short_list if c.id == pick["picked_id"]),
            None,
        )
        source_id = db.upsert_source(
            profile_id=profile.id,
            source_platform="youtube",
            external_id=pick["picked_id"],
            url=f"https://www.youtube.com/watch?v={pick['picked_id']}",
            title=pick["picked_title"],
            channel=pick["picked_channel"],
            duration_sec=picked_meta.duration_sec if picked_meta else None,
            source_language="en",
            metadata={
                "view_count": picked_meta.view_count if picked_meta else None,
                "published_at": picked_meta.published_at if picked_meta else None,
                "has_captions": picked_meta.has_captions if picked_meta else None,
                "discovered_for_topic_id": topic_id,
            },
        )
        pick["topic_id"] = topic_id
        pick["source_id"] = source_id
        out_path.write_text(json.dumps(pick, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"db: topic_id={topic_id} source_id={source_id}")

    print()
    print("=" * 60)
    if pick.get("picked_id"):
        print(f"  picked:  {pick['picked_id']}")
        print(f"  title:   {pick['picked_title']}")
        print(f"  channel: {pick['picked_channel']}")
        print(f"  reason:  {pick['reason_zh']}")
        print()
        print(f"  alternatives ({len(pick.get('alternatives', []))}):")
        for a in pick.get("alternatives", []):
            print(f"    - {a['id']}  {a['title'][:60]}")
        print()
        print(f"  saved:   {out_path}")
        print()
        print("  next:")
        print(f"    .venv/bin/yt-dlp --cookies ~/.config/youtube-clips-cookies.txt \\")
        print(f"      --remote-components ejs:github \\")
        print(f"      -f 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]' \\")
        print(f"      --merge-output-format mp4 --write-auto-subs --write-subs \\")
        print(f"      --sub-langs en,en-US --sub-format vtt \\")
        print(f"      -o '/video/youtube-clips/raw/{pick['picked_id']}/source.%(ext)s' \\")
        print(f"      'https://www.youtube.com/watch?v={pick['picked_id']}'")
        print()
        print(f"    .venv/bin/python scripts/edl-prototype.py \\")
        print(f"      --title {json.dumps(pick['picked_title'])} \\")
        print(f"      --channel {json.dumps(pick['picked_channel'])} \\")
        print(f"      -- '{pick['picked_id']}'")
        print()
        print(f"    .venv/bin/python scripts/edl-render.py -- '{pick['picked_id']}'")
    else:
        print(f"  SKIP: {pick.get('skip_reason')}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
