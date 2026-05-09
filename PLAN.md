# youtube-clips — Design Plan

**Status:** Phase 0 in progress (as of 2026-05-09).
**Owner:** liharr
**Repo (planned):** `WhatsFish/youtube-clips`

> Single source of truth for this project's design. Update this file when decisions change. Earlier discussion lives in conversation history.

---

## What this project is

A **Profile-based, multi-platform, cross-language video remix pipeline**. You give a topic (or an agent proposes one and you approve it); the pipeline searches a configured source platform for raw material, downloads it, has Claude write an edit decision list (EDL) and a target-language commentary script, renders one or more platform-specific variants (16:9 / 9:16, language-converted), and shows you previews to download. **No auto-publishing** — you upload to each platform manually.

Operating model: **you only do命题选择 and final review**; everything between is automated.

---

## Why "Profile-based"

A Profile = one **channel concept**. Different channels target different platforms, languages, audiences, and editing styles. Hardcoding any of these into the pipeline would mean per-channel forks. Instead, each Profile is a config blob that drives the entire pipeline; downstream code is profile-agnostic.

Example Profile (the demo one):

```yaml
profile_id: tech-insights-cn
description: "English tech YouTube videos → Chinese Bilibili commentary"

source:
  platforms: [youtube]              # extensible: bilibili, douyin, vimeo, ...
  language: en
  content_hints: ["tech review", "AI news"]

output:
  platforms: [bilibili_long, bilibili_vertical, douyin]
  language: zh
  tts_voice: "zh-CN-XiaoxiaoNeural"

style:
  template: commentary              # commentary | montage | reaction | tutorial
  pacing: medium
  audio_strategy: ducked_original   # original audio low + Chinese voiceover
  caption_strategy: burn_zh         # burn Chinese subtitles

branding:
  intro_path: null
  outro_path: null
  watermark: "@your-handle"

topic_generation_prompt: |
  你为一个面向中文受众的科技频道选题 ...

edit_style_prompt: |
  你写 commentary 风格的 EDL，audio strategy = ducked_original ...
```

A new "channel" is a new Profile row, no code changes.

---

## Cross-platform & cross-language strategy

**Source/output platform pairing**: prefer cross-platform to reduce same-platform fingerprint detection. The demo Profile uses YouTube (English source) → Bilibili (Chinese output). The reverse direction (Bilibili source → YouTube output) is a future Profile.

**Language pipeline** when source.language ≠ output.language:
1. Get/generate source-language transcript with word-level timestamps
2. Claude translates and adapts into target-language commentary script (not a direct translation; a commentary)
3. TTS in target language
4. Mix original audio (ducked) + commentary
5. Burn target-language subtitles

---

## Architecture

```
┌─────────────┐    ┌──────────────────────────────────────┐
│ Cron        │───▶│ Topic Generator Agent                │
│             │    │  Claude + trends + Profile.topic_prompt│
└─────────────┘    └──────────────────┬───────────────────┘
                                       │ topic candidates
                                       ▼
                          ┌─────────────────────┐
                  ┌──────▶│ Web UI: 你审核 topic │
                  │       └──────────┬──────────┘
                  │                  │ approved
                  │                  ▼
                  │       ┌──────────────────────────────┐
                  │       │ Source Discovery Agent       │
                  │       │ Per-platform search + filter │
                  │       └──────────┬───────────────────┘
                  │                  │ selected videos
                  │                  ▼
                  │       ┌──────────────────────────────┐
                  │       │ Download + Transcribe         │
                  │       │ yt-dlp + Groq Whisper        │
                  │       └──────────┬───────────────────┘
                  │                  │
                  │                  ▼
                  │       ┌──────────────────────────────┐
                  │       │ Edit Decision Agent          │
                  │       │ Claude → EDL + commentary    │
                  │       └──────────┬───────────────────┘
                  │                  │
                  │                  ▼
                  │       ┌──────────────────────────────┐
                  │       │ Render Pipeline              │
                  │       │ ffmpeg + Azure TTS + captions│
                  │       │ → N platform variants        │
                  │       └──────────┬───────────────────┘
                  │                  │
                  │                  ▼
                  │       ┌──────────────────────────────┐
                  └───────│ Web UI: 预览/下载/反馈重剪    │
                          └──────────────────────────────┘
```

---

## Database schema

