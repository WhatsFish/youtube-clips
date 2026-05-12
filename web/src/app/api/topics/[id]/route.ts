import { NextResponse } from "next/server";
import { setTopicStatus } from "@/lib/topics";

export const dynamic = "force-dynamic";

export async function POST(
  req: Request,
  { params }: { params: { id: string } },
) {
  const id = parseInt(params.id, 10);
  if (!Number.isFinite(id)) {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  const body = (await req.json().catch(() => ({}))) as { action?: string };
  if (body.action !== "approve" && body.action !== "reject") {
    return NextResponse.json(
      { error: "action must be 'approve' or 'reject'" },
      { status: 400 },
    );
  }
  const newStatus = body.action === "approve" ? "approved" : "rejected";
  try {
    await setTopicStatus(id, newStatus);
    return NextResponse.json({ ok: true, status: newStatus });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}
