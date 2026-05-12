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
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Pipeline helpers live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.prompts import load_prompt
from pipeline.profiles import fetch_profile
from pipeline.claude_io import call_claude, extract_json, DEFAULT_MCP_CONFIG, DEFAULT_MCP_TOOLS
from pipeline.pexels import PexelsClient, slugify_query
from pipeline.volcengine import VolcengineClient
from pipeline.cogvideox import CogVideoXClient
from pipeline.cogview import CogViewClient
from pipeline.exemplars import render_exemplars_block, harvest_for_topic
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
    # Dynamic exemplars: when the Profile opts in via channel.style_exemplars.dynamic,
    # search Bilibili for same-topic viral videos at produce time. Falls back to
    # the static ref_bvids list if search returns too few.
    ref_bvids = harvest_for_topic(topic, profile)
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
    # Stage 2 script writer gets MCP tool access (search_bilibili,
    # read_bilibili_video, fetch_url, fetch_rss_feed) when the template
    # version supports it — v2+ documents the tools and instructs the
    # agent to use them; v1 is text-only. Auto-detect by template stamp.
    use_tools = tmpl.version >= 2 if isinstance(tmpl.version, int) else False
    print(
        f"prompt: {tmpl.stamp} ({len(prompt)} chars)"
        + ("  [tools: MCP enabled]" if use_tools else "")
    )
    if use_tools:
        raw = call_claude(
            prompt,
            timeout=900,
            max_turns=12,
            mcp_config=DEFAULT_MCP_CONFIG,
            mcp_tools=DEFAULT_MCP_TOOLS,
        )
    else:
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


def _strip_audio(mp4: Path) -> None:
    """Remove the audio track from an mp4 in place.

    Doubao Seedance auto-generates an AI ambient/voice track that leaks
    under the narration and makes Doubao-backed shots audibly louder
    than Pexels-backed (silent) shots — operator perceives it as
    "narration is loud-quiet-loud-quiet" across the timeline. We strip
    Doubao audio at acquire time so renderer always sees silent sources,
    same code path as Pexels stock.
    """
    tmp = mp4.with_suffix(".muxed.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(mp4),
            "-c:v", "copy", "-an",
            str(tmp),
        ],
        check=True,
    )
    tmp.replace(mp4)


def _doubao_duration_for_shot(narration: str | None) -> int:
    """Right-size the Doubao clip to the narration's actual length.

    Old behavior was a fixed 10s clip regardless of shot. That overshoots
    most shots (narration averages 5-8s @ 4.5 chars/sec), wasting per-sec
    pricing. We now request narr_dur + 1s headroom, clamped to Seedance's
    accepted band [5, 10]. tpad fills any leftover at render time.
    """
    chars = len((narration or "").strip())
    est = math.ceil(chars / CHARS_PER_SEC) + 1
    return max(5, min(10, est))


def _acquire_one_ai(
    sh: dict,
    i: int,
    query: str,
    assets_dir: Path,
    volc,
    run_id: int | None = None,
) -> dict:
    """Generate this shot's clip via the AI video tier — either
    CogVideoX-Flash (free, preferred) or Doubao Seedance (paid fallback).
    Both clients expose the same `.generate(prompt, target, duration_sec,
    resolution, run_id, shot_idx)` signature so the dispatch is opaque.

    Cost params:
    - Doubao 480p: ~half the per-sec cost of 720p. CogVideoX-Flash is
      currently free regardless of resolution; we still pass duration so
      the request stays right-sized.
    - Duration sized to shot's narration (typically 5-7s), clamped to
      vendor-accepted band (Doubao [5,10], CogVideoX {5,10}).

    Audio is stripped post-download — see _strip_audio comment.
    """
    target = assets_dir / f"clip-{i:02d}-ai-{slugify_query(query)}.mp4"
    dur = _doubao_duration_for_shot(sh.get("narration"))
    vendor = volc.__class__.__name__.replace("Client", "").lower()
    print(
        f"  s{i:02d} {vendor} generating ({query!r}) — {dur}s, takes ~60s..."
    )
    t0 = time.monotonic()
    result = volc.generate(
        query, target, duration_sec=dur, resolution="480p",
        run_id=run_id, shot_idx=i,
    )
    _strip_audio(target)
    # CogVideoX response doesn't echo duration; ffprobe the local file.
    actual_dur = result.duration_sec or _ffprobe_seconds(target)
    print(
        f"  s{i:02d} {vendor}:{result.task_id} ({actual_dur:.0f}s clip, muted) "
        f"in {time.monotonic()-t0:.0f}s wall"
    )
    channel_label = "CogVideoX Flash" if vendor == "cogvideox" else "Doubao Seedance"
    return {
        "video_id": f"{vendor}-{result.task_id}",
        "title": query,
        "channel": channel_label,
        "role": "primary" if i == 0 else "supplement",
        "path": str(target),
        "duration_sec": actual_dur,
        "page_url": None,
        "asset_strategy": "ai",
    }


