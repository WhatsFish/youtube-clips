import { query } from "./db";

export type TopicStatus = "pending" | "approved" | "rejected" | "done";
export type TopicSource = "agent" | "human";

export type Topic = {
  id: number;
  profileId: number;
  profileName: string;
  title: string;
  description: string | null;
  keywords: string[];
  status: TopicStatus;
  source: TopicSource;
  generatedAt: Date;
  approvedAt: Date | null;
  // Has any Job ever started for this Topic? (i.e. has produce.py been run)
  jobCount: number;
};

type Row = {
  id: number;
  profile_id: number;
  profile_name: string;
  title: string;
  description: string | null;
  keywords: string[];
  status: TopicStatus;
  source: TopicSource;
  generated_at: Date;
  approved_at: Date | null;
  job_count: string;
};

const SELECT = `
  SELECT
    t.id, t.profile_id, p.name AS profile_name,
    t.title, t.description, t.keywords, t.status, t.source,
    t.generated_at, t.approved_at,
    COUNT(j.id) AS job_count
  FROM topics t
  JOIN profiles p ON p.id = t.profile_id
  LEFT JOIN jobs j ON j.topic_id = t.id
  GROUP BY t.id, p.name
`;

function rowToTopic(r: Row): Topic {
  return {
    id: r.id,
    profileId: r.profile_id,
    profileName: r.profile_name,
    title: r.title,
    description: r.description,
    keywords: r.keywords ?? [],
    status: r.status,
    source: r.source,
    generatedAt: r.generated_at,
    approvedAt: r.approved_at,
    jobCount: parseInt(r.job_count, 10) || 0,
  };
}

export async function listTopics(): Promise<Topic[]> {
  // Order: still-pending first (operator's working set), then by recency.
  // Status sort key uses a CASE so 'pending' floats to the top regardless of
  // the underlying string ordering.
  const rows = await query<Row>(
    `${SELECT}
     ORDER BY
       CASE t.status
         WHEN 'pending'  THEN 0
         WHEN 'approved' THEN 1
         WHEN 'done'     THEN 2
         WHEN 'rejected' THEN 3
       END,
       t.generated_at DESC`,
  );
  return rows.map(rowToTopic);
}

export function groupTopicsByProfile(topics: Topic[]): Map<string, Topic[]> {
  const m = new Map<string, Topic[]>();
  for (const t of topics) {
    if (!m.has(t.profileName)) m.set(t.profileName, []);
    m.get(t.profileName)!.push(t);
  }
  return m;
}

/**
 * Build the produce.py CLI command an operator can paste into their SSH session.
 * Quoting handles topics that contain double quotes or backslashes.
 */
export function produceCommand(profileName: string, topicTitle: string): string {
  const t = topicTitle.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return [
    "set -a && source ~/.config/youtube-clips.env && set +a",
    `cd /home/liharr/src/youtube-clips`,
    `.venv/bin/python scripts/produce.py --topic "${t}" --profile ${profileName}`,
  ].join(" && ");
}
