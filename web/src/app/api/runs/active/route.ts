import { NextResponse } from "next/server";
import { listActiveRuns } from "@/lib/runs";

export const dynamic = "force-dynamic";

export async function GET() {
  const runs = await listActiveRuns();
  return NextResponse.json({ runs });
}
