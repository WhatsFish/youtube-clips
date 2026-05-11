import { query } from "./db";

export type Shot = {
  narration: string;
  source_start_sec: number;
  source_idx?: number;  // present from EDL prompt v4 onward; defaults to 0 (primary)
  purpose?: string;
};

export type EdlSource = {
  video_id: string;
  title?: string;
  channel?: string;
  role?: "primary" | "supplement";
};

export type Edl = {
  decision: string;
  profile_name?: string;
  decision_reason?: string;
  title_zh?: string;
  description_zh?: string;
  tags_zh?: string[];
  shots?: Shot[];
  // v4+: multi-source EDLs carry the full sources array; older single-
  // source EDLs only have the singular source_id below.
  sources?: EdlSource[];
  prompt_template_version?: string;
  rendered_at?: string;
  topic_id?: number;
  source_id?: number;        // primary source's DB id (always set)
  source_ids?: number[];     // v4+: every source's DB id, primary first
  job_id?: number;
};

/**
 * One render = one Output row joined back to its Job + Source. We surface
 * the source video_id (Source.external_id) as the public-facing slug for
 * URLs because that's what nginx maps under /youtube-clips/media/. The
 * underlying numeric output_id is kept around for joins (feedback, etc.)
 * but isn't shown in the UI.
 */
export type Job = {
  id: string;                     // source.external_id (the YouTube video id)
  outputId: number;
  jobId: number;
  profileName: string;
  title: string | null;
  description: string | null;
  tags: string[];
  shotCount: number;
  edl: Edl | null;
  renderSizeBytes: number | null;
  renderMtime: Date | null;
  durationSec: number | null;
  platform: string;
  aspectRatio: string;
  language: string;
  renderCount: number;            // total Outputs ever produced for this (source, profile)
};

type Row = {
  output_id: number;
  job_id: number;
  external_id: string;
  profile_name: string;
  title: string | null;
  description: string | null;
  tags: string[] | null;
  platform: string;
  aspect_ratio: string;
  language: string;
  duration_sec: number | null;
  file_size_bytes: number | null;
  ready_at: Date | null;
  edl_jsonb: Edl | null;
  shot_count: number;
  render_count: string;  // Postgres COUNT(*) returns a bigint; pg lib gives us a string
  url_slug: string | null;  // producer mode stamps a readable slug; null for commentary/synthesis
};

// One render = one Output row. But re-running edl-render.py overwrites
// render.mp4 in place under the primary source's directory, so multiple
// Output rows for the same source all link to the same physical file.
// The home page should therefore show one card per (source, profile),
// pointing at the most recent Output. We surface a `render_count` so
// older versions stay visible as a small "v3" badge — they're still in
// the DB for debug, just not separate cards.
//
// jobs.edl_jsonb carries a source_id stamp written by edl-prototype.py
// (and by the backfill script for legacy renders). That's the cleanest
// join key from a Job back to its Source — Phase 3 will likely add a
// direct sources.id column on jobs and this join goes away.
const SELECT_RENDERS = `
  WITH ranked AS (
    SELECT
      o.id              AS output_id,
      o.job_id          AS job_id,
      s.external_id     AS external_id,
      j.edl_jsonb ->> 'url_slug' AS url_slug,
      p.name            AS profile_name,
      o.title           AS title,
      o.description     AS description,
      o.tags            AS tags,
      o.platform        AS platform,
      o.aspect_ratio    AS aspect_ratio,
      o.language        AS language,
      o.duration_sec    AS duration_sec,
      o.file_size_bytes AS file_size_bytes,
      o.ready_at        AS ready_at,
      j.edl_jsonb       AS edl_jsonb,
      COALESCE(jsonb_array_length(j.edl_jsonb -> 'shots'), 0) AS shot_count,
      ROW_NUMBER() OVER (
        PARTITION BY COALESCE(
          j.edl_jsonb ->> 'url_slug',
          s.external_id,
          'orphan-' || o.id::text
        ), p.name
        ORDER BY o.ready_at DESC NULLS LAST, o.id DESC
      ) AS rn,
      COUNT(*) OVER (
        PARTITION BY COALESCE(
          j.edl_jsonb ->> 'url_slug',
          s.external_id,
          'orphan-' || o.id::text
        ), p.name
      ) AS render_count
    FROM outputs o
    JOIN jobs     j ON j.id = o.job_id
    JOIN profiles p ON p.id = j.profile_id
    LEFT JOIN sources s
         ON s.id = NULLIF(j.edl_jsonb ->> 'source_id', '')::bigint
    WHERE o.status = 'ready'
  )
  SELECT * FROM ranked WHERE rn = 1
`;

function rowToJob(r: Row): Job {
  return {
    // URL routing key: producer mode stamps `url_slug` directly; older
    // commentary/synthesis renders fall back to the source's external_id
    // (which by convention is also the on-disk directory name).
    id: r.url_slug || r.external_id,
    outputId: r.output_id,
    jobId: r.job_id,
    profileName: r.profile_name,
    title: r.title,
    description: r.description,
    tags: r.tags ?? [],
    shotCount: r.shot_count ?? 0,
    edl: r.edl_jsonb,
    renderSizeBytes: r.file_size_bytes,
    renderMtime: r.ready_at,
    durationSec: r.duration_sec ? Number(r.duration_sec) : null,
    platform: r.platform,
    aspectRatio: r.aspect_ratio,
    language: r.language,
    renderCount: parseInt(r.render_count ?? "1", 10) || 1,
  };
}

export async function listJobs(): Promise<Job[]> {
  // SELECT_RENDERS already collapses to one row per (source, profile) via
  // ROW_NUMBER + WHERE rn = 1; we just sort the survivors by recency for
  // the home page. The LEFT JOIN falls back to NULL external_id if no
  // Source row matches; for those, we recover the id from the EDL's
  // source_id field (set by edl-prototype/backfill). Belt-and-suspenders
  // until sources↔jobs gets a direct foreign key in a future migration.
  const rows = await query<Row>(
    `${SELECT_RENDERS} ORDER BY ready_at DESC NULLS LAST`,
  );
  return rows.map(rowToJob).map((j) => {
    if (j.id) return j;
    const fromEdl = (j.edl as Edl | null)?.source_id;
    return { ...j, id: fromEdl ? String(fromEdl) : `output-${j.outputId}` };
  });
}

export async function loadJob(id: string): Promise<Job | null> {
  // `id` is the YouTube video_id (Source.external_id). The CTE in
  // SELECT_RENDERS already picked the latest Output per (source, profile),
  // so we just filter to that external_id and take the freshest row
  // across all profiles in case the same source was rendered under more
  // than one Profile.
  const rows = await query<Row>(
    `${SELECT_RENDERS}
     AND ($1 IN (url_slug, external_id))
     ORDER BY ready_at DESC NULLS LAST
     LIMIT 1`,
    [id],
  );
  if (rows.length === 0) return null;
  return rowToJob(rows[0]);
}

export function fmtMb(bytes: number | null): string {
  if (bytes === null) return "—";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtTime(d: Date | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleString("zh-CN", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtTimestamp(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export function groupByProfile(jobs: Job[]): Map<string, Job[]> {
  const m = new Map<string, Job[]>();
  for (const j of jobs) {
    if (!m.has(j.profileName)) m.set(j.profileName, []);
    m.get(j.profileName)!.push(j);
  }
  return m;
}