```sql
profiles            -- channel strategies; one row per channel concept
  id, name, description,
  config_jsonb,     -- the Profile YAML above
  active, created_at, updated_at

topics              -- selection items
  id, profile_id, title, description, keywords[],
  status,           -- pending | approved | rejected | done
  source,           -- 'agent' | 'human'
  generated_at, approved_at

sources             -- raw material per source platform
  id, profile_id, source_platform, external_id, url,
  title, channel, duration_sec, source_language,
  transcript_jsonb, -- {original: ..., translated: ..., word_timestamps: ...}
  metadata_jsonb,
  download_path, downloaded_at, ttl_delete_at

jobs                -- one render job
  id, topic_id, profile_id,
  edl_jsonb,
  parent_job_id,    -- for regeneration lineage
  status, error_jsonb,
  created_at, started_at, completed_at

outputs             -- one job → N platform variants
  id, job_id, platform, aspect_ratio, language,
  path, duration_sec, file_size_bytes,
  thumbnail_path,
  title, description, tags[],
  status

feedback            -- user regenerate instructions
  id, job_id, user_text,
  regenerated_job_id, created_at
```

---

## Phase plan

### Phase 0 — Infrastructure (current)

| # | Owner | Action |
|---|---|---|
| 0.1 | liharr | Azure portal: create 500 GB **Standard SSD**, Japan East, same zone as `ai-native` VM, LRS. Attach to VM (Read/Write host caching) |
| 0.2 | claude | Identify new disk (`lsblk`), `parted` GPT, `mkfs.ext4`, get UUID, add to `/etc/fstab` with `defaults,nofail`, `mount /video`, `chown liharr:liharr /video` |
| 0.3 | claude | Verify `df -h /video` ~492 GB available; 1 GB read/write smoke test |
| 0.4 | claude | Update root `CLAUDE.md` "Disk layout" section: add `/video/` for video projects |
| 0.5 | claude | Add `/video` disk-water-level check to /status (>80% red) |

### Phase 1 — Project skeleton (six-step convention from root CLAUDE.md)

| # | Action |
|---|---|
| 1.1 | `git init` `/home/liharr/src/youtube-clips/`; `gh repo create WhatsFish/youtube-clips --public --source=. --remote=origin --push` |
| 1.2 | Postgres: bootstrap `youtube_clips` role + DB via umami superuser (mirror `stock-analyst/db/bootstrap.sh`) |
| 1.3 | nginx snippet `/etc/nginx/snippets/youtube-clips.conf`, basePath `/youtube-clips`, proxy `127.0.0.1:3008` |
| 1.4 | Next.js 14 App Router + Tailwind + pg, container on `traffic-monitor_default`, `output: standalone` |
| 1.5 | site-index navigation entry |
| 1.6 | /status group: HTTP probe + DB freshness + cron heartbeats; register `/video` disk check |
| 1.7 | `~/.config/youtube-clips.env`: `YT_API_KEY`, `AZURE_SPEECH_KEY`, `GROQ_API_KEY`, DB creds (Claude is invoked via the `claude` CLI which uses its own auth — no `ANTHROPIC_API_KEY` needed) |
| 1.8 | Umami site (manual via Umami UI to get website-id) |
| 1.9 | `run-agent.sh` template; cost-tracker hook |

### Phase 2 — MVP pipeline (single platform variant, demo Profile only)

**Goal:** approved topic → 1 mp4 (16:9 Bilibili long, Chinese narration over English clips). Prove the loop. **Skip everything not on this critical path.**

| # | Module | Tool |
|---|---|---|
| 2.1 | Migrations: schema above (all tables) | sql |
| 2.2 | Seed demo Profile `tech-insights-cn` | sql |
| 2.3 | Source discovery agent: YouTube Data API search + Claude filter on transcripts | TS/Python script |
| 2.4 | Downloader: yt-dlp → `/video/youtube-clips/raw/<id>/` | yt-dlp |
| 2.5 | Transcriber: prefer YouTube native captions; fallback Groq Whisper API | groq |
| 2.6 | Translator: Claude (transcript → adapted Chinese commentary) | claude |
| 2.7 | Edit decision agent: Claude → EDL JSON | claude |
| 2.8 | TTS: Azure Speech (Chinese voice from Profile) → mp3 | azure-speech |
| 2.9 | Renderer: ffmpeg cut + duck original audio + overlay Chinese narration → 16:9 mp4 | ffmpeg |
| 2.10 | Web UI: `/youtube-clips/jobs/[id]` preview + download | next |
| 2.11 | Cron: scan approved topics, run pipeline | cron |
| 2.12 | Cleanup cron: TTL delete `raw/` >7d, `clips/` >30d; heartbeat | cron |

**Deliberately NOT in Phase 2**: caption burn-in, multi-platform variants, smart vertical crop, thumbnails, agent-proposed topics, regeneration loop. All these come in later phases — first make the loop work end-to-end.

### Phase 3 — Quality enhancements

- Burn Chinese captions with word-level highlighting (`captacity`, OSS)
- Multi-platform variants from same EDL: Bilibili long (16:9), Bilibili vertical / Douyin (9:16, ≤60s)
- 16:9 → 9:16: heuristic center+headroom crop (subject tracking later if needed)
- Per-platform titles/descriptions/tags from Claude

