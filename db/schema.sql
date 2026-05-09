-- youtube-clips schema. Phase 1 ships only the `profiles` table (a single
-- channel-strategy config blob); Phase 2 adds topics / sources / jobs /
-- outputs / feedback. Re-applying the file is idempotent.
--
-- Apply by running ./db/bootstrap.sh.

-- Channel strategies. Each row is one "channel concept" — source platforms,
-- output platforms, languages, editing style, branding. Pipeline reads
-- config_jsonb to decide everything; downstream code is profile-agnostic.
CREATE TABLE IF NOT EXISTS profiles (
  id           BIGSERIAL    PRIMARY KEY,
  name         TEXT         NOT NULL UNIQUE,
  description  TEXT,
  config_jsonb JSONB        NOT NULL,
  active       BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
