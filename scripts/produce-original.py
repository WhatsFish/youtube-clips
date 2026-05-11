#!/usr/bin/env python3
"""
Producer-mode end-to-end orchestrator (Phase 2 / Step 2a).

Unlike `produce.py` (which discovers YouTube sources and writes
commentary on top), this script takes a topic + a producer-mode
Profile and generates an original video from scratch:

  1. Stage 1 (outline)   topic → thesis + 5-7 point outline
                         with per-point visual_brief_en
  2. Stage 2 (script)    outline → 8-12 shot narration
                         with per-shot visual_brief_en
  3. Asset acquire       per-shot visual_brief_en → Pexels search
                         → download best matching clip
  4. EDL assemble        shots[i].source_idx = i, source_start_sec = 0
                         sources[i] = {video_id: pexels-XXX, path: ...}
  5. Render              existing edl-render.py (now path-aware)

No YouTube involvement. Operator provides only the topic; system finds
the visuals from the Pexels library (free, CC-equivalent, no attribution
required).

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/produce-original.py \\
      --topic "中国为什么不需要再追 GDP" \\
      --profile editorial-cn

Requires PEXELS_API_KEY in env. Sign up at https://www.pexels.com/api/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
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
from pipeline.pexels import PexelsClient, slugify_query
from pipeline.volcengine import VolcengineClient
from pipeline.exemplars import render_exemplars_block
from pipeline import db, events

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_BASE = Path("/video/youtube-clips/outputs/edl-prototype")
ASSETS_BASE = Path("/video/youtube-clips/assets")

# Char-to-audio-seconds heuristic for narration. zh-CN TTS at +5-15%
# rate runs ~5 chars/sec. We use 4.5 as a slightly conservative lower
# bound when picking Pexels clips so we don't end up with clips shorter
# than the narration they'll back.
CHARS_PER_SEC = 4.5

# Pexels search behaviour. PEXELS_PER_PAGE candidates per shot then we
# pick the first that satisfies the duration constraint. Bumping above
# 10 burns quota faster without improving quality.
PEXELS_PER_PAGE = 8


def slug_for_job(topic: str) -> str:
    """Slugify topic for use as a job directory name (filesystem-safe,
    chronologically sortable). Keeps the topic readable in `ls`."""
    base = re.sub(r"[^\w一-鿿\s-]", "", topic.lower())
    base = re.sub(r"[\s_-]+", "-", base).strip("-")[:50] or "topic"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"orig-{stamp}-{base}"


def _stage(name: str):
    print(f"\n──── {name} {'─' * (54 - len(name))}", flush=True)


def _save_raw(job_dir: Path, name: str, raw: str) -> None:
    """Persist the raw Claude output so a failed JSON parse can be
    inspected after the fact (Claude is stochastic — the same prompt
    re-run typically succeeds, but the original failure mode is lost
    if we don't capture it)."""
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / name).write_text(raw, encoding="utf-8")


def _outline(profile, topic: str, job_dir: Path) -> dict:
    # Profile-level override: channel.outline_prompt_name lets a channel
    # use a brief-specific outline template; falls back to default.
    cfg = (profile.config or {}).get("channel") or {}
    name = cfg.get("outline_prompt_name") or "producer-outline"
    tmpl = load_prompt(name, version="latest")
    block_render = profile.render_block()
    cfg = profile.config or {}
    ch = cfg.get("channel") or {}
    out_cfg = cfg.get("output") or {}
    prompt = tmpl.render(
        profile_block=block_render,
        channel_position=ch.get("channel_position") or "Chinese commentary channel",
        target_language_label="中文",
        tone_description=ch.get("tone") or "natural and engaged",
        topic=topic,
    )
    print(f"prompt: {tmpl.stamp} ({len(prompt)} chars)")
    raw = call_claude(prompt)
    _save_raw(job_dir, "outline.raw-claude.txt", raw)
    data = extract_json(raw)
    return data


