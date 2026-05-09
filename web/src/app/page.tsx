import Link from "next/link";
import { query } from "@/lib/db";
import { listJobs, fmtMb, fmtTime } from "@/lib/jobs";

export const dynamic = "force-dynamic";

type ProfileRow = {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
};

export default async function Home() {
  let profiles: ProfileRow[] = [];
  let dbError: string | null = null;
  try {
    profiles = await query<ProfileRow>(
      `SELECT id, name, description, active FROM profiles ORDER BY id`,
    );
  } catch (e) {
    dbError = e instanceof Error ? e.message : String(e);
  }
  const jobs = await listJobs();

  return (
    <main className="max-w-3xl mx-auto px-5 py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">youtube-clips</h1>
        <p className="text-sm text-neutral-500">
          Profile-based multi-platform video remix pipeline. Phase 2 prototype renders
          live below.
        </p>
      </header>

      <section className="mb-10">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
          Recent renders
        </h2>
        {jobs.length === 0 ? (
          <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-6 text-sm text-neutral-500">
            <p>No renders yet. Run <code className="text-xs">scripts/edl-prototype.py</code> + <code className="text-xs">scripts/edl-render.py</code> to produce one.</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {jobs.map((j) => (
              <li
                key={j.id}
                className="border border-neutral-200 dark:border-neutral-800 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900 transition"
              >
                <Link
                  href={`/jobs/${encodeURIComponent(j.id)}`}
                  className="block p-4"
                >
                  <div className="font-medium text-base mb-1">
                    {j.title ?? <span className="font-mono text-sm">{j.id}</span>}
                  </div>
                  {j.description ? (
                    <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-2 line-clamp-2">
                      {j.description}
                    </p>
                  ) : null}
                  <div className="text-xs text-neutral-500 flex flex-wrap gap-x-4 gap-y-1">
                    <span>{j.shotCount} shots</span>
                    <span>{fmtMb(j.renderSizeBytes)}</span>
                    <span>{fmtTime(j.renderMtime)}</span>
                    <span className="font-mono">{j.id}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
          Profiles
        </h2>
        {dbError ? (
          <div className="border border-red-300 dark:border-red-800 rounded-md p-4 text-sm">
            <p className="font-medium text-red-700 dark:text-red-400 mb-1">DB error</p>
            <pre className="text-xs whitespace-pre-wrap">{dbError}</pre>
          </div>
        ) : profiles.length === 0 ? (
          <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-6 text-sm text-neutral-500">
            <p>No profiles seeded.</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {profiles.map((p) => (
              <li
                key={p.id}
                className="border border-neutral-200 dark:border-neutral-800 rounded-md p-4"
              >
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-sm">{p.name}</span>
                  {p.active ? null : (
                    <span className="text-xs text-neutral-500">(inactive)</span>
                  )}
                </div>
                {p.description ? (
                  <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                    {p.description}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
