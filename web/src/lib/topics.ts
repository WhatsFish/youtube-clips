import { query } from "./db";

export type TopicStatus = "pending" | "approved" | "rejected" | "done";

export type Topic = {
  id: number;
  profileId: number;
  profileName: string;
  title: string;
  description: string | null;
  status: TopicStatus;
  source: "agent" | "human";
  metadata: {
    suggested_angle?: string;
    reasoning?: string;
    source_feed?: string;
    source_link?: string;
    discovered_at?: string;
  } | null;
  generatedAt: Date | string;
  approvedAt: Date | string | null;
  // True if a completed job exists for this topic_id. Lets the UI mark
  // approved topics as either "approved waiting" or "approved + rendered".
  rendered: boolean;
  // Slug of the most recent rendered output, if any — for linking to /jobs/<slug>
  renderedSlug: string | null;
};

type Row = {
  id: number;
  profile_id: number;
  profile_name: string;
  title: string;
  description: string | null;
  status: string;
  source: string;
  metadata: Topic["metadata"];
  generated_at: Date;
  approved_at: Date | null;
  rendered: boolean | null;
  rendered_slug: string | null;
};

function rowToTopic(r: Row): Topic {
  return {
    id: r.id,
    profileId: r.profile_id,
    profileName: r.profile_name,
    title: r.title,
    description: r.description,
    status: r.status as TopicStatus,
    source: r.source as Topic["source"],
    metadata: r.metadata,
    generatedAt: r.generated_at,
    approvedAt: r.approved_at,
    rendered: Boolean(r.rendered),
    renderedSlug: r.rendered_slug,
  };
}

// Topics joined with the latest completed job for the same topic_id, if
// any exists. `rendered` and `rendered_slug` come from that join so the
// UI can show "approved & rendered" vs "approved waiting" inline.
const SELECT_TOPIC = `
  SELECT t.id, t.profile_id, t.title, t.description, t.status, t.source,
         t.metadata, t.generated_at, t.approved_at,
         p.name AS profile_name,
         (latest_job.id IS NOT NULL) AS rendered,
         latest_job.url_slug         AS rendered_slug
    FROM topics t
    JOIN profiles p ON p.id = t.profile_id
    LEFT JOIN LATERAL (
      SELECT j.id, j.edl_jsonb ->> 'url_slug' AS url_slug
        FROM jobs j
        WHERE j.topic_id = t.id AND j.status = 'completed'
        ORDER BY j.id DESC LIMIT 1
    ) latest_job ON TRUE
`;

export async function listPendingTopics(): Promise<Topic[]> {
  const rows = await query<Row>(
    `${SELECT_TOPIC}
     WHERE t.status = 'pending'
     ORDER BY t.generated_at DESC`,
  );
  return rows.map(rowToTopic);
}

/** Approved topics — both those waiting for production and those already
 *  rendered. UI sections can split by `rendered` flag. */
export async function listApprovedTopics(): Promise<Topic[]> {
  const rows = await query<Row>(
    `${SELECT_TOPIC}
     WHERE t.status IN ('approved','done')
     ORDER BY rendered ASC, t.approved_at DESC NULLS LAST, t.id DESC`,
  );
  return rows.map(rowToTopic);
}

export async function countPendingTopics(): Promise<number> {
  const rows = await query<{ n: string }>(
    `SELECT COUNT(*)::text AS n FROM topics WHERE status = 'pending'`,
  );
  return parseInt(rows[0]?.n ?? "0", 10);
}

export async function loadTopic(id: number): Promise<Topic | null> {
  const rows = await query<Row>(`${SELECT_TOPIC} WHERE t.id = $1`, [id]);
  return rows[0] ? rowToTopic(rows[0]) : null;
}

export async function countApprovedTopics(): Promise<{ waiting: number; rendered: number }> {
  const rows = await query<{ waiting: string; rendered: string }>(
    `SELECT
       COUNT(*) FILTER (WHERE j.id IS NULL)::text AS waiting,
       COUNT(*) FILTER (WHERE j.id IS NOT NULL)::text AS rendered
       FROM topics t
       LEFT JOIN LATERAL (
         SELECT 1 AS id FROM jobs WHERE topic_id = t.id AND status='completed' LIMIT 1
       ) j ON TRUE
       WHERE t.status IN ('approved','done')`,
  );
  return {
    waiting: parseInt(rows[0]?.waiting ?? "0", 10),
    rendered: parseInt(rows[0]?.rendered ?? "0", 10),
  };
}

export async function setTopicStatus(
  id: number,
  status: "approved" | "rejected",
): Promise<void> {
  const approvedClause =
    status === "approved"
      ? ", approved_at = NOW()"
      : "";
  await query(
    `UPDATE topics SET status = $1${approvedClause} WHERE id = $2`,
    [status, id],
  );
}

/** Bulk-reject all pending topics for one profile older than N days.
 *  Used by the "清理 >Nd" button on the /topics page. Returns affected count. */
export async function bulkRejectOldPending(
  profileName: string,
  olderThanDays: number,
): Promise<number> {
  const rows = await query<{ id: number }>(
    `UPDATE topics t
        SET status = 'rejected'
       FROM profiles p
      WHERE t.profile_id = p.id
        AND p.name = $1
        AND t.status = 'pending'
        AND t.generated_at < NOW() - ($2::int * INTERVAL '1 day')
    RETURNING t.id`,
    [profileName, olderThanDays],
  );
  return rows.length;
}
