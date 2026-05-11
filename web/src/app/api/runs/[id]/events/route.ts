import { NextResponse } from "next/server";
import { loadRun, loadRunEvents } from "@/lib/runs";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { id: string } },
) {
  const runId = parseInt(params.id, 10);
  if (!Number.isFinite(runId)) {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  const [run, events] = await Promise.all([
    loadRun(runId),
    loadRunEvents(runId),
  ]);
  if (!run) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ run, events });
}
