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
from pipeline import db, events

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
    ap.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Run id to attach events to (set by produce.py)",
    )
    args = ap.parse_args()
    run_id = args.run_id

    profile = fetch_profile(args.profile)
    print(f"profile: {profile.name}")
    events.emit(run_id, "discover_search", "start", f"query={args.topic!r}")

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
    events.emit(run_id, "discover_search", "done",
                f"{len(raw_candidates)} candidates from YouTube",
                candidates=len(raw_candidates))

    # Hard-rule filter. has_captions in the YT Data API only flags *manual*
    # captions; auto-captions are virtually universal on English YouTube and
    # yt-dlp picks them up via --write-auto-subs. Filtering on has_captions
    # therefore over-rejects (especially for non-tech genres where channels
    # don't upload manual transcripts). Filter on duration only here; the
    # download stage will surface a clean error if a picked video genuinely
    # has zero captions of any kind.
    filtered = [
        c
        for c in raw_candidates
        if MIN_DURATION_SEC <= c.duration_sec <= MAX_DURATION_SEC
    ]
    print(
        f"filter:  {len(filtered)} pass "
        f"(duration {MIN_DURATION_SEC // 60}-{MAX_DURATION_SEC // 60}m; "
        f"with-manual-captions: {sum(1 for c in filtered if c.has_captions)})"
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
    events.emit(run_id, "discover_pick", "start",
                f"asking claude to pick from {len(short_list)} candidates")
    raw = call_claude(prompt)
    raw_path.write_text(raw, encoding="utf-8")
    pick = extract_json(raw)

    # Normalize v1 (single picked_id) → v2 (picked_sources[]) shape so the
    # rest of the pipeline only sees one schema. v1 kept available as fallback.
    pick = _normalize_pick_schema(pick)

    pick["topic"] = args.topic
    pick["profile_name"] = profile.name
    pick["prompt_template_version"] = pt.stamp
    pick["query"] = query
    pick["published_since"] = cutoff
    pick["candidates_considered"] = len(short_list)
    pick["discovered_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    out_path.write_text(json.dumps(pick, ensure_ascii=False, indent=2), encoding="utf-8")

    picked = pick.get("picked_sources") or []

    # Persist to Postgres so the rest of the pipeline (and the web UI)
    # can find this discovery without scanning the filesystem. We write
    # one Source row per picked video; the primary's id stays in the
    # legacy `source_id` field on the discovery JSON (single-source
    # backward compat for tooling), and the full list is in source_ids.
    if picked:
        topic_id = db.upsert_topic(
            profile_id=profile.id,
            title=args.topic,
            keywords=[query] if query != args.topic else None,
            status="approved",
            source="agent",
        )
        source_ids: list[int] = []
        for ps in picked:
            picked_meta = next((c for c in short_list if c.id == ps["id"]), None)
            sid = db.upsert_source(
                profile_id=profile.id,
                source_platform="youtube",
                external_id=ps["id"],
                url=f"https://www.youtube.com/watch?v={ps['id']}",
                title=ps.get("title"),
                channel=ps.get("channel"),
                duration_sec=picked_meta.duration_sec if picked_meta else None,
                source_language="en",
                metadata={
                    "view_count": picked_meta.view_count if picked_meta else None,
                    "published_at": picked_meta.published_at if picked_meta else None,
                    "has_captions": picked_meta.has_captions if picked_meta else None,
                    "role": ps.get("role"),
                    "discovered_for_topic_id": topic_id,
                },
            )
            ps["source_id"] = sid
            source_ids.append(sid)
        pick["topic_id"] = topic_id
        pick["source_ids"] = source_ids
        # Legacy field: primary source_id, kept so single-source tooling
        # and downstream backward-compat paths still work.
        pick["source_id"] = source_ids[0]
        pick["picked_id"] = picked[0]["id"]
        pick["picked_title"] = picked[0].get("title")
        pick["picked_channel"] = picked[0].get("channel")
        out_path.write_text(json.dumps(pick, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"db: topic_id={topic_id} source_ids={source_ids}")
        events.attach_topic(run_id, topic_id)
        events.emit(run_id, "discover_pick", "done",
                    f"picked {len(picked)}: " + ", ".join(p["id"] for p in picked),
                    picked=[p["id"] for p in picked],
                    topic_id=topic_id, source_ids=source_ids)
    else:
        events.emit(run_id, "discover_pick", "skip", pick.get("skip_reason"))

    print()
    print("=" * 60)
    if picked:
        print(f"  picked {len(picked)} source{'s' if len(picked) > 1 else ''}:")
        for i, ps in enumerate(picked):
            tag = "primary  " if i == 0 else "supplement"
            print(f"    [{i}] {tag}  {ps['id']}  {ps.get('title','')[:55]}")
            if ps.get("what_it_brings_zh"):
                print(f"        贡献: {ps['what_it_brings_zh']}")
        print(f"  reason:  {pick.get('reason_zh','')}")
        print()
        print(f"  alternatives ({len(pick.get('alternatives', []))}):")
        for a in pick.get("alternatives", []):
            print(f"    - {a['id']}  {a['title'][:60]}")
        print()
        print(f"  saved:   {out_path}")
        print()
        print("  next: produce.py orchestrates download(s) + EDL + render")
        print(f"        (or edl-prototype.py --from-discovery {out_path})")
    else:
        print(f"  SKIP: {pick.get('skip_reason')}")
    print("=" * 60)
    return 0


def _normalize_pick_schema(pick: dict) -> dict:
    """Coerce v1 (single picked_id) and v2 (picked_sources[]) outputs into a
    unified shape. The rest of the pipeline only ever sees `picked_sources`.

    v1 input shape: {"picked_id", "picked_title", "picked_channel", ...}
    v2 input shape: {"picked_sources": [{"id","title","channel","role"}], ...}
    """
    if pick.get("picked_sources"):
        # v2 — already in target shape. Ensure the first one is marked primary.
        srcs = pick["picked_sources"]
        for i, s in enumerate(srcs):
            s.setdefault("role", "primary" if i == 0 else "supplement")
        return pick
    if pick.get("picked_id"):
        # v1 — wrap the single pick.
        pick["picked_sources"] = [{
            "id": pick["picked_id"],
            "title": pick.get("picked_title"),
            "channel": pick.get("picked_channel"),
            "role": "primary",
            "what_it_brings_zh": pick.get("reason_zh"),
        }]
        return pick
    # No pick (skip case) — leave alone; caller checks picked_sources truthiness.
    pick.setdefault("picked_sources", [])
    return pick


if __name__ == "__main__":
    sys.exit(main())