def _script(profile, topic: str, outline: dict, job_dir: Path) -> dict:
    # Profile-level override: channel.script_prompt_name (alias prompt_name)
    # lets a channel use a brief-specific script template; falls back to default.
    cfg = (profile.config or {}).get("channel") or {}
    name = cfg.get("script_prompt_name") or cfg.get("prompt_name") or "producer-script"
    tmpl = load_prompt(name, version="latest")
    block_render = profile.render_block()
    cfg = profile.config or {}
    ch = cfg.get("channel") or {}
    out_cfg = cfg.get("output") or {}
    tics = ch.get("verbal_tics") or []
    forb = ch.get("forbidden_phrases") or []
    forbidden_block = (
        "\n".join(f"      - 「{p}」" for p in forb) if forb else "      （无）"
    )
    tics_block = (
        "、".join(f"「{t}」" for t in tics) if tics else "（无频道指定，自由发挥）"
    )
    disc_zh = ch.get("disclaimer_zh")
    disclaimer_req = (
        f"\n  - **收尾必须带免责声明**：在最后一个 shot 的 narration 末尾追加：「{disc_zh}」"
        if ch.get("must_include_disclaimer") and disc_zh
        else ""
    )
    ref_bvids = ((ch.get("style_exemplars") or {}).get("ref_bvids") or [])
    prompt = tmpl.render(
        profile_block=block_render,
        channel_position=ch.get("channel_position") or "Chinese commentary channel",
        target_language_label="中文",
        tone_description=ch.get("tone") or "natural and engaged",
        verbal_tics_example=tics_block,
        forbidden_phrases_block=forbidden_block,
        disclaimer_requirement=disclaimer_req,
        topic=topic,
        outline_block=json.dumps(outline, ensure_ascii=False, indent=2),
        style_exemplars_block=render_exemplars_block(ref_bvids),
    )
    print(f"prompt: {tmpl.stamp} ({len(prompt)} chars)")
    raw = call_claude(prompt)
    _save_raw(job_dir, "script.raw-claude.txt", raw)
    return extract_json(raw)


def _acquire_one_pexels(
    sh: dict,
    i: int,
    query: str,
    assets_dir: Path,
    pexels: PexelsClient,
) -> dict:
    """Try Pexels for this shot. Caller decided this is a Pexels-tier
    shot via asset_strategy. Returns a sources[] entry."""
    est_narr_sec = max(4, math.ceil(len(sh["narration"]) / CHARS_PER_SEC) + 1)
    videos = pexels.search(query, per_page=PEXELS_PER_PAGE, min_duration=est_narr_sec)
    if not videos:
        videos = pexels.search(query, per_page=PEXELS_PER_PAGE, min_duration=2)
    if not videos:
        sys.exit(
            f"shot {i}: pexels returned no candidates for query={query!r}. "
            f"Try a more concrete English visual_brief_en or asset_strategy='ai'."
        )
    pick = videos[0]
    target = assets_dir / f"clip-{i:02d}-pexels-{slugify_query(query)}.mp4"
    print(f"  s{i:02d} pexels:{pick.id} ({pick.duration_sec}s) ← {query!r}")
    pexels.download(pick, target)
    return {
        "video_id": f"pexels-{pick.id}",
        "title": query,
        "channel": "Pexels stock",
        "role": "primary" if i == 0 else "supplement",
        "path": str(target),
        "duration_sec": pick.duration_sec,
        "page_url": pick.page_url,
        "asset_strategy": "pexels",
    }


