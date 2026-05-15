import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Operator rejected the script. Flips status to 'rejected' and saves
 *  their free-form comment. No regenerate trigger yet — operator can SSH
 *  and re-run produce-script.py with the feedback in mind. A future change
 *  may add a "重写" button that posts the feedback back into the Stage 2
 *  prompt automatically (see the `feedback` table for the lineage shape). */
export async function POST(
  req: Request,
  { params }: { params: { id: string } },
) {
  const id = parseInt(params.id, 10);
  if (!Number.isFinite(id)) {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  const body = (await req.json().catch(() => ({}))) as { feedback?: string };
  const fb = (body.feedback ?? "").trim();
  if (!fb) {
    return NextResponse.json({ error: "feedback required" }, { status: 400 });
  }
  const rows = await query<{ id: number }>(
    `UPDATE jobs
        SET status = 'rejected',
            feedback = $2,
            script_approved_at = NULL
      WHERE id = $1 AND status IN ('script_draft','rejected')
      RETURNING id`,
    [id, fb],
  );
  if (rows.length === 0) {
    return NextResponse.json(
      { error: "job not in a state that can be rejected" },
      { status: 409 },
    );
  }
  return NextResponse.json({ ok: true, jobId: id });
}
