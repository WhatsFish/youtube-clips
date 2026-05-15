import { NextResponse } from "next/server";
import { bulkRejectOldPending } from "@/lib/topics";

export const dynamic = "force-dynamic";

/** POST /api/topics/bulk-reject  body: { profileName, olderThanDays }
 *  Marks every pending topic for the named profile older than N days as
 *  'rejected'. Returns { count } affected rows. Used by the /topics page
 *  cleanup button to prune long-stale candidate lists. */
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    profileName?: string;
    olderThanDays?: number;
  };
  const profileName = body.profileName?.trim();
  const days = body.olderThanDays;
  if (!profileName) {
    return NextResponse.json({ error: "profileName required" }, { status: 400 });
  }
  if (typeof days !== "number" || days < 1 || days > 365) {
    return NextResponse.json(
      { error: "olderThanDays must be 1-365" },
      { status: 400 },
    );
  }
  try {
    const count = await bulkRejectOldPending(profileName, days);
    return NextResponse.json({ ok: true, count });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}
