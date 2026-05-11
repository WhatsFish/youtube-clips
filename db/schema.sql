-- youtube-clips schema. Idempotent: safe to re-run via ./db/bootstrap.sh
-- when adding tables or indexes. Phase 1 shipped only `profiles`; Phase 2
-- adds the rest of the pipeline state — topics, sources, jobs, outputs,
-- feedback.
--
-- Design notes:
--   * IDs are BIGSERIAL across the board; keys are project-internal.
--   * Profile config travels as JSONB (channel-strategy blob) so adding a
--     new platform / language / style doesn't require schema changes.
--   * Enum-like fields use CHECK constraints rather than Postgres ENUMs:
--     CHECK is cheap to evolve (just edit the constraint) where ENUM types
--     require type-altering migrations.
--   * Source platform is plain TEXT (not a constraint) — yt-dlp covers
--     1700+ sites; we don't want to gate which one a Profile uses.

-- Channel strategies. One row per channel concept.
CREATE TABLE IF NOT EXISTS profiles (
  id           BIGSERIAL    PRIMARY KEY,
  name         TEXT         NOT NULL UNIQUE,
  description  TEXT,
  config_jsonb JSONB        NOT NULL,
  active       BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Topics — selection items. The agent proposes; the operator approves.
-- A topic owns the downstream pipeline for that production cycle.
CREATE TABLE IF NOT EXISTS topics (
  id           BIGSERIAL    PRIMARY KEY,
  profile_id   BIGINT       NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  title        TEXT         NOT NULL,
  description  TEXT,
  keywords     TEXT[]       NOT NULL DEFAULT '{}',
  status       TEXT         NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected','done')),
  source       TEXT         NOT NULL DEFAULT 'agent'
    CHECK (source IN ('agent','human')),
  generated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  approved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS topics_profile_status ON topics (profile_id, status, generated_at DESC);

-- Sources — raw video material discovered for a topic. One topic can
-- harvest from many sources, and a single source may be reused across
-- topics (rare but allowed) — hence the M:N is implicit via topic_id
-- on the join in jobs.edl rather than a sources↔topics table.
--
-- transcript_jsonb shape:
--   { "original":   "<text>",
--     "translated": "<text>",        -- optional, only if cross-lang
--     "words": [{"t": 12.34, "w": "..."}, ...]   -- word-level timestamps
--   }
CREATE TABLE IF NOT EXISTS sources (
  id              BIGSERIAL    PRIMARY KEY,
  profile_id      BIGINT       NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_platform TEXT         NOT NULL,           -- 'youtube' | 'bilibili' | ...
  external_id     TEXT         NOT NULL,           -- platform's video id
  url             TEXT         NOT NULL,
  title           TEXT,
  channel         TEXT,
  duration_sec    INT,
  source_language TEXT,                            -- ISO-639-1; nullable when unknown
  transcript_jsonb JSONB,
  metadata_jsonb  JSONB,                           -- views, publish date, tags, etc.
  download_path   TEXT,                            -- /video/youtube-clips/raw/<id>/...
  downloaded_at   TIMESTAMPTZ,
  ttl_delete_at   TIMESTAMPTZ,                     -- when the cleanup cron should drop the file
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (source_platform, external_id)
);
CREATE INDEX IF NOT EXISTS sources_profile_created ON sources (profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS sources_ttl ON sources (ttl_delete_at) WHERE download_path IS NOT NULL;

-- Jobs — one render request. The EDL JSON is the single source of truth
-- for what should be in the output: clip list (referencing sources.id +
-- timestamps), narration script, music cues, text overlays.
--
-- parent_job_id captures regeneration lineage: when the operator says
-- "再生成一版" with a feedback note, the new job links back here.
CREATE TABLE IF NOT EXISTS jobs (
  id             BIGSERIAL    PRIMARY KEY,
  topic_id       BIGINT       NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  profile_id     BIGINT       NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  edl_jsonb      JSONB,                            -- nullable until the EDL agent runs
  parent_job_id  BIGINT       REFERENCES jobs(id) ON DELETE SET NULL,
  status         TEXT         NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','planning','rendering','completed','failed')),
  error_jsonb    JSONB,
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  started_at     TIMESTAMPTZ,
  completed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS jobs_topic_status ON jobs (topic_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs (status, created_at DESC);

-- Outputs — one job → N platform variants. Phase 2 produces a single
-- variant per job (16:9 Bilibili long); Phase 3 fans out to 4-5 platforms
-- without schema change.
CREATE TABLE IF NOT EXISTS outputs (
  id              BIGSERIAL    PRIMARY KEY,
  job_id          BIGINT       NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  platform        TEXT         NOT NULL,           -- 'bilibili_long' | 'youtube_shorts' | ...
  aspect_ratio    TEXT         NOT NULL,           -- '16:9' | '9:16' | '1:1'
  language        TEXT         NOT NULL,
  path            TEXT,                            -- /video/youtube-clips/outputs/<job>/...
  duration_sec    NUMERIC(8,3),
  file_size_bytes BIGINT,
  thumbnail_path  TEXT,
  title           TEXT,                            -- per-platform title (different vibes)
  description     TEXT,
  tags            TEXT[]       NOT NULL DEFAULT '{}',
  status          TEXT         NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','rendering','ready','failed')),
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  ready_at        TIMESTAMPTZ,
  UNIQUE (job_id, platform)
);
CREATE INDEX IF NOT EXISTS outputs_job ON outputs (job_id);

-- Feedback — operator's regenerate instructions. Closes the loop with
-- jobs.parent_job_id: "this is the feedback that produced the next job".
CREATE TABLE IF NOT EXISTS feedback (
  id                 BIGSERIAL    PRIMARY KEY,
  job_id             BIGINT       NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  user_text          TEXT         NOT NULL,
  regenerated_job_id BIGINT       REFERENCES jobs(id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS feedback_job ON feedback (job_id, created_at DESC);

-- Runs — one operator-initiated production attempt. Captures the whole
-- lifecycle from discovery (or topic input) through render, including
-- failures that happen before a `jobs` row would exist. `runs` is the
-- parent of `jobs`: a successful run ends with a `job_id` set; a failed
-- run (e.g. discovery skipped, download crashed) ends without one.
--
-- url_slug mirrors the value stamped into jobs.edl_jsonb -> 'url_slug' so
-- the web layer can route /runs/<slug> deterministically before EDL exists.
CREATE TABLE IF NOT EXISTS runs (
  id            BIGSERIAL    PRIMARY KEY,
  profile_id    BIGINT       NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  topic_id      BIGINT       REFERENCES topics(id) ON DELETE SET NULL,
  job_id        BIGINT       REFERENCES jobs(id) ON DELETE SET NULL,
  kind          TEXT         NOT NULL CHECK (kind IN ('commentary','synthesis','producer')),
  topic_title   TEXT         NOT NULL,
  url_slug      TEXT,
  status        TEXT         NOT NULL DEFAULT 'running'
    CHECK (status IN ('running','completed','failed','skipped')),
  current_stage TEXT,
  error_message TEXT,
  started_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS runs_status_started ON runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS runs_url_slug ON runs (url_slug) WHERE url_slug IS NOT NULL;

-- Run events — every stage transition (start / done / fail / skip) within
-- a run. Web polls this table while runs.status = 'running' to render a
-- live timeline. metadata carries stage-specific payload (shot index,
-- file path, error stack, etc.) without rigid schema.
CREATE TABLE IF NOT EXISTS run_events (
  id         BIGSERIAL    PRIMARY KEY,
  run_id     BIGINT       NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  stage      TEXT         NOT NULL,
  status     TEXT         NOT NULL CHECK (status IN ('start','done','fail','skip','info')),
  message    TEXT,
  metadata   JSONB,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS run_events_run_ts ON run_events (run_id, created_at);

-- ============================================================
-- Seed: tech-insights-cn demo Profile
-- ============================================================
-- Phase 2 currently renders one platform variant (Bilibili long, 16:9).
-- Phase 3 will extend output.platforms in this row's config_jsonb (or
-- replace via UPDATE) without schema changes. Re-running this file via
-- bootstrap.sh on an existing DB INSERT-skips the row; to refresh the
-- shape, UPDATE explicitly (see db/seeds/update-tech-insights-cn.sql).
INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'tech-insights-cn',
  'English tech YouTube videos → Chinese Bilibili commentary. Demo Profile for the Phase 2 MVP.',
  '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": ["tech review", "AI news", "developer tools"]
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-YunxiNeural",
      "tts_rate_pct": 15,
      "aspect_ratio": "16:9"
    },
    "style": {
      "template": "continuous_commentary",
      "pacing": "medium",
      "audio_strategy": "ducked_original",
      "source_audio_volume": 0.10,
      "narration_volume": 1.6,
      "caption_strategy": "burn_zh"
    },
    "branding": {
      "intro_path": null,
      "outro_path": null,
      "watermark": null
    },
    "channel": {
      "channel_position": "Bilibili 科技频道 UP 主",
      "tone": "年轻、专业、有态度，可以有 mild hot take",
      "vocabulary": "技术术语直接用，不需要每个名词都解释",
      "verbal_tics": ["划重点", "反常识的是", "这就有意思了", "值得注意的是"],
      "forbidden_phrases": ["大家好欢迎收看", "今天我们要讲", "如有错误欢迎指正"],
      "must_include_disclaimer": false
    },
    "topic_generation_prompt": "你为一个面向中文受众的科技频道选题。候选话题应当聚焦最近 1-2 周内英文科技 YouTube 上有讨论度的内容（AI、开发者工具、新品发布、行业动态），适合做 3-5 分钟连续解说视频。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL：连续中文解说不间断，源视频做 B-roll。8-15 个 shot，每个 shot 是一句中文（15-50 字）配一段源视频画面。语气年轻、专业、有态度。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO NOTHING;
