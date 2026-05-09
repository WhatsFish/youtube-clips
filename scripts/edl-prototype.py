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
from pipeline.claude_io import call_claude, extract_json
from pipeline.transcript import parse_vtt, format_transcript
from pipeline import db

RAW_BASE = Path("/video/youtube-clips/raw")
OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")

# ---- Prompt placeholder builder -------------------------------------------

# Map ISO-639-1 → display label used in narration. Add when you add a new
# target_language to a Profile.
_LANG_LABEL = {"zh": "中文", "en": "English"}


def build_prompt_kwargs(profile, *, title, channel, duration, transcript):
    """Pull every placeholder the prompt templates can ask for out of the
    Profile config. Extras are harmless — str.format ignores keys the
    template doesn't reference, so v2 (which only uses {profile_block}
    et al.) still works alongside v3 (which uses the channel-driven set).
    """
    cfg = profile.config or {}
    ch = cfg.get("channel") or {}
    out = cfg.get("output") or {}

    channel_position = ch.get("channel_position") or (
        f"{out.get('language', 'zh')}-language commentary channel"
    )
    target_language_label = _LANG_LABEL.get(out.get("language", "zh"), out.get("language", "zh"))
    tone_description = ch.get("tone") or "professional, engaged, opinionated where it earns it"

    tics = ch.get("verbal_tics") or []
    verbal_tics_example = (
        "、".join(f"「{t}」" for t in tics) if tics else "（无频道指定，自由发挥）"
    )

    forb = ch.get("forbidden_phrases") or []
    forbidden_phrases_block = (
        "\n".join(f"      - 「{p}」" for p in forb)
        if forb
        else "      （无）"
    )

    disc_zh = ch.get("disclaimer_zh")
    if ch.get("must_include_disclaimer") and disc_zh:
        disclaimer_requirement = (
            f"\n  - **收尾必须带免责声明**：在最后一个 shot 的 narration 末尾追加："
            f"「{disc_zh}」"
        )
    else:
        disclaimer_requirement = ""

    return {
        "profile_block": profile.render_block(),
        "title": title,
        "channel": channel,
        "duration": int(duration),
        "transcript": transcript,
        # v3-specific
        "channel_position": channel_position,
        "target_language_label": target_language_label,
        "tone_description": tone_description,
        "verbal_tics_example": verbal_tics_example,
        "forbidden_phrases_block": forbidden_phrases_block,
        "disclaimer_requirement": disclaimer_requirement,
    }


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
        **build_prompt_kwargs(
            profile,
            title=args.title,
            channel=args.channel,
            duration=duration,
            transcript=format_transcript(entries),
        )
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

    # Persist to Postgres. Source row is upserted (creates it if discover
    # didn't run, else refreshes the title/channel from CLI args). Topic
    # row is created on-the-fly using EDL.title_zh as the title — it's
    # the closest thing we have when the user invoked produce.py with a
    # bare --video-id and no preceding discover step.
    source_id = db.upsert_source(
        profile_id=profile.id,
        source_platform="youtube",
        external_id=args.video_id,
        url=f"https://www.youtube.com/watch?v={args.video_id}",
        title=args.title if args.title != "(unknown)" else None,
        channel=args.channel if args.channel != "(unknown)" else None,
        duration_sec=int(duration),
        source_language="en",
        download_path=str(mp4),
        downloaded=True,
    )
    topic_title = edl.get("title_zh") or args.title or args.video_id
    topic_id = db.upsert_topic(
        profile_id=profile.id,
        title=topic_title,
        description=edl.get("description_zh"),
        keywords=edl.get("tags_zh"),
        status="approved",
        source="agent",
    )
    # Stamp ids into the EDL *before* persisting so the stored
    # jobs.edl_jsonb carries them too (the web read path joins via
    # edl_jsonb->>'source_id'). job_id has to go in via a follow-up
    # UPDATE because we don't know it until after the INSERT.
    edl["topic_id"] = topic_id
    edl["source_id"] = source_id
    job_id = db.insert_job(
        topic_id=topic_id,
        profile_id=profile.id,
        edl_jsonb=edl,
        status="planning",
    )
    edl["job_id"] = job_id
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET edl_jsonb = edl_jsonb || jsonb_build_object('job_id', %s::bigint) WHERE id = %s",
            (job_id, job_id),
        )
    edl_path = job_dir / "edl.json"
    edl_path.write_text(
        json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nedl saved: {edl_path}")
    print(f"db: topic_id={topic_id} source_id={source_id} job_id={job_id}")

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
