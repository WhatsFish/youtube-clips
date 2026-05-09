# youtube-clips — Design Plan

**Owner:** liharr
**Repo:** [`WhatsFish/youtube-clips`](https://github.com/WhatsFish/youtube-clips)

> Single source of truth for this project's design. Update this file when decisions change. Earlier discussion lives in conversation history.

---

## Status snapshot (2026-05-09)

```
Phase 0 — Infrastructure                                ████████████  done
Phase 1 — Project skeleton (the six-step convention)    ████████████  done
Phase 2 — MVP pipeline                                  ████████░░░░  ~60%
  ├ DB schema + demo Profile seed                       ████████████  done
  ├ vertical-slice prototype (LLM core proven E2E)      ████████████  done
  │   • hello-render.py — yt-dlp + ffmpeg + TTS chain
  │   • edl-prototype.py — Claude → EDL JSON
  │   • edl-render.py    — EDL → 16:9 mp4
  ├ web review UI (home grouped by Profile, /jobs/[id]) ████████████  done
  ├ prompts as files + Profile read from DB             ████████████  done
  ├ source discovery agent (2.3)                        ████████████  done
  ├ download / transcribe modules (2.4 / 2.5)           ░░░░░░░░░░░░  not started
  ├ DB-backed jobs/sources/outputs (productionize)      ░░░░░░░░░░░░  not started
  └ cleanup cron + multi-platform fan-out               ░░░░░░░░░░░░  not started
Phase 3+ — quality, topics, feedback loop               ░░░░░░░░░░░░  not started
```

The Phase 2 sub-tasks below carry ✅ for the ones that have shipped and ☐ for the ones that haven't, so a cold reader can tell at a glance where the line is. Update this section whenever a sub-task crosses the line.

---

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

## Profile model: three dimensions of style

The Profile abstraction has to absorb three orthogonal dimensions of stylistic
variation — mixing them up produces unmaintainable prompts and per-channel
forks. The expanded schema below separates them so any single (Profile,
Topic, Output) tuple resolves cleanly to one final prompt + one render config.

| Dimension | Examples | Where it lives |
|---|---|---|
| **Channel** (persona / brand voice) | "professional tech UP" vs "tech meme channel"; voice; verbal tics | `Profile.channel` (defaults for everything) |
| **Topic-class** (genre within a channel) | AI news vs hardware review vs tutorial — same channel, different cadence and tone | `Profile.topic_classes[<class>]` (overrides channel) |
| **Platform-variant** (per-output overrides) | B 站长 vs 抖音 vs YT Shorts — same narration, different aspect / pacing / caption density | `Profile.output_variants[<platform>]` (overrides everything else) |

### Expanded Profile schema (target shape; current seed uses the simpler subset)

```yaml
profile_id: tech-insights-cn

# Channel-level defaults — apply when no topic_class / output_variant override
channel:
  voice: zh-CN-YunxiNeural
  rate_pct: 15
  tone: "年轻、专业、有态度，带轻微 hot take"
  vocabulary: "技术术语直接用，不需要每个名词都解释"
  hot_take_propensity: mild         # none | mild | strong
  verbal_tics: ["划重点", "反常识的是", "这就有意思了"]
  forbidden_phrases: ["大家好欢迎收看", "今天我们要讲"]
  example_narrations:               # few-shot samples for prompt assembly
    - "上周谷歌干了件 FAANG 大厂都不敢干的事..."
    - ...

# Topic-class overrides — pick a class on each Topic; absent → channel defaults
topic_classes:
  ai_news:
    pacing_sec_per_shot: [6, 10]
    hot_take_propensity: mild
  hardware_review:
    pacing_sec_per_shot: [8, 14]    # show the hardware longer
    vocabulary: "性能数字必须给出，不能含糊"
  tutorial:
    hot_take_propensity: none
    rate_pct: 0                     # slow it down for instruction

# Output-variant overrides — one per target platform, fans out at render
output_variants:
  bilibili_long:
    aspect_ratio: 16:9
    length_target_min: [3, 8]
    caption_strategy: burn_zh_static
  bilibili_vertical:
    aspect_ratio: 9:16
    length_target_min: [0.5, 1]
    caption_strategy: burn_zh_animated
    hook_strategy: "前 1.5 秒必须有钩子"
  douyin:
    aspect_ratio: 9:16
    length_target_min: [0.5, 1]
    caption_strategy: burn_zh_animated_aggressive
    rate_pct: 25                    # tolerance is lower; faster delivery

# Branding (per-channel; can be platform-overridden)
branding:
  intro_path: null
  outro_path: null
  watermark: "@your-handle"

# Free-text escape hatches — used when structured fields don't capture
# something a particular channel needs.
topic_generation_prompt: |
  你为一个面向中文受众的科技频道选题 ...
edit_style_prompt: |
  你写 commentary 风格的 EDL ...
```

### Prompt assembly at runtime

For each `(Profile, Topic, Output)` tuple, the agent's prompt is composed top-down with later layers overriding earlier ones:

```
final_prompt = base_prompt
             ⊕ Profile.channel
             ⊕ Profile.topic_classes[Topic.topic_class]    # override channel
             ⊕ Profile.output_variants[Output.platform]    # override everything
             ⊕ Profile.channel.example_narrations          # few-shot
             ⊕ source transcript
```

A single source video that ships to (B 站长, B 站竖屏, 抖音) resolves to three independent EDLs and three render configs — but they share `channel.tone`, `forbidden_phrases`, and `verbal_tics`, so they sound like the same channel. Brand consistency comes from the `channel` layer; platform native-ness comes from the variant layer.

### What's actually implemented vs. designed

The current DB seed of `tech-insights-cn` uses a flatter `config_jsonb` (single voice, single platform, single style block). That's fine — `JSONB` accepts arbitrary shapes, so growing into the full schema above is a matter of writing it into existing rows, not a migration.

Concrete rollout order:

1. **Now** (Phase 2 demo): keep the current shape. One Profile, one variant, no topic-class.
2. **When the second Profile lands** (e.g., a tutorial-style channel, or a non-tech topic): structure `channel` and `forbidden_phrases` then. Validate the layered model with two real concrete cases.
3. **When fan-out to a 2nd platform is needed**: add `output_variants` and rev the renderer to iterate over them.
4. **When a channel has multiple topic types**: add `topic_classes` + `topic_class` field on Topic.

Each step is additive — no schema migration, just JSONB updates and prompt-assembly logic.

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

| # | Owner | Action | Status |
|---|---|---|---|
| 0.1 | liharr | Azure portal: create 500 GB **Standard SSD**, Japan East, same zone as `ai-native` VM, LRS. Attach to VM (Read/Write host caching) | ✅ |
| 0.2 | claude | Identify new disk (`lsblk`), `parted` GPT, `mkfs.ext4`, get UUID, add to `/etc/fstab` with `defaults,nofail`, `mount /video`, `chown liharr:liharr /video` | ✅ |
| 0.3 | claude | Verify `df -h /video` ~492 GB available; 1 GB read/write smoke test | ✅ |
| 0.4 | claude | Update root `CLAUDE.md` "Disk layout" section: add `/video/` for video projects | ✅ |
| 0.5 | claude | Add `/video` disk-water-level check to /status (>80% red) | ✅ |

### Phase 1 — Project skeleton (six-step convention from root CLAUDE.md)

| # | Action | Status |
|---|---|---|
| 1.1 | `git init` `/home/liharr/src/youtube-clips/`; `gh repo create WhatsFish/youtube-clips --public --source=. --remote=origin --push` | ✅ |
| 1.2 | Postgres: bootstrap `youtube_clips` role + DB via umami superuser (mirror `stock-analyst/db/bootstrap.sh`) | ✅ |
| 1.3 | nginx snippet `/etc/nginx/snippets/youtube-clips.conf`, basePath `/youtube-clips`, proxy `127.0.0.1:3008` | ✅ |
| 1.4 | Next.js 14 App Router + Tailwind + pg, container on `traffic-monitor_default`, `output: standalone` | ✅ |
| 1.5 | site-index navigation entry | ✅ |
| 1.6 | /status group: HTTP probe + DB freshness + cron heartbeats; register `/video` disk check | ✅ |
| 1.7 | `~/.config/youtube-clips.env`: `YT_API_KEY`, `AZURE_SPEECH_KEY`, `GROQ_API_KEY`, DB creds (Claude is invoked via the `claude` CLI which uses its own auth — no `ANTHROPIC_API_KEY` needed) | ✅ |
| 1.8 | Umami site (manual via Umami UI to get website-id) | ✅ |
| 1.9 | `run-agent.sh` template; cost-tracker hook | ✅ (stub; real agent in Phase 2.x) |

### Phase 2 — MVP pipeline (single platform variant, demo Profile only)

**Goal:** approved topic → 1 mp4 (16:9 Bilibili long, Chinese narration over English clips). Prove the loop. **Skip everything not on this critical path.**

| # | Module | Tool | Status |
|---|---|---|---|
| 2.1 | Migrations: full schema (`profiles` + `topics`/`sources`/`jobs`/`outputs`/`feedback`) | sql | ✅ |
| 2.2 | Seed demo Profile `tech-insights-cn` | sql | ✅ (also `db/seeds/update-…sql` for evolving the row in place) |
| 2.3 | Source discovery agent: YouTube Data API search + metadata filter + Claude pick | Python | ✅ via `scripts/discover-source.py` (uses `pipeline/youtube_search.py` + `prompts/source-pick.v1.md`); transcript-based ranking deferred to v2 of the prompt if needed |
| 2.4 | Downloader: yt-dlp → `/video/youtube-clips/raw/<id>/` | yt-dlp | ☐ — single-shot proven by `scripts/hello-render.py` (cookies + deno + EJS) |
| 2.5 | Transcriber: prefer YouTube native captions; fallback Groq Whisper API | groq | ☐ — VTT path proven inside `scripts/edl-prototype.py` |
| 2.6 | Translator: Claude (transcript → adapted Chinese commentary) | claude | ✅ via `scripts/edl-prototype.py` (file-based prompt + DB Profile) |
| 2.7 | Edit decision agent: Claude → EDL JSON | claude | ✅ same script as 2.6 (single-pass) |
| 2.8 | TTS: Azure Speech (Chinese voice from Profile) → mp3 | azure-speech | ✅ via `scripts/edl-render.py` |
| 2.9 | Renderer: ffmpeg cut + duck original audio + overlay Chinese narration → 16:9 mp4 | ffmpeg | ✅ same script as 2.8 |
| 2.10 | Web UI: `/youtube-clips/` (Profile-grouped list) + `/youtube-clips/jobs/[id]` preview + download | next | ✅ |
| 2.11 | Cron: scan approved topics, run pipeline | cron | ☐ |
| 2.12 | Cleanup cron: TTL delete `raw/` >7d, `clips/` >30d; heartbeat | cron | ☐ |

**Phase 2 productionization debt** (the prototype works end-to-end, but several pieces still need to be unified into the official pipeline):

| Item | Status | Notes |
|---|---|---|
| Renders enumerated from filesystem, not Postgres | ⚠ debt | `web/src/lib/jobs.ts` scans `/data/renders/`; should query `jobs`/`outputs` tables once 2.3–2.5 land |
| `edl-prototype.py` doesn't write to `topics` / `sources` / `jobs` / `outputs` tables | ⚠ debt | output is a folder of files; rows happen during productionization |
| Source discovery is manual (you give `video_id` + `--title` + `--channel` flags) | ✅ closed | `scripts/discover-source.py --topic "..."` picks a video; output JSON has the id + title + channel ready for the next step |
| Cookie freshness for yt-dlp — silent failure when cookies rotate | ⚠ debt | YouTube rotates account cookies every few weeks; needs a /status check on cookie age + a cookie-refresh playbook (re-export from browser) |
| Downloader is one yt-dlp call inside `hello-render.py` | ⚠ debt | 2.4 will move it into a reusable downloader module |
| Single platform variant per render | ⚠ debt | Phase 3 fan-out reads `Profile.output_variants[]` (see Profile model section) |

**Deliberately NOT in Phase 2**: caption burn-in, multi-platform variants, smart vertical crop, thumbnails, agent-proposed topics, regeneration loop. All these come in later phases — first make the loop work end-to-end.

### Prompt management

LLM prompts live as plain markdown files under `prompts/<task>.v<n>.md` with YAML frontmatter (name, version, purpose, last_updated, notes, required_placeholders). Body uses `str.format()` placeholders that the runtime fills in. Loader is `pipeline.prompts.load_prompt(name, version="latest")`.

```
prompts/
  edl-continuous.v2.md     ← current default for the EDL agent
  README.md                ← prompt convention + version policy
```

Three rules that pay off as the prompt count grows:

1. **Frozen versions**. Don't edit a versioned prompt in place; copy to the next version. Old versions stay so you can A/B and so prior EDL outputs that reference them remain reproducible.
2. **Stamp identity into outputs**. `edl-prototype.py` writes `prompt_template_version: "edl-continuous.v2"` and `profile_name: "tech-insights-cn"` and `rendered_at` into every `edl.json`. Every render is traceable to a (Profile row, prompt file) pair.
3. **Profile drives values, prompt drives structure**. The prompt template is the *task* (filter + EDL + Chinese narration). The Profile is the *channel-specific tunables* (voice, tone, verbal_tics, edit_style_prompt). At runtime, `Profile.render_block()` is injected into the prompt template's `{profile_block}` slot. New channel = new Profile row; no prompt edit. Prompt iteration = bump the version; no DB change.

`pipeline/profiles.py` reads from Postgres (no more code-side hardcoded copy). `pipeline/prompts.py` loads the markdown files. Both modules are thin.

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

## Directory layout

```
/home/liharr/src/youtube-clips/      # code (root disk)
  PLAN.md                            # this file
  web/                               # Next.js (basePath /youtube-clips, port 3008)
    src/
      app/                           # pages: / + /jobs/[id]
      lib/
        db.ts                        # Postgres helper
        jobs.ts                      # filesystem-backed render enumeration
  pipeline/                          # Python helpers shared by scripts
    prompts.py                       # load+render markdown prompt files
    profiles.py                      # fetch Profile from Postgres
    claude_io.py                     # call_claude + extract_json (sanitizer)
    youtube_search.py                # YouTube Data API v3 search + enrich
  prompts/                           # LLM prompts as data, not code
    edl-continuous.v2.md             # current EDL default
    source-pick.v1.md                # source-discovery agent default
    README.md                        # prompt versioning convention
  db/
    schema.sql                       # idempotent CREATE + INSERT-skip seed
    bootstrap.sh                     # apply schema as the youtube_clips role
    seeds/
      update-tech-insights-cn.sql    # one-shot UPDATE for evolving the seed
  scripts/                           # CLI entrypoints (no daemons)
    hello-render.py                  # standalone yt-dlp+ffmpeg+TTS smoke
    discover-source.py               # topic → search → Claude pick → JSON
    edl-prototype.py                 # transcript → Claude → EDL JSON
    edl-render.py                    # EDL → mp4
    run-agent.sh                     # cron entrypoint stub
  docker-compose.yml                 # web container + traffic-monitor_default
  .env                               # gitignored, mirrors ~/.config/...env
  .venv/                             # Python venv (gitignored)

/video/youtube-clips/                # data (500 GB Standard SSD)
  raw/<source_id>/                   # yt-dlp downloads, source.mp4 + source.en.vtt
  clips/<source_id>/                 # (Phase 3) extracted segments, TTL 30d
  outputs/
    discovered/<profile>/<topic-slug>.json    # discover-source.py output
    edl-prototype/<source_id>/       # current prototype output dir
      edl.json                       # stamped: profile_name + prompt_template_version + rendered_at
      render.mp4                     # rendered Bilibili-long mp4
      prompt.txt                     # exact prompt sent to Claude (debugging)
      raw-claude.txt                 # raw stdout from Claude (debugging)
      _work/                         # per-shot intermediates (kept for debugging)
    <job_id>/                        # (Phase 2 productionized) one folder per Job row
      bilibili_long.mp4
      bilibili_vertical.mp4          # (Phase 3 fan-out)
      douyin.mp4                     # (Phase 3)
  thumbnails/<job_id>/               # (Phase 4)
  bgm/                               # shared music library
  voices/                            # TTS voice samples

~/.config/youtube-clips.env          # mode 600: DB password + API keys + Umami
~/.config/youtube-clips-cookies.txt  # mode 600: YouTube cookies for yt-dlp
```
