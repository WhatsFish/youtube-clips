import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Operator approved the script draft. Stamps `script_approved_at`; a host-
 *  side cron polls every minute, atomically claims the row, and runs
 *  produce-render.py for it. We DON'T flip status to 'rendering' here so
 *  the cron's atomic claim (UPDATE…RETURNING with SKIP LOCKED) stays the
 *  single source of truth for "this job started rendering at T". */
export async function POST(
  _req: Request,
  { params }: { params: { id: string } },
) {
  const id = parseInt(params.id, 10);
  if (!Number.isFinite(id)) {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  const rows = await query<{ id: number; status: string }>(
    `UPDATE jobs
        SET script_approved_at = NOW()
      WHERE id = $1 AND status IN ('script_draft','rejected')
      RETURNING id, status`,
    [id],
  );
  if (rows.length === 0) {
    return NextResponse.json(
      { error: "job not in a state that can be approved" },
      { status: 409 },
    );
  }
  return NextResponse.json({ ok: true, jobId: id });
}