def _kenburns_image_to_mp4(
    image_path: Path, out_path: Path, duration_sec: float,
) -> Path:
    """Animate a still image to an mp4 using ffmpeg zoompan (Ken Burns).

    Slow zoom-in over the clip duration; output 1920x1080 30fps, no audio.
    Used to turn a single AI-generated still into a B-roll clip the
    concat path can splice in just like a Doubao/Pexels video.

    The 25fps zoompan output is then re-rendered to 30fps to match the
    rest of the pipeline. Slow zoom (target 1.10x over duration) feels
    natural — too fast and it looks fake; static feels frozen.
    """
    frames = max(int(duration_sec * 30), 30)
    # zoom rate: start at 1.0, end at 1.10 (10% zoom across the clip)
    zoom_expr = f"zoom+0.0035*if(gte(on,1),1,0)"
    # Center the zoom; pre-scale source up so zoompan doesn't pixelate
    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan=z='min(zoom+0.0008,1.10)':d={frames}:x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image_path),
        "-vf", vf,
        "-t", f"{duration_sec:.2f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _acquire_one_image(
    sh: dict,
    i: int,
    query: str,
    assets_dir: Path,
    cogview: CogViewClient,
    run_id: int | None = None,
) -> dict:
    """Generate a still via CogView, animate with ken-burns to give B-roll
    a B-roll a slow zoom-in motion.

    Cost: CogView-3-Flash is free at time of writing. ~5-10s per image
    vs ~10 minutes for CogVideoX-Flash video gen — dramatically faster
    when speed matters. Same watermark caveat applies (右下角 「AI 生成」).
    """
    from pipeline import cost_log
    dur = _doubao_duration_for_shot(sh.get("narration"))
    img_path = assets_dir / f"clip-{i:02d}-image-{slugify_query(query)}.png"
    target = assets_dir / f"clip-{i:02d}-image-{slugify_query(query)}.mp4"
    print(f"  s{i:02d} cogview generating ({query!r}) — ~10s...")
    t0 = time.monotonic()
    res = cogview.generate(query, size="1280x720")
    cogview.download(res, img_path)
    wall_gen = time.monotonic() - t0
    cost_log.log_event(
        service="youtube-clips-cogview",
        provider="zhipu",
        model=cogview.model,
        cost_usd=0.0,
        duration_ms=int(wall_gen * 1000),
        metadata={
            "image_id": res.image_id,
            "size": res.size,
            "run_id": run_id,
            "shot_idx": i,
            "prompt": (query or "")[:500],
        },
    )
    t1 = time.monotonic()
    _kenburns_image_to_mp4(img_path, target, dur)
    print(
        f"  s{i:02d} cogview:{res.image_id[:12]}... → ken-burns {dur}s "
        f"in {wall_gen:.0f}s gen + {time.monotonic()-t1:.0f}s anim"
    )
    return {
        "video_id": f"cogview-{res.image_id}",
        "title": query,
        "channel": "CogView Flash (ken-burns)",
        "role": "primary" if i == 0 else "supplement",
        "path": str(target),
        "duration_sec": dur,
        "page_url": None,
        "asset_strategy": "image",
    }


