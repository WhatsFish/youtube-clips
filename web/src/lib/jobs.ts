import { promises as fs } from "fs";
import path from "path";

const RENDERS_DIR = process.env.RENDERS_DIR ?? "/data/renders";

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
};

export type Job = {
  id: string;
  profileName: string;
  title: string | null;
  description: string | null;
  tags: string[];
  shotCount: number;
  edl: Edl | null;
  renderSizeBytes: number | null;
  renderMtime: Date | null;
};

// Pre-Profile-stamping renders are assumed to belong to the only Profile
// that existed at the time. Update this if a second Profile is seeded
// before all legacy renders get backfilled.
const DEFAULT_PROFILE_NAME = "tech-insights-cn";

/**
 * Phase 2 prototype storage: each subdir under RENDERS_DIR is keyed by
 * the source YouTube video_id. A subdir counts as a "job" iff it has
 * a render.mp4. Future Phase 2-final pipeline will move this enumeration
 * into Postgres; for now reading the filesystem is the source of truth.
 */
export async function listJobs(): Promise<Job[]> {
  let entries: string[];
  try {
    entries = await fs.readdir(RENDERS_DIR);
  } catch {
    return [];
  }
  const loaded = await Promise.all(
    entries.map((id) => loadJob(id).catch(() => null)),
  );
  return loaded
    .filter((j): j is Job => j !== null)
    .sort((a, b) => {
      const ta = a.renderMtime?.getTime() ?? 0;
      const tb = b.renderMtime?.getTime() ?? 0;
      return tb - ta;
    });
}

export async function loadJob(id: string): Promise<Job | null> {
  const dir = path.join(RENDERS_DIR, id);
  const renderPath = path.join(dir, "render.mp4");
  const edlPath = path.join(dir, "edl.json");

  let renderStat;
  try {
    renderStat = await fs.stat(renderPath);
  } catch {
    return null;
  }

  let edl: Edl | null = null;
  try {
    const raw = await fs.readFile(edlPath, "utf-8");
    edl = JSON.parse(raw) as Edl;
  } catch {
    edl = null;
  }

  return {
    id,
    profileName: edl?.profile_name ?? DEFAULT_PROFILE_NAME,
    title: edl?.title_zh ?? null,
    description: edl?.description_zh ?? null,
    tags: edl?.tags_zh ?? [],
    shotCount: edl?.shots?.length ?? 0,
    edl,
    renderSizeBytes: renderStat.size,
    renderMtime: renderStat.mtime,
  };
}

export function groupByProfile(jobs: Job[]): Map<string, Job[]> {
  const m = new Map<string, Job[]>();
  for (const j of jobs) {
    if (!m.has(j.profileName)) m.set(j.profileName, []);
    m.get(j.profileName)!.push(j);
  }
  return m;
}

export function fmtMb(bytes: number | null): string {
  if (bytes === null) return "—";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtTime(d: Date | null): string {
  if (!d) return "—";
  return d.toLocaleString("zh-CN", {
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
