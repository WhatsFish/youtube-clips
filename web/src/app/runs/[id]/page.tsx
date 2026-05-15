import Link from "next/link";
import { notFound } from "next/navigation";
import { loadRun, loadRunEvents, loadRunCost } from "@/lib/runs";
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
  const [events, cost] = await Promise.all([
    loadRunEvents(runId),
    loadRunCost(runId),
  ]);

  // next/link auto-prepends basePath ("/youtube-clips"); don't add it
  // manually or you get /youtube-clips/youtube-clips/... → 404.
  const jobHref = run.urlSlug
    ? `/jobs/${encodeURIComponent(run.urlSlug)}`
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

      {cost.doubaoCalls > 0 && (
        <section className="mb-6 border border-amber-200 dark:border-amber-900 bg-amber-50/40 dark:bg-amber-950/20 rounded-md p-4">
          <div className="text-xs text-neutral-500 uppercase tracking-wider mb-1">
            Doubao 视频生成成本（估）
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div>
              <span className="font-mono font-medium">
                ${cost.doubaoUsd.toFixed(3)}
              </span>
              <span className="text-neutral-500 ml-1">
                ≈ ¥{(cost.doubaoUsd * 7.2).toFixed(2)}
              </span>
            </div>
            <div className="text-neutral-600 dark:text-neutral-400">
              {cost.doubaoCalls} 次调用 · {cost.doubaoSeconds.toFixed(0)}s 视频
            </div>
          </div>
        </section>
      )}

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