### Phase 4 — Topics & thumbnails

- Topic generator agent (cron): Claude + YouTube trending + `Profile.topic_generation_prompt`
- Topic review UI (`/youtube-clips/topics`): approve / reject / edit-and-approve
- Thumbnail generation: Claude prompt → image API (Imagen 4 or GPT Image, decide at this phase) → text overlay

### Phase 5 — Feedback loop

- Job detail page: inline previews + textarea for regen feedback + "再生成一版" button
- Regen agent: feedback + previous EDL → new EDL → new job linked via `parent_job_id`

### Phase 6 — (deferred) Quality ceiling

- Paid drop-in upgrades: Submagic (captions), Opus Clip (smart vertical), ElevenLabs (voices)
- Visual understanding: Claude/Gemini video input for picking visually compelling moments
- BGM library + emotion-based selection
- A/B variants per topic

---

## Tool stack (decided)

| Use | Choice | Note |
|---|---|---|
| Video download | yt-dlp | Supports 1700+ sites incl. Bilibili — no need for separate downloaders |
| Video processing | ffmpeg | — |
| Transcription | YouTube native captions → Groq Whisper API fallback | No local Whisper, no GPU |
| Translation/commentary | Claude 4.7 | — |
| TTS | Azure Speech | Already on Azure |
| Captions (Phase 3) | captacity (OSS) | Word-level ffmpeg burn-in |
| Image gen (Phase 4) | TBD: Imagen 4 vs GPT Image | Decide at Phase 4 |
| Web | Next.js 14 + Tailwind + pg | Fleet standard |
| DB | Shared Postgres `traffic-monitor-db-1` | Per-service role + DB |
| Smart vertical crop | Heuristic (Phase 3) → optional Opus Clip API (Phase 6) | — |

---

## GPU / VM decision

- **No GPU**. All AI workloads via cloud APIs (Groq Whisper, Azure Speech, Claude, image gen). Maintaining a GPU VM is overhead for this workload.
- **VM resize deferred** to post-MVP. Current VM (D2s_v3, 2 vCPU / 8 GB) is fine for Phase 0–1 (pure web/DB). For Phase 2+ ffmpeg load, evaluate after measurements; likely candidate is **F4s_v2** (4 vCPU compute-optimized, ~$130/mo, 10-min online resize).

---

## Cost estimate (monthly)

| Item | Estimate |
|---|---|
| 500 GB Standard SSD | ~$38 |
| Claude API (≈30 outputs/mo) | $30–100 |
| Azure Speech TTS | $5–15 |
| Groq Whisper (fallback) | <$5 |
| YouTube Data API | $0 (free quota) |
| Image gen (thumbnails, ≈30/mo) | $1–2 |
| **Total** | **~$75–155/mo** |

VM resize (if executed Phase 2+): +$60–150/mo on top.

---

## Operational conventions (per root CLAUDE.md)

- Code under `/home/liharr/src/youtube-clips/` (root disk)
- Working data under `/video/youtube-clips/` (new 500 GB SSD)
- Secrets in `~/.config/youtube-clips.env` (mode 600, gitignored)
- Cron heartbeats: `/home/liharr/.local/share/cron-heartbeats/youtube-clips-<job>`
- Auto-commit at logical milestones, auto-push to `WhatsFish/youtube-clips`
- All Anthropic + Azure Foundry calls log a `cost_event` row

---

## Open / deferred questions

- Phase 4 thumbnail engine choice (Imagen 4 vs GPT Image)
- Phase 6 paid upgrades (decide based on Phase 3 quality assessment)
- Bilibili search API (when adding Bilibili as a source platform — not needed for demo Profile)
- Scope of Profile-level branding (intros/outros) — defined when we have a real channel
- Whether to add Azure Blob archive tier for long-term output storage (only needed if disk fills)

---

## Directory layout (post Phase 1)

```
/home/liharr/src/youtube-clips/      # code (root disk)
  PLAN.md                            # this file
  web/                               # Next.js
  agents/                            # topic, source, edit, render
  db/                                # migrations, bootstrap
  scripts/                           # cron entrypoints, run-agent.sh
  docker-compose.yml
  .env                               # gitignored, links to ~/.config

/video/youtube-clips/                # data (new 500 GB disk)
  raw/<source_id>/                   # yt-dlp downloads, TTL 7d
  clips/<source_id>/                 # extracted segments, TTL 30d
  outputs/<job_id>/                  # rendered variants, long-lived
    bilibili_long.mp4
    bilibili_vertical.mp4
    douyin.mp4
  thumbnails/<job_id>/
  bgm/                               # shared music library
  voices/                            # TTS voice samples

~/.config/youtube-clips.env          # secrets
```
