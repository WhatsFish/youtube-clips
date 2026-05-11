import { query } from "./db";
import type { Run, RunEvent, RunStatus, EventStatus } from "./runs-shared";

export type { Run, RunEvent, RunStatus, EventStatus } from "./runs-shared";
export { stageLabel } from "./runs-shared";

type RunRow = {
  id: number;
  profile_name: string;
  kind: string;
  topic_title: string;
  url_slug: string | null;
  status: string;
  current_stage: string | null;
  error_message: string | null;
  topic_id: number | null;
  job_id: number | null;
  started_at: Date;
  finished_at: Date | null;
};

type EventRow = {
  id: number;
  run_id: number;
  stage: string;
  status: string;
  message: string | null;
  metadata: Record<string, unknown> | null;
  created_at: Date;
};

function rowToRun(r: RunRow): Run {
  return {
    id: r.id,
    profileName: r.profile_name,
    kind: r.kind as Run["kind"],
    topicTitle: r.topic_title,
    urlSlug: r.url_slug,
    status: r.status as RunStatus,
    currentStage: r.current_stage,
    errorMessage: r.error_message,
    topicId: r.topic_id,
    jobId: r.job_id,
    startedAt: r.started_at,
    finishedAt: r.finished_at,
  };
}

function rowToEvent(r: EventRow): RunEvent {
  return {
    id: r.id,
    runId: r.run_id,
    stage: r.stage,
    status: r.status as EventStatus,
    message: r.message,
    metadata: r.metadata,
    createdAt: r.created_at,
  };
}

const SELECT_RUN = `
  SELECT r.id, r.kind, r.topic_title, r.url_slug, r.status,
         r.current_stage, r.error_message, r.topic_id, r.job_id,
         r.started_at, r.finished_at,
         p.name AS profile_name
    FROM runs r
    JOIN profiles p ON p.id = r.profile_id
`;

export async function loadRun(id: number): Promise<Run | null> {
  const rows = await query<RunRow>(`${SELECT_RUN} WHERE r.id = $1`, [id]);
  return rows[0] ? rowToRun(rows[0]) : null;
}

export async function loadRunEvents(id: number): Promise<RunEvent[]> {
  const rows = await query<EventRow>(
    `SELECT id, run_id, stage, status, message, metadata, created_at
       FROM run_events
       WHERE run_id = $1
       ORDER BY id ASC`,
    [id],
  );
  return rows.map(rowToEvent);
}

export async function listActiveRuns(): Promise<Run[]> {
  const rows = await query<RunRow>(
    `${SELECT_RUN} WHERE r.status = 'running' ORDER BY r.started_at DESC`,
  );
  return rows.map(rowToRun);
}

export async function listRecentFailures(limit = 5): Promise<Run[]> {
  const rows = await query<RunRow>(
    `${SELECT_RUN}
       WHERE r.status IN ('failed','skipped')
         AND r.finished_at > NOW() - INTERVAL '24 hours'
       ORDER BY r.finished_at DESC
       LIMIT $1`,
    [limit],
  );
  return rows.map(rowToRun);
}
