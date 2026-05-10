import Link from "next/link";
import { notFound } from "next/navigation";
import { loadJob, fmtMb, fmtTime, fmtTimestamp } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export default async function JobDetail({
  params,
}: {
  params: { id: string };
}) {
  const id = decodeURIComponent(params.id);
  const job = await loadJob(id);
  if (!job) notFound();

  const mediaBase = `/youtube-clips/media/${encodeURIComponent(id)}`;
  const sourceUrl = `https://www.youtube.com/watch?v=${id}`;

  return (
    <main className="max-w-4xl mx-auto px-5 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>

      <header className="mt-4 mb-6">
        <h1 className="text-2xl font-semibold tracking-tight mb-2">
          {job.title ?? <span className="font-mono">{id}</span>}
        </h1>
        {job.description ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            {job.description}
          </p>
        ) : null}
      </header>

      <section className="mb-8">
        <video
          controls
          preload="metadata"
          className="w-full rounded-md bg-black aspect-video"
          src={`${mediaBase}/render.mp4`}
        >
          您的浏览器不支持视频播放。
        </video>
      </section>

      <section className="mb-8 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
        <div>
          <div className="text-xs text-neutral-500 uppercase tracking-wider">source</div>
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener"
            className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            YouTube ↗
          </a>
        </div>
        <div>
          <div className="text-xs text-neutral-500 uppercase tracking-wider">size</div>
          <div>{fmtMb(job.renderSizeBytes)}</div>
        </div>
        <div>
          <div className="text-xs text-neutral-500 uppercase tracking-wider">rendered</div>
          <div>{fmtTime(job.renderMtime)}</div>
        </div>
        <div>
          <div className="text-xs text-neutral-500 uppercase tracking-wider">shots</div>
          <div>{job.shotCount}</div>
        </div>
      </section>

      {job.tags.length > 0 ? (
        <section className="mb-8">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
            tags
          </h2>
          <div className="flex flex-wrap gap-2">
            {job.tags.map((t) => (
              <span
                key={t}
                className="text-xs px-2 py-1 bg-neutral-100 dark:bg-neutral-800 rounded"
              >
                {t}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {job.edl?.sources && job.edl.sources.length > 1 ? (
        <section className="mb-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
            sources ({job.edl.sources.length})
          </h2>
          <ol className="space-y-1">
            {job.edl.sources.map((src, i) => (
              <li key={i} className="text-xs flex gap-2">
                <span className="font-mono text-neutral-500">[{i}]</span>
                <span className="font-mono text-neutral-500">{src.role ?? "—"}</span>
                <a
                  className="underline truncate"
                  href={`https://www.youtube.com/watch?v=${src.video_id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {src.title ?? src.video_id}
                </a>
                {src.channel ? (
                  <span className="text-neutral-500">· {src.channel}</span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {job.edl?.shots ? (
        <section className="mb-8">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
            shots
          </h2>
          <ol className="space-y-2">
            {job.edl.shots.map((s, i) => {
              const srcIdx = s.source_idx ?? 0;
              const showSrcLabel = (job.edl?.sources?.length ?? 1) > 1;
              return (
                <li
                  key={i}
                  className="border border-neutral-200 dark:border-neutral-800 rounded-md p-3"
                >
                  <div className="text-xs text-neutral-500 mb-1 flex gap-3">
                    <span>#{i + 1}</span>
                    {showSrcLabel ? (
                      <span className="font-mono">src{srcIdx}</span>
                    ) : null}
                    <span className="font-mono">
                      @ {fmtTimestamp(s.source_start_sec)}
                    </span>
                  </div>
                  <div className="text-sm">{s.narration}</div>
                  {s.purpose ? (
                    <div className="text-xs italic text-neutral-500 mt-1">
                      {s.purpose}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      <section className="mb-8">
        <details>
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
            EDL JSON
          </summary>
          <pre className="text-xs overflow-x-auto bg-neutral-100 dark:bg-neutral-900 p-3 rounded-md mt-2">
            {JSON.stringify(job.edl, null, 2)}
          </pre>
        </details>
      </section>

      <section className="flex gap-3">
        <a
          href={`${mediaBase}/render.mp4`}
          download={`${id}.mp4`}
          className="inline-flex items-center px-4 py-2 text-sm font-medium border border-neutral-300 dark:border-neutral-700 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900"
        >
          ⬇ Download mp4
        </a>
        <a
          href={`${mediaBase}/edl.json`}
          download={`${id}.edl.json`}
          className="inline-flex items-center px-4 py-2 text-sm font-medium border border-neutral-300 dark:border-neutral-700 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900"
        >
          ⬇ Download edl.json
        </a>
      </section>
    </main>
  );
}
