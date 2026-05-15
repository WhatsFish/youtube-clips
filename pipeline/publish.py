"""Stage 3 — per-platform publish-materials generation.

For each platform in `Profile.channel.publish_channels`, render the
platform's publish prompt (publish-bilibili / publish-douyin / ...),
call Claude to get title/description/tags/category + N cover_prompts,
generate covers via CogView, UPDATE outputs row with the materials.

Shared by both `produce-original.py` (producer mode) and `produce.py`
(commentary / synthesis modes). Both modes' EDLs share the same shape
for what this code reads — title_zh, thesis_zh, description_zh, tags_zh,
shots[].narration — so this function is mode-agnostic.

Idempotent: re-running overwrites cover files and UPDATEs row.
Per-channel failure is logged but doesn't abort the loop.
"""
from __future__ import annotations

from pathlib import Path

from pipeline import db, events
from pipeline.claude_io import call_claude, extract_json
from pipeline.cogview import CogViewClient
from pipeline.prompts import load_prompt


def enhance_cogview_prompt(visual_brief: str) -> str:
    """Wrap a visual_brief with quality directives that consistently
    lift CogView-3-Flash output. Without these the model tends to produce
    flat, generic, illustration-y images.
    """
    base = visual_brief.strip().rstrip(".")
    style = "photorealistic documentary photography, natural lighting"
    technical = "8k resolution, sharp focus, fine detail, depth of field"
    if any(kw in base.lower() for kw in ("chinese", "china", "县", "中国")):
        cultural = "authentic Chinese aesthetic, realistic textures, no stylization"
    else:
        cultural = "natural realistic look"
    negative = "no text overlays, no watermarks, no logos, no cartoon style"
    return f"{base}. {style}. {cultural}. {technical}. {negative}."


def generate_publish_materials(
    *,
    profile,
    edl: dict,
    job_id: int,
    job_dir: Path,
    run_id: int | None = None,
) -> None:
    """Iterate publish_channels[]; for each, render the prompt → call
    Claude → generate covers via CogView → UPDATE outputs row.
    """
    cfg = (profile.config or {}).get("channel") or {}
    channels = cfg.get("publish_channels") or []
    if not channels:
        return

    events.emit(run_id, "publish", "start", f"{len(channels)} channel(s)")
    print(f"\n──── publish materials {'─' * 39}")

    for ch_cfg in channels:
        platform = ch_cfg.get("platform")
        if not platform:
            continue
        try:
            _publish_one_channel(
                profile=profile, edl=edl, job_id=job_id, job_dir=job_dir,
                channel_cfg=ch_cfg, run_id=run_id,
            )
        except Exception as e:
            print(f"  [publish:{platform}] failed: {e}", flush=True)
            events.emit(run_id, "publish", "fail", f"{platform}: {e}")

    events.emit(run_id, "publish", "done", "")


def _publish_one_channel(
    *,
    profile,
    edl: dict,
    job_id: int,
    job_dir: Path,
    channel_cfg: dict,
    run_id: int | None = None,
) -> None:
    platform = channel_cfg["platform"]
    prompt_name = channel_cfg.get("publish_prompt") or f"publish-{platform.split('_')[0]}"
    cover_count = int(channel_cfg.get("cover_count") or 4)
    cover_size = channel_cfg.get("cover_size") or "1280x800"

    shots_summary = "\n".join(
        f"  shot{i:02d}: {sh.get('narration','')[:90]}"
        for i, sh in enumerate(edl.get("shots") or [])
    )

    tmpl = load_prompt(prompt_name, version="latest")
    tags_zh = edl.get("tags_zh") or []
    prompt = tmpl.render(
        profile_block=profile.render_block(),
        title_zh=edl.get("title_zh") or "",
        thesis_zh=edl.get("thesis_zh") or "",
        description_zh=edl.get("description_zh") or "",
        tags_zh=", ".join(tags_zh) if tags_zh else "(none)",
        shots_summary=shots_summary,
    )
    print(f"  [{platform}] calling claude ({tmpl.stamp})...")
    events.emit(run_id, "publish", "info", f"{platform}: claude call")
    raw = call_claude(prompt, timeout=180)
    materials = extract_json(raw)

    cogview = CogViewClient()
    covers_dir = job_dir / f"covers-{platform}"
    covers_dir.mkdir(exist_ok=True)
    cover_prompts = (materials.get("cover_prompts") or [])[:cover_count]
    cover_paths: list[str] = []
    for j, cp in enumerate(cover_prompts):
        print(f"  [{platform}] cover {j+1}/{len(cover_prompts)}...")
        try:
            enhanced = enhance_cogview_prompt(cp)
            res = cogview.generate(enhanced, size=cover_size)
            out = covers_dir / f"cover-{j+1}.png"
            cogview.download(res, out)
            cover_paths.append(str(out))
        except Exception as e:
            print(f"    cover gen failed: {e}")

    with db.cursor() as cur:
        cur.execute(
            """
            UPDATE outputs SET
                title       = COALESCE(%s, title),
                description = COALESCE(%s, description),
                tags        = %s,
                category    = COALESCE(%s, category),
                cover_paths = %s
            WHERE job_id = %s AND platform = %s
            """,
            (
                materials.get("title"),
                materials.get("description"),
                materials.get("tags") or [],
                materials.get("category"),
                cover_paths,
                job_id, platform,
            ),
        )
    print(f"  [{platform}] {len(cover_paths)} covers + materials saved")
    events.emit(run_id, "publish", "done", f"{platform}: {len(cover_paths)} covers")