def _acquire_one_ai(
    sh: dict,
    i: int,
    query: str,
    assets_dir: Path,
    volc: VolcengineClient,
) -> dict:
    """Generate this shot's clip via Doubao Seedance. Use 10s default —
    most narration lines fit under that, and longer means more flexibility
    for tpad-free playback.
    """
    target = assets_dir / f"clip-{i:02d}-ai-{slugify_query(query)}.mp4"
    print(f"  s{i:02d} doubao generating ({query!r}) — this takes ~60s...")
    t0 = time.monotonic()
    result = volc.generate(query, target, duration_sec=10, resolution="720p")
    print(
        f"  s{i:02d} doubao:{result.task_id} ({result.duration_sec:.0f}s clip) "
        f"in {time.monotonic()-t0:.0f}s wall"
    )
    return {
        "video_id": f"doubao-{result.task_id}",
        "title": query,
        "channel": "Doubao Seedance",
        "role": "primary" if i == 0 else "supplement",
        "path": str(target),
        "duration_sec": result.duration_sec,
        "page_url": None,
        "asset_strategy": "ai",
    }


def _acquire_assets(
    shots: list[dict],
    assets_dir: Path,
    pexels: PexelsClient,
    volc: VolcengineClient | None,
    *,
    global_strategy: str = "hybrid",
    run_id: int | None = None,
) -> list[dict]:
    """Route each shot to Pexels or AI generation based on the agent's
    per-shot `asset_strategy` (and the global override).

    `global_strategy`:
      - `pexels`  → force all shots to Pexels regardless of what agent picked
      - `ai`      → force all shots through Doubao (expensive; use only when
                    debugging AI tier or doing a fully-AI sample render)
      - `hybrid`  → respect each shot's `asset_strategy` (default)
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    sources: list[dict] = []
    for i, sh in enumerate(shots):
        query = (sh.get("visual_brief_en") or "").strip()
        if not query:
            sys.exit(f"shot {i}: missing visual_brief_en")
        shot_strategy = (sh.get("asset_strategy") or "pexels").lower()
        if global_strategy == "pexels":
            chosen = "pexels"
        elif global_strategy == "ai":
            chosen = "ai"
        else:  # hybrid
            chosen = shot_strategy
        events.emit(run_id, "acquire", "start",
                    f"s{i:02d} {chosen}: {query[:60]}",
                    shot_idx=i, strategy=chosen, query=query)
        if chosen == "ai":
            if volc is None:
                print(
                    f"  s{i:02d} agent asked for AI but VOLC_ARK_API_KEY not set — "
                    f"falling back to pexels"
                )
                src = _acquire_one_pexels(sh, i, query, assets_dir, pexels)
                events.emit(run_id, "acquire", "done",
                            f"s{i:02d} fallback pexels:{src.get('video_id')}",
                            shot_idx=i, video_id=src.get("video_id"))
            else:
                src = _acquire_one_ai(sh, i, query, assets_dir, volc)
                events.emit(run_id, "acquire", "done",
                            f"s{i:02d} doubao:{src.get('video_id')}",
                            shot_idx=i, video_id=src.get("video_id"))
        else:
            src = _acquire_one_pexels(sh, i, query, assets_dir, pexels)
            events.emit(run_id, "acquire", "done",
                        f"s{i:02d} pexels:{src.get('video_id')}",
                        shot_idx=i, video_id=src.get("video_id"))
        sources.append(src)
    return sources


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="What this video is about")
    ap.add_argument("--profile", required=True, help="Profile name (must be production_mode=producer)")
    ap.add_argument(
        "--asset-strategy",
        choices=["pexels", "ai", "hybrid"],
        default="hybrid",
        help=(
            "How to source per-shot visuals. 'hybrid' (default) respects "
            "the per-shot strategy the script agent chose. 'pexels' forces "
            "all-stock. 'ai' forces all-Doubao (expensive, ~¥1-2 per 5s)."
        ),
    )
    args = ap.parse_args()

    overall_t0 = time.monotonic()

    # 0. Profile guardrail — only producer-mode Profiles drive this script.
    profile = fetch_profile(args.profile)
    mode = ((profile.config or {}).get("channel") or {}).get("production_mode")
    if mode != "producer":
        sys.exit(
            f"Profile {profile.name!r} has production_mode={mode!r}; "
            f"this script only runs on producer-mode Profiles. "
            f"For commentary/synthesis, use produce.py."
        )
    print(f"profile: {profile.name} (mode={mode})")

    slug = slug_for_job(args.topic)
    job_dir = OUT_BASE / slug
    job_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = ASSETS_BASE / slug

    run_id = events.start_run(
        profile_id=profile.id,
        kind="producer",
        topic_title=args.topic,
        url_slug=slug,
    )
    events.register_atexit(run_id)
    print(f"run_id: {run_id}")

    # 1. Outline.
    _stage("outline")
    events.emit(run_id, "outline", "start", "Stage 1: thesis + outline")
    outline = _outline(profile, args.topic, job_dir)
    (job_dir / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if outline.get("decision") == "skip":
        reason = outline.get("decision_reason_zh") or "outline skip"
        print(f"outline returned skip: {reason}")
        events.emit(run_id, "outline", "skip", reason)
        events.finish_run(run_id, "skipped", reason)
        return 1
    print(f"thesis: {outline.get('thesis_zh')}")
    print(f"outline points: {len(outline.get('outline', []))}")
    events.emit(run_id, "outline", "done",
                outline.get("thesis_zh"),
                points=len(outline.get("outline", [])))

    # 2. Script.
    _stage("script")
    events.emit(run_id, "script", "start", "Stage 2: shot narration")
    script = _script(profile, args.topic, outline, job_dir)
    (job_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if script.get("decision") == "skip":
        reason = script.get("decision_reason") or "script skip"
        print(f"script returned skip: {reason}")
        events.emit(run_id, "script", "skip", reason)
        events.finish_run(run_id, "skipped", reason)
        return 1
    shots = script.get("shots") or []
    if not shots:
        events.emit(run_id, "script", "fail", "script returned no shots")
        events.finish_run(run_id, "failed", "script returned no shots")
        sys.exit("script returned no shots")
    print(f"shots: {len(shots)}")
    events.emit(run_id, "script", "done", f"{len(shots)} shots",
                shots=len(shots),
                voice=script.get("voice"),
                pacing=(script.get("pacing") or {}).get("tier"))

    # 3. Acquire assets — Pexels stock and/or Doubao AI per the agent's
    #    per-shot decision (overridable via --asset-strategy).
    _stage(f"assets ({args.asset_strategy})")
    events.emit(run_id, "assets", "start",
                f"strategy={args.asset_strategy}, {len(shots)} shots")
    pexels = PexelsClient.from_env()
    try:
        volc = VolcengineClient()
    except RuntimeError as e:
        # AI key missing — that's fine if the strategy doesn't need it.
        # If hybrid and any shot asked for AI, _acquire_assets falls
        # back to pexels per-shot (and warns).
        if args.asset_strategy == "ai":
            events.emit(run_id, "assets", "fail", str(e))
            events.finish_run(run_id, "failed", str(e))
            sys.exit(f"--asset-strategy ai requires VOLC_ARK_API_KEY: {e}")
        volc = None
    sources = _acquire_assets(
        shots, assets_dir, pexels, volc,
        global_strategy=args.asset_strategy,
        run_id=run_id,
    )
    events.emit(run_id, "assets", "done", f"{len(sources)} sources ready")

    # 4. Assemble EDL. Each shot points at its own freshly-downloaded
    # clip via source_idx; source_start_sec stays 0 (each clip plays
    # from its beginning).
    edl_shots = []
    for i, sh in enumerate(shots):
        edl_shots.append({
            "narration": sh["narration"],
            "source_idx": i,
            "source_start_sec": 0,
            "outline_ref": sh.get("outline_ref"),
            "purpose": sh.get("purpose"),
            "visual_brief_en": sh.get("visual_brief_en"),
        })

    edl = {
        "decision": "make",
        "production_mode": "producer",
        # Web URL routing key. Commentary/synthesis modes inherit the
        # primary source's external_id (a YouTube video id) which
        # doubles as the on-disk directory name; producer mode has no
        # YouTube id, so we stamp the human-readable job slug here and
        # the web layer prefers this over sources[0].external_id.
        "url_slug": slug,
        "thesis_zh": script.get("thesis_zh") or outline.get("thesis_zh"),
        "title_zh": script.get("title_zh"),
        "description_zh": script.get("description_zh"),
        "tags_zh": script.get("tags_zh") or [],
        "pacing": script.get("pacing") or {"tier": "normal", "inter_shot_pause_sec": 0.8, "reason_zh": "default"},
        "bgm": script.get("bgm") or {"mode": "off", "mood": "neutral", "reason_zh": "default"},
        "sources": sources,
        "shots": edl_shots,
        "profile_name": profile.name,
        "prompt_template_version": "producer-script.v1",
        "rendered_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    # Voice/rate_pct fallback chain — same as edl-prototype: EDL > Profile > renderer default
    _po = (profile.config or {}).get("output") or {}
    voice_from_script = script.get("voice")
    rate_from_script = script.get("rate_pct")
    if voice_from_script:
        edl["voice"] = voice_from_script
    elif _po.get("tts_voice"):
        edl["voice"] = _po["tts_voice"]
    if rate_from_script is not None:
        edl["rate_pct"] = rate_from_script
    elif _po.get("tts_rate_pct") is not None:
        edl["rate_pct"] = _po["tts_rate_pct"]

    # 5. Persist Topic + Job + Source rows.
    # `external_id` for producer sources is `pexels-<id>` — not a YouTube
    # id but treated the same by the DB schema (source_platform="pexels").
    source_db_ids: list[int] = []
    for s in sources:
        sid = db.upsert_source(
            profile_id=profile.id,
            source_platform="pexels",
            external_id=s["video_id"],
            url=s.get("page_url") or f"https://www.pexels.com/video/{s['video_id'].split('-')[-1]}/",
            title=s.get("title"),
            channel=s.get("channel"),
            duration_sec=s.get("duration_sec"),
            source_language="en",
            download_path=s.get("path"),
            downloaded=True,
        )
        source_db_ids.append(sid)
    topic_id = db.upsert_topic(
        profile_id=profile.id,
        title=args.topic,
        description=edl.get("description_zh"),
        keywords=edl.get("tags_zh"),
        status="approved",
        source="human",
    )
    edl["topic_id"] = topic_id
    edl["source_id"] = source_db_ids[0] if source_db_ids else None
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

    events.attach_topic(run_id, topic_id)
    events.attach_job(run_id, job_id)

    (job_dir / "edl.json").write_text(
        json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"edl saved: {job_dir / 'edl.json'}")
    print(f"db: topic_id={topic_id} source_ids={source_db_ids} job_id={job_id}")
    events.emit(run_id, "edl_persist", "done",
                f"job_id={job_id} sources={len(source_db_ids)}",
                job_id=job_id, topic_id=topic_id)

    # 6. Render.
    _stage("render")
    events.emit(run_id, "render", "start", f"{len(shots)} shots")
    cmd = [
        str(PROJECT_ROOT / ".venv" / "bin" / "python"),
        str(PROJECT_ROOT / "scripts" / "edl-render.py"),
        "--run-id", str(run_id or ""),
        "--", slug,
    ]
    subprocess.run(cmd, check=True)
    events.emit(run_id, "render", "done", "render.mp4 written")

    elapsed = time.monotonic() - overall_t0
    render_path = job_dir / "render.mp4"
    print()
    print("=" * 60)
    print(f"  produce-original complete: {slug}")
    print(f"  shots:  {len(shots)}")
    print(f"  edl:    {job_dir / 'edl.json'}")
    print(f"  render: {render_path}")
    print(f"  total:  {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(
        f"  view:   https://ai-native.japaneast.cloudapp.azure.com/youtube-clips/"
        f"jobs/{slug}"
    )
    print("=" * 60)
    events.finish_run(run_id, "completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
