import { query } from "./db";

export type Shot = {
  narration: string;
  source_start_sec: number;
  purpose?: string;
};

export type Edl = {
  decision: string;
  profile_name?: string;
  decision_reason?: string;
  title_zh?: string;
  description_zh?: string;
  tags_zh?: string[];
  shots?: Shot[];
  prompt_template_version?: string;
  rendered_at?: string;
  topic_id?: number;
  source_id?: number;
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
};

// jobs.edl_jsonb carries a source_id stamp written by edl-prototype.py
// (and by the backfill script for legacy renders). That's the cleanest
// join key from a Job back to its Source — Phase 3 will likely add a
// direct sources_id column on jobs and this join goes away.
const SELECT_RENDERS = `
  SELECT
    o.id              AS output_id,
    o.job_id          AS job_id,
    s.external_id     AS external_id,
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
    COALESCE(jsonb_array_length(j.edl_jsonb -> 'shots'), 0) AS shot_count
  FROM outputs o
  JOIN jobs     j ON j.id = o.job_id
  JOIN profiles p ON p.id = j.profile_id
  LEFT JOIN sources s
       ON s.id = NULLIF(j.edl_jsonb ->> 'source_id', '')::bigint
  WHERE o.status = 'ready'
`;

function rowToJob(r: Row): Job {
  return {
    id: r.external_id,
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
  };
}

export async function listJobs(): Promise<Job[]> {
  // The LEFT JOIN above falls back to NULL external_id if no Source row
  // matches; for those, we recover the id from the EDL's source_id field
  // (set by edl-prototype/backfill). Belt-and-suspenders pattern until
  // sources↔jobs gets a direct foreign key in a future migration.
  const rows = await query<Row>(
    `${SELECT_RENDERS} ORDER BY o.ready_at DESC NULLS LAST`,
  );
  return rows.map(rowToJob).map((j) => {
    if (j.id) return j;
    const fromEdl = (j.edl as Edl | null)?.source_id;
    return { ...j, id: fromEdl ? String(fromEdl) : `output-${j.outputId}` };
  });
}

export async function loadJob(id: string): Promise<Job | null> {
  // `id` is the YouTube video_id (Source.external_id). Look up the most
  // recent `ready` Output for any Job whose EDL stamped that source_id.
  const rows = await query<Row>(
    `${SELECT_RENDERS}
       AND s.external_id = $1
     ORDER BY o.ready_at DESC NULLS LAST
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
