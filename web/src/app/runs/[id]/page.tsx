import Link from "next/link";
import { notFound } from "next/navigation";
import { loadRun, loadRunEvents } from "@/lib/runs";
import RunTimeline from "@/components/RunTimeline";

export const dynamic = "force-dynamic";

export default async function RunDetail({
  params,
}: {
  params: { id: string };
}) {
  const runId = parseInt(params.id, 10);
  if (!Number.isFinite(runId)) notFound();
  const run = await loadRun(runId);
  if (!run) notFound();
  const events = await loadRunEvents(runId);

  const jobHref = run.urlSlug
    ? `/youtube-clips/jobs/${encodeURIComponent(run.urlSlug)}`
    : null;

  return (
    <main className="max-w-4xl mx-auto px-5 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>

      <header className="mt-4 mb-6">
        <div className="text-xs text-neutral-500 uppercase tracking-wider mb-1">
          run #{run.id} · {run.profileName} · {run.kind}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {run.topicTitle}
        </h1>
        {run.urlSlug && (
          <div className="mt-2 text-sm text-neutral-500">
            slug: <span className="font-mono">{run.urlSlug}</span>
          </div>
        )}
      </header>

      <RunTimeline initialRun={run} initialEvents={events} />

      {run.status === "completed" && jobHref && (
        <section className="mt-8 pt-6 border-t border-neutral-200 dark:border-neutral-800">
          <Link
            href={jobHref}
            className="inline-flex items-center gap-1 text-sm font-medium hover:underline"
          >
            查看视频 →
          </Link>
        </section>
      )}
    </main>
  );
}
