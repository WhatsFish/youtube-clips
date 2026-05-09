# youtube-clips — runbook

Day-to-day operational guide. **Design rationale lives in [PLAN.md](PLAN.md);** this file is "how do I run it."

---

## What it does

Given a topic and a Profile, produces a Chinese-language commentary mp4 from an English-language YouTube source video. The Profile drives voice / tone / verbal tics / forbidden phrases / disclaimer; same source under two Profiles produces two distinctly-styled outputs.

**No auto-publish.** You upload to Bilibili / YouTube / Douyin / TikTok yourself. The web UI at `/youtube-clips/` is for previewing and downloading.

---

## Make one video

### Full chain (recommended)

```bash
source ~/.config/youtube-clips.env
.venv/bin/python scripts/produce.py \
  --topic "Federal Reserve rate decision" \
  --profile finance-insights-cn
```

That runs **discover → download → EDL → render** end-to-end and prints a URL to the result.

### When you already know the source video

```bash
.venv/bin/python scripts/produce.py \
  --video-id YZ15suxtiaM \
  --profile finance-insights-cn
```

Skips discovery; pulls title/channel via `videos.list` (1 quota unit).

### Other options

| Flag | Default | Effect |
|---|---|---|
| `--profile` | `tech-insights-cn` | Which Profile (channel) to use |
| `--prompt-version` | `latest` | Use a specific prompt version, e.g. `2` to A/B against v3 |
| `--title` / `--channel` | (looked up) | Override metadata when using `--video-id` |
| `--force-download` | off | Re-download even if `source.mp4` already cached |

---

## Cookies (read this before everything else fails)

YouTube's anti-bot **rejects requests from this Azure VM's IP within hours** of a cookie refresh. This is the single biggest operational drag on the project.

### Symptom

```
ERROR: [youtube] ...: Sign in to confirm you're not a bot.
```

### Fix

1. On your **local browser** (not the VM), make sure you're signed into YouTube
2. Use a `cookies.txt` extension to export cookies for `youtube.com`
3. Copy the file to the VM:
   ```bash
   scp /path/to/cookies.txt liharr@ai-native.japaneast.cloudapp.azure.com:~/.config/youtube-clips-cookies.txt
   ```
4. Re-run `produce.py`

`produce.py` prints the cookie file's age before the download stage so you can see at a glance whether to refresh first.

### Why this happens

Azure datacenter IPs have terrible reputation with YouTube. Even fresh, structurally-valid cookies (containing `__Secure-3PSID` etc.) get tossed once they've been used a few times from this VM. The right long-term fixes are residential proxy / local-download-+-rsync / VPN — see PLAN.md "productionization debt" for the deferred decision.

---

## Watch / download a render

`https://ai-native.japaneast.cloudapp.azure.com/youtube-clips/`

Renders are grouped by Profile. Click a card to see the player + shot list + EDL JSON + download buttons.

---

## Add a new Profile

Two pieces:

**1. Insert the row** — copy `db/seeds/insert-finance-insights-cn.sql`, change the values, apply:

```bash
source ~/.config/youtube-clips.env
docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
  traffic-monitor-db-1 \
  psql -h localhost -U youtube_clips -d youtube_clips \
  < db/seeds/insert-<your-name>.sql
```

**2. Use it** — `produce.py --profile <your-name> --topic "..."`. No code change needed.

The Profile fields that drive style are documented in PLAN.md "Profile model: three dimensions of style"; the relevant ones are under `channel.*` in `config_jsonb` (`channel_position`, `tone`, `verbal_tics`, `forbidden_phrases`, `must_include_disclaimer`, `disclaimer_zh`).

---

## Iterate the prompt

The EDL agent's prompt is `prompts/edl-continuous.v3.md`. The source-discovery prompt is `prompts/source-pick.v1.md`.

**Don't edit a frozen version in place.** Copy to the next version and bump the filename:

```bash
cp prompts/edl-continuous.v3.md prompts/edl-continuous.v4.md
# ...edit v4...
```

`produce.py` defaults to the highest version. Pass `--prompt-version 3` if you want to A/B against a previous one. Every saved EDL stamps the prompt version that produced it (`edl_jsonb.prompt_template_version`), so you can always trace back.

---

## Where things live

| | Path |
|---|---|
| Code | `/home/liharr/src/youtube-clips/` |
| Working data (raw + clips + outputs) | `/video/youtube-clips/` |
| Secrets | `~/.config/youtube-clips.env` (mode 600) |
| YouTube cookies | `~/.config/youtube-clips-cookies.txt` (mode 600) |
| Cron heartbeats | `~/.local/share/cron-heartbeats/youtube-clips-*` |
| nginx route | `/etc/nginx/snippets/youtube-clips.conf` |
| GitHub repo | [`WhatsFish/youtube-clips`](https://github.com/WhatsFish/youtube-clips) |
| Web URL | `https://ai-native.japaneast.cloudapp.azure.com/youtube-clips/` |
| /status group | `https://ai-native.japaneast.cloudapp.azure.com/status` (search "youtube-clips") |

---

## Cron

| When | What |
|---|---|
| `30 5 * * *` | `cleanup-cron.sh` deletes raw downloads older than 7 days |

The main pipeline (discover → render) is **not on cron** because the cookie/IP issue makes autonomous runs unreliable. Run `produce.py` manually for now.

---

## Common operations

### Backfill DB from filesystem

If a render exists on disk but isn't in the DB (e.g. an out-of-band run, or a fresh DB):

```bash
source ~/.config/youtube-clips.env
.venv/bin/python scripts/backfill-db.py
```

Idempotent — skips renders that already have an `outputs` row.

### Re-render an existing EDL

```bash
.venv/bin/python scripts/edl-render.py -- <video_id>
```

(Note: produce.py does discover→download→EDL→render. If you only want render, call edl-render.py directly. Same goes for re-doing just the EDL.)

### Refresh a Profile in DB

`db/seeds/insert-<name>.sql` ends with an `ON CONFLICT DO UPDATE`, so re-applying it overwrites the row's `config_jsonb`. Useful when iterating on Profile config.

### Pick a different voice / try a different Profile field

Edit the SQL file, re-apply (above), re-run `produce.py`. No code change, no rebuild.

---

## When something fails

| Symptom | Likely fix |
|---|---|
| `Sign in to confirm you're not a bot` | Refresh cookies (see above) |
| `cookies file missing` | Same — first time on this VM, copy the file over |
| `claude exited 1` | `claude` CLI auth — try `claude` interactively to renew |
| `BotWallError` | Same as cookies |
| Web shows "DB error" | `docker ps` — `traffic-monitor-db-1` not running |
| Web shows 0 renders but mp4 exists on disk | Run `scripts/backfill-db.py` |
| /status shows youtube-clips group fail | Check cron output + heartbeats; check container logs (`docker logs youtube-clips-web-1`) |
| ffmpeg slow | Expected on D2s_v3 (2 vCPU). Resize to F4s_v2 if it becomes blocking — PLAN.md notes this is a deferred ~10-min online resize |

---

## What this isn't

This system **does not** auto-publish. It produces mp4s; humans upload them. That's deliberate — the goal is to take production friction out of the operator's day, not to remove the operator's editorial judgment.

It also **does not** do brand-new research. The agents work over external content (YouTube videos) plus your channel's stylistic constraints; they don't generate facts. Treat the output as a draft.
