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
  };
}

const SELECT_TOPIC = `
  SELECT t.id, t.profile_id, t.title, t.description, t.status, t.source,
         t.metadata, t.generated_at, t.approved_at,
         p.name AS profile_name
    FROM topics t
    JOIN profiles p ON p.id = t.profile_id
`;

export async function listPendingTopics(): Promise<Topic[]> {
  const rows = await query<Row>(
    `${SELECT_TOPIC}
     WHERE t.status = 'pending'
     ORDER BY t.generated_at DESC`,
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
