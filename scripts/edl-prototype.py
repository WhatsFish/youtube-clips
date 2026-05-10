#!/usr/bin/env python3
"""
EDL prototype: take 1-3 downloaded YouTube videos + their English VTT
subtitle files, ask Claude (via the `claude` CLI) to filter + select
clips + write Chinese commentary, and emit an EDL JSON.

This is the LLM-heavy core of the youtube-clips pipeline (PLAN.md Phase
2.6 + 2.7). Reads the Profile from Postgres and the prompt template from
`prompts/edl-continuous.v<n>.md` so prompt iteration and channel-style
tweaks don't require code changes.

v4 introduces multi-source: a single EDL can pull B-roll from 1, 2, or
3 source videos. Each shot carries `source_idx` (0, 1, or 2) telling
the renderer which video to clip from. Single-source mode is the same
as multi-source with sources length 1.

Usage:
  source ~/.config/youtube-clips.env

  # Multi-source via discovery JSON (the typical produce.py path):
  .venv/bin/python scripts/edl-prototype.py \\
      --from-discovery /video/youtube-clips/outputs/discovered/<profile>/<slug>.json
      [--profile <name>]   # overrides discovery JSON's profile
      [--prompt-version latest]

  # Single-source manual (back-compat):
  .venv/bin/python scripts/edl-prototype.py <video_id> \\
      --title "..." --channel "..." [--profile ...]

  # Multi-source manual (rare):
  .venv/bin/python scripts/edl-prototype.py \\
      --source <vid>:<title>:<channel> \\
      --source <vid>:<title>:<channel> \\
      [--profile ...]

Inputs (filesystem, per source):
  /video/youtube-clips/raw/<video_id>/source.mp4
  /video/youtube-clips/raw/<video_id>/source.en.vtt

Inputs (DB):
  profiles row matching --profile

Inputs (repo):
  prompts/edl-continuous.v<N>.md  (defaults to latest = v4)

Output (under primary source's video_id):
  /video/youtube-clips/outputs/edl-prototype/<primary_video_id>/edl.json
  /video/youtube-clips/outputs/edl-prototype/<primary_video_id>/prompt.txt   (kept for review)
  /video/youtube-clips/outputs/edl-prototype/<primary_video_id>/raw-claude.txt (kept for debug)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
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

# Map ISO-639-1 → display label used in narration. Add when you add a new
# target_language to a Profile.
_LANG_LABEL = {"zh": "中文", "en": "English"}


@dataclass(frozen=True)
class SourceSpec:
    """One source video for the EDL prompt: id + display metadata + paths."""
    video_id: str
    title: str
    channel: str
    role: str  # "primary" | "supplement"

    @property
    def mp4(self) -> Path:
        return RAW_BASE / self.video_id / "source.mp4"

    @property
    def vtt(self) -> Path | None:
        for name in ("source.en.vtt", "source.en-US.vtt"):
            p = RAW_BASE / self.video_id / name
            if p.exists():
                return p
        return None


# ---- Prompt placeholder builder -------------------------------------------


def _verbal_tics_block(tics: list) -> str:
    return "、".join(f"「{t}」" for t in tics) if tics else "（无频道指定，自由发挥）"


def _forbidden_block(forb: list) -> str:
    return (
        "\n".join(f"      - 「{p}」" for p in forb) if forb else "      （无）"
    )


def _disclaimer_requirement(channel_cfg: dict) -> str:
    disc_zh = channel_cfg.get("disclaimer_zh")
    if channel_cfg.get("must_include_disclaimer") and disc_zh:
        return (
            f"\n  - **收尾必须带免责声明**：在最后一个 shot 的 narration 末尾追加："
            f"「{disc_zh}」"
        )
    return ""


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def build_prompt_kwargs(profile, sources: list[SourceSpec]):
    """Build the placeholder dict for the EDL prompt.

    Produces the union of v3 (single-source) and v4 (multi-source)
    placeholders so the prompt template chooses what it actually needs;
    `str.format` silently drops any extras the active template doesn't
    reference.
    """
    cfg = profile.config or {}
    ch = cfg.get("channel") or {}
    out_cfg = cfg.get("output") or {}

    channel_position = ch.get("channel_position") or (
        f"{out_cfg.get('language', 'zh')}-language commentary channel"
    )
    target_language_label = _LANG_LABEL.get(
        out_cfg.get("language", "zh"), out_cfg.get("language", "zh")
    )
    tone_description = ch.get("tone") or "professional, engaged, opinionated where it earns it"

    # ---- v4: multi-source blocks --------------------------------------
    sources_meta_lines = []
    transcripts_blocks = []
    for i, s in enumerate(sources):
        if not s.vtt:
            sys.exit(f"missing transcript for source {s.video_id} ({s.vtt})")
        if not s.mp4.exists():
            sys.exit(f"missing video for source {s.video_id} ({s.mp4})")
        dur = _ffprobe_duration(s.mp4)
        sources_meta_lines.append(
            f"[source_idx={i}]  role={s.role}\n"
            f"  video_id: {s.video_id}\n"
            f"  title: {s.title}\n"
            f"  channel: {s.channel}\n"
            f"  duration_sec: {int(dur)}"
        )
        entries = parse_vtt(s.vtt)
        transcripts_blocks.append(
            f"=== Source {i} (id={s.video_id}, title={s.title}) ===\n"
            f"{format_transcript(entries)}"
        )
    sources_metadata = "\n\n".join(sources_meta_lines)
    transcripts_block = "\n\n".join(transcripts_blocks)

    # ---- v3 single-source legacy placeholders -------------------------
    # When we have exactly one source, also expose v3's flat fields so
    # an older v3 template invoked via --prompt-version 3 still works.
    primary = sources[0]
    primary_dur = _ffprobe_duration(primary.mp4)
    primary_entries = parse_vtt(primary.vtt) if primary.vtt else []

    return {
        "profile_block": profile.render_block(),
        "channel_position": channel_position,
        "target_language_label": target_language_label,
        "tone_description": tone_description,
        "verbal_tics_example": _verbal_tics_block(ch.get("verbal_tics") or []),
        "forbidden_phrases_block": _forbidden_block(ch.get("forbidden_phrases") or []),
        "disclaimer_requirement": _disclaimer_requirement(ch),
        # v4 (multi-source)
        "sources_metadata": sources_metadata,
        "transcripts_block": transcripts_block,
        # v3 (single-source legacy; harmless when v4 is active)
        "title": primary.title,
        "channel": primary.channel,
        "duration": int(primary_dur),
        "transcript": format_transcript(primary_entries),
    }


# ---- Source resolution ----------------------------------------------------


def _parse_source_flag(spec: str, role: str) -> SourceSpec:
    """Parse a `--source vid:title:channel` triplet."""
    parts = spec.split(":", 2)
    if len(parts) != 3:
        sys.exit(f"--source must be vid:title:channel, got: {spec!r}")
    vid, title, channel = parts
    return SourceSpec(video_id=vid.strip(), title=title.strip(), channel=channel.strip(), role=role)


def _sources_from_discovery(path: Path) -> list[SourceSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    picked = data.get("picked_sources") or []
    if not picked:
        sys.exit(f"discovery JSON has empty picked_sources: {path}")
    out: list[SourceSpec] = []
    for i, p in enumerate(picked):
        out.append(SourceSpec(
            video_id=p["id"],
            title=p.get("title") or "(unknown)",
            channel=p.get("channel") or "(unknown)",
            role=p.get("role") or ("primary" if i == 0 else "supplement"),
        ))
    return out


# ---- Driver ---------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id", nargs="?", help="(legacy) single YouTube video id")
    ap.add_argument("--title", default="(unknown)", help="(legacy) only with positional video_id")
    ap.add_argument("--channel", default="(unknown)", help="(legacy) only with positional video_id")
    ap.add_argument(
        "--source",
        action="append",
        default=[],
        help="vid:title:channel  — repeatable; first becomes primary",
    )
    ap.add_argument(
        "--from-discovery",
        type=Path,
        help="path to a discover-source.py output JSON (preferred multi-source path)",
    )
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

    # Resolve sources: discovery JSON > --source flags > legacy positional.
    if args.from_discovery:
        sources = _sources_from_discovery(args.from_discovery)
    elif args.source:
        sources = [
            _parse_source_flag(s, role="primary" if i == 0 else "supplement")
            for i, s in enumerate(args.source)
        ]
    elif args.video_id:
        sources = [SourceSpec(
            video_id=args.video_id,
            title=args.title,
            channel=args.channel,
            role="primary",
        )]
    else:
        sys.exit("need one of: <video_id> | --source ... | --from-discovery <path>")
    if len(sources) > 3:
        sys.exit(f"max 3 sources, got {len(sources)}")

    primary = sources[0]
    print(f"sources: {len(sources)}  (primary={primary.video_id})")
    for i, s in enumerate(sources):
        print(f"  [{i}] {s.role:<10} {s.video_id}  {s.title[:50]}")

    # Pre-flight check on filesystem for every source.
    for s in sources:
        if not s.mp4.exists():
            sys.exit(f"missing video for source {s.video_id}: {s.mp4}")
        if not s.vtt:
            sys.exit(f"missing transcript for source {s.video_id} (no source.en.vtt)")

    # Load Profile + prompt template.
    profile = fetch_profile(args.profile)
    print(f"profile: {profile.name} (id={profile.id}, active={profile.active})")
    pv = args.prompt_version
    prompt_tmpl = load_prompt(
        "edl-continuous", version=int(pv) if pv != "latest" else "latest"
    )
    print(f"prompt:  {prompt_tmpl.stamp}  ({prompt_tmpl.source_path.name})")

    # Output dir is keyed off the primary source.
    job_dir = OUT_BASE / primary.video_id
    job_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt_tmpl.render(**build_prompt_kwargs(profile, sources))
    (job_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"prompt: {len(prompt)} chars → {job_dir / 'prompt.txt'}")

    print("calling claude...", flush=True)
    t0 = time.monotonic()
    raw = call_claude(prompt)
    elapsed = time.monotonic() - t0
    (job_dir / "raw-claude.txt").write_text(raw, encoding="utf-8")
    print(f"claude returned in {elapsed:.1f}s, {len(raw)} chars")

    edl = extract_json(raw)
    edl["profile_name"] = profile.name
    edl["prompt_template_version"] = prompt_tmpl.stamp
    edl["rendered_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    # Write the canonical sources array into the EDL so the renderer (and
    # the web UI) know which raw mp4s back which shots. This is the v4
    # source of truth — Claude's source_idx fields index into this list.
    edl["sources"] = [
        {
            "video_id": s.video_id,
            "title": s.title,
            "channel": s.channel,
            "role": s.role,
        }
        for s in sources
    ]

    # Default any shot missing source_idx to 0 (primary). Belt-and-
    # suspenders for templates / agents that omit it on single-source.
    for sh in edl.get("shots") or []:
        sh.setdefault("source_idx", 0)

    # Persist Source rows (one per source) + Topic + Job.
    source_db_ids: list[int] = []
    for s in sources:
        sid = db.upsert_source(
            profile_id=profile.id,
            source_platform="youtube",
            external_id=s.video_id,
            url=f"https://www.youtube.com/watch?v={s.video_id}",
            title=s.title if s.title != "(unknown)" else None,
            channel=s.channel if s.channel != "(unknown)" else None,
            duration_sec=int(_ffprobe_duration(s.mp4)),
            source_language="en",
            download_path=str(s.mp4),
            downloaded=True,
        )
        source_db_ids.append(sid)

    topic_title = edl.get("title_zh") or primary.title or primary.video_id
    topic_id = db.upsert_topic(
        profile_id=profile.id,
        title=topic_title,
        description=edl.get("description_zh"),
        keywords=edl.get("tags_zh"),
        status="approved",
        source="agent",
    )
    # Stamp ids into the EDL *before* persisting so jobs.edl_jsonb carries
    # them. `source_id` (singular) stays as the primary's id for backward
    # compat with web/src/lib/jobs.ts's existing single-source join. The
    # full array is in `source_ids`.
    edl["topic_id"] = topic_id
    edl["source_id"] = source_db_ids[0]
    edl["source_ids"] = source_db_ids
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
    print(f"db: topic_id={topic_id} source_ids={source_db_ids} job_id={job_id}")

    # Compact summary.
    print()
    print("=" * 60)
    print(f"  decision: {edl.get('decision')}")
    print(f"  reason:   {edl.get('decision_reason', '')[:100]}")
    if edl.get("decision") == "make":
        shots = edl.get("shots", [])
        print(f"  title_zh: {edl.get('title_zh', '')}")
        print(f"  shots:    {len(shots)}")
        # Per-source shot distribution — at-a-glance signal that the
        # multi-source agent actually *used* the supplements.
        usage = [0] * len(sources)
        for sh in shots:
            idx = sh.get("source_idx", 0)
            if 0 <= idx < len(usage):
                usage[idx] += 1
        print(f"  shot dist: {' '.join(f'src{i}={n}' for i, n in enumerate(usage))}")
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
