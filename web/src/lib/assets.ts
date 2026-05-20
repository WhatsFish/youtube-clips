import fs from "fs";
import path from "path";
import { query } from "./db";

const ARCHIVAL_BASE = "/video/youtube-clips/archival-sources";

export type ArchivalAsset = {
  videoId: string;
  source: "youtube" | "bilibili";
  url: string;
  title: string | null;
  channel: string | null;
  durationSec: number | null;
  uploadDate: string | null;
  fetchedAt: string | null;
  profileName: string | null;
  fileSizeBytes: number;
  usedCount: number;
  backfilled: boolean;
};

type MetaJson = {
  video_id?: string;
  source?: string;
  url?: string;
  title?: string | null;
  channel?: string | null;
  duration_sec?: number | null;
  upload_date?: string | null;
  fetched_at?: string | null;
  profile_name?: string | null;
  backfilled?: boolean;
};

type UsageRow = { video_id: string; uses: number };

async function loadUsageMap(): Promise<Map<string, number>> {
  // Tally references to each archival video_id across all jobs.edl_jsonb.
  // Two shapes: single-clip (shot.archival_video_id) and multi-clip
  // (shot.archival_clips[*].video_id). Sum both into one count per id.
  const rows = await query<UsageRow>(`
    WITH single_use AS (
      SELECT shot->>'archival_video_id' AS video_id, COUNT(*) AS uses
        FROM jobs,
             LATERAL jsonb_array_elements(COALESCE(edl_jsonb->'shots', '[]'::jsonb)) AS shot
       WHERE shot ? 'archival_video_id'
         AND shot->>'archival_video_id' IS NOT NULL
       GROUP BY video_id
    ),
    multi_use AS (
      SELECT clip->>'video_id' AS video_id, COUNT(*) AS uses
        FROM jobs,
             LATERAL jsonb_array_elements(COALESCE(edl_jsonb->'shots', '[]'::jsonb)) AS shot,
             LATERAL jsonb_array_elements(COALESCE(shot->'archival_clips', '[]'::jsonb)) AS clip
       WHERE clip ? 'video_id'
       GROUP BY video_id
    )
    SELECT video_id, SUM(uses)::int AS uses
      FROM (
        SELECT video_id, uses FROM single_use
        UNION ALL
        SELECT video_id, uses FROM multi_use
      ) all_uses
     GROUP BY video_id
  `);
  const map = new Map<string, number>();
  for (const r of rows) {
    if (r.video_id) map.set(r.video_id, Number(r.uses));
  }
  return map;
}

export async function listArchivalCache(): Promise<ArchivalAsset[]> {
  let usage: Map<string, number>;
  try {
    usage = await loadUsageMap();
  } catch {
    usage = new Map();
  }
  const out: ArchivalAsset[] = [];
  for (const source of ["youtube", "bilibili"] as const) {
    const base = path.join(ARCHIVAL_BASE, source);
    let entries: string[];
    try {
      entries = fs.readdirSync(base);
    } catch {
      continue;
    }
    for (const vid of entries) {
      const dir = path.join(base, vid);
      const metaPath = path.join(dir, "meta.json");
      const mp4Path = path.join(dir, "source.mp4");
      let metaText: string;
      try {
        metaText = fs.readFileSync(metaPath, "utf-8");
      } catch {
        continue;
      }
      let meta: MetaJson;
      try {
        meta = JSON.parse(metaText);
      } catch {
        continue;
      }
      let fileSize = 0;
      try {
        fileSize = fs.statSync(mp4Path).size;
      } catch {
        // mp4 missing but meta present — skip the row, it's a stale dir
        continue;
      }
      const videoId = meta.video_id ?? vid;
      out.push({
        videoId,
        source,
        url: meta.url ?? "",
        title: meta.title ?? null,
        channel: meta.channel ?? null,
        durationSec: typeof meta.duration_sec === "number" ? meta.duration_sec : null,
        uploadDate: meta.upload_date ?? null,
        fetchedAt: meta.fetched_at ?? null,
        profileName: meta.profile_name ?? null,
        fileSizeBytes: fileSize,
        usedCount: usage.get(videoId) ?? 0,
        backfilled: Boolean(meta.backfilled),
      });
    }
  }
  // Sort: most recently fetched first.
  out.sort((a, b) => (b.fetchedAt ?? "").localeCompare(a.fetchedAt ?? ""));
  return out;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function fmtDuration(sec: number | null): string {
  if (sec == null) return "—";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return `${m}:${String(r).padStart(2, "0")}`;
}