def _ffprobe_seconds(path: Path) -> float:
    """Best-effort duration probe; returns 0.0 if ffprobe unavailable."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            text=True,
        )
        return float(out.strip())
    except Exception:
        return 0.0


def _acquire_assets(
    shots: list[dict],
    assets_dir: Path,
    pexels: PexelsClient,
    volc,  # AI video client (CogVideoX or Volcengine) or None
    *,
    cogview: CogViewClient | None = None,
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
        # Map global override → chosen strategy. global_strategy options:
        # 'pexels' forces all-stock; 'ai' forces all video gen; 'image'
        # forces all AI image+ken-burns; 'hybrid' (default) honours
        # whatever the script agent emitted per shot.
        if global_strategy == "pexels":
            chosen = "pexels"
        elif global_strategy == "ai":
            chosen = "ai"
        elif global_strategy == "image":
            chosen = "image"
        else:  # hybrid
            chosen = shot_strategy
        events.emit(run_id, "acquire", "start",
                    f"s{i:02d} {chosen}: {query[:60]}",
                    shot_idx=i, strategy=chosen, query=query)

        def _fallback_pexels(reason: str = "") -> dict:
            if reason:
                events.emit(run_id, "acquire", "fail",
                            f"s{i:02d} {reason}", shot_idx=i)
            s = _acquire_one_pexels(sh, i, query, assets_dir, pexels)
            events.emit(run_id, "acquire", "done",
                        f"s{i:02d} pexels:{s.get('video_id')}",
                        shot_idx=i, video_id=s.get("video_id"))
            return s

        if chosen == "image":
            if cogview is None:
                print(f"  s{i:02d} asked for image but ZHIPU_API_KEY missing — pexels fallback")
                src = _fallback_pexels("image unavailable")
            else:
                try:
                    src = _acquire_one_image(
                        sh, i, query, assets_dir, cogview, run_id=run_id,
                    )
                    events.emit(run_id, "acquire", "done",
                                f"s{i:02d} {src.get('video_id')}",
                                shot_idx=i, video_id=src.get("video_id"))
                except Exception as e:
                    print(
                        f"  s{i:02d} image gen failed ({type(e).__name__}: {e}); "
                        f"falling back to pexels", flush=True,
                    )
                    src = _fallback_pexels(f"image failed: {e}")
        elif chosen == "ai":
            if volc is None:
                print(f"  s{i:02d} asked for AI video but no client — pexels fallback")
                src = _fallback_pexels("ai-video unavailable")
            else:
                try:
                    src = _acquire_one_ai(
                        sh, i, query, assets_dir, volc, run_id=run_id,
                    )
                    events.emit(run_id, "acquire", "done",
                                f"s{i:02d} {src.get('video_id')}",
                                shot_idx=i, video_id=src.get("video_id"))
                except Exception as e:
                    print(
                        f"  s{i:02d} AI video gen failed ({type(e).__name__}: "
                        f"{e}); falling back to pexels",
                        flush=True,
                    )
                    src = _fallback_pexels(f"ai-video failed: {e}")
        else:
            src = _fallback_pexels()
        sources.append(src)
    return sources


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="What this video is about")
    ap.add_argument("--profile", required=True, help="Profile name (must be production_mode=producer)")
    ap.add_argument(
        "--asset-strategy",
        choices=["pexels", "ai", "image", "hybrid"],
        default="hybrid",
        help=(
            "How to source per-shot visuals. 'hybrid' (default) respects "
            "the per-shot strategy the script agent chose. 'pexels' forces "
            "all-stock. 'ai' forces all AI-video (slow / costly). 'image' "
            "forces all AI-still + ken-burns (free, fast)."
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
    # AI-tier vendor pick — two parallel tiers:
    #   - VIDEO  (`volc`): CogVideoX-Flash (zhipu, free, slow ~10min/clip)
    #     → fallback to Doubao Seedance (volcengine, paid, fast ~60s)
    #   - IMAGE  (`cogview`): CogView-3-Flash (zhipu, free, ~10s/image)
    #     animated to clip via ken-burns. Operator's KPI is Doubao $; cogview
    #     route gives free, fast, no-watermark-on-burn-in-subtitle B-roll.
    volc = None
    if os.environ.get("ZHIPU_API_KEY"):
        try:
            volc = CogVideoXClient()
            print(f"  ai-video vendor: CogVideoX-Flash (zhipu, free)")
        except RuntimeError as e:
            print(f"  CogVideoXClient init failed: {e}")
    if volc is None:
        try:
            volc = VolcengineClient()
            print(f"  ai-video vendor: Doubao Seedance (volcengine, paid)")
        except RuntimeError as e:
            if args.asset_strategy == "ai":
                events.emit(run_id, "assets", "fail", str(e))
                events.finish_run(run_id, "failed", str(e))
                sys.exit(
                    f"--asset-strategy ai needs ZHIPU_API_KEY or "
                    f"VOLC_ARK_API_KEY: {e}"
                )
    cogview = None
    if os.environ.get("ZHIPU_API_KEY"):
        try:
            cogview = CogViewClient()
            print(f"  ai-image vendor: CogView-3-Flash (zhipu, free)")
        except RuntimeError as e:
            print(f"  CogViewClient init failed: {e}")
    sources = _acquire_assets(
        shots, assets_dir, pexels, volc,
        cogview=cogview,
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
