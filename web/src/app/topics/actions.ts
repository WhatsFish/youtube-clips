"use server";

import { revalidatePath } from "next/cache";
import { query } from "@/lib/db";
import type { TopicStatus } from "@/lib/topics";

const ALLOWED_STATUSES: TopicStatus[] = ["pending", "approved", "rejected", "done"];

export async function addTopic(formData: FormData) {
  const profileId = parseInt(String(formData.get("profile_id") ?? ""), 10);
  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim() || null;
  const keywordsRaw = String(formData.get("keywords") ?? "").trim();
  const keywords = keywordsRaw
    ? keywordsRaw.split(",").map((k) => k.trim()).filter(Boolean)
    : [];

  if (!Number.isFinite(profileId) || profileId <= 0) {
    throw new Error("invalid profile_id");
  }
  if (!title) {
    throw new Error("title is required");
  }

  await query(
    `INSERT INTO topics (profile_id, title, description, keywords, status, source)
     VALUES ($1, $2, $3, $4, 'pending', 'human')`,
    [profileId, title, description, keywords],
  );
  revalidatePath("/topics");
}

export async function updateTopicStatus(formData: FormData) {
  const id = parseInt(String(formData.get("id") ?? ""), 10);
  const status = String(formData.get("status") ?? "") as TopicStatus;

  if (!Number.isFinite(id) || id <= 0) throw new Error("invalid id");
  if (!ALLOWED_STATUSES.includes(status)) throw new Error("invalid status");

  // approved_at is set the first time a topic is approved; we don't reset
  // it on later status changes (e.g. approved → done) since the original
  // approval moment is the historically interesting point.
  const setApprovedAt = status === "approved";
  await query(
    `UPDATE topics
        SET status = $1,
            approved_at = COALESCE(approved_at, $2)
      WHERE id = $3`,
    [status, setApprovedAt ? new Date() : null, id],
  );
  revalidatePath("/topics");
}

export async function deleteTopic(formData: FormData) {
  const id = parseInt(String(formData.get("id") ?? ""), 10);
  if (!Number.isFinite(id) || id <= 0) throw new Error("invalid id");

  // Only allow delete if no Job has ever spawned from this Topic. Otherwise
  // we'd orphan the join key in jobs.topic_id (FK is set to NO ACTION here
  // by default, so the DELETE would fail anyway — but giving a friendly
  // error is nicer than a constraint-violation page).
  const result = await query<{ job_count: string }>(
    `SELECT COUNT(*) AS job_count FROM jobs WHERE topic_id = $1`,
    [id],
  );
  if (parseInt(result[0]?.job_count ?? "0", 10) > 0) {
    throw new Error("cannot delete: topic has produce runs attached");
  }

  await query(`DELETE FROM topics WHERE id = $1`, [id]);
  revalidatePath("/topics");
}
