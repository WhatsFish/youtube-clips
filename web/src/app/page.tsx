import Link from "next/link";
import { query } from "@/lib/db";
import {
  listJobs,
  groupByProfile,
  fmtMb,
  fmtTime,
  type Job,
} from "@/lib/jobs";

export const dynamic = "force-dynamic";

type ProfileRow = {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
  config_jsonb: { output?: { platforms?: string[] } } | null;
};

const PLATFORM_LABEL: Record<string, string> = {
  bilibili_long: "B 站长",
  bilibili_vertical: "B 站竖屏",
  douyin: "抖音",
  tiktok: "TikTok",
  youtube_long: "YouTube",
  youtube_shorts: "YouTube Shorts",
};

function platformLabel(slug: string): string {
  return PLATFORM_LABEL[slug] ?? slug;
}

export default async function Home() {
  let profiles: ProfileRow[] = [];
  let dbError: string | null = null;
  try {
    profiles = await query<ProfileRow>(
      `SELECT id, name, description, active, config_jsonb FROM profiles ORDER BY id`,
    );
  } catch (e) {
    dbError = e instanceof Error ? e.message : String(e);
  }

  const jobs = await listJobs();
  const jobsByProfile = groupByProfile(jobs);

  // Profiles ordered by DB id; orphan jobs (Profile name not in DB) get a
  // synthetic trailing section so nothing silently disappears.
  const orphanNames = new Set<string>(jobsByProfile.keys());
  for (const p of profiles) orphanNames.delete(p.name);

  return (
    <main className="max-w-3xl mx-auto px-5 py-12">
      <header className="mb-10">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">
          youtube-clips
        </h1>
        <p className="text-sm text-neutral-500">
          Profile-based multi-platform video remix pipeline.
        </p>
      </header>

      {dbError ? (
        <div className="mb-8 border border-red-300 dark:border-red-800 rounded-md p-4 text-sm">
          <p className="font-medium text-red-700 dark:text-red-400 mb-1">
            DB error
          </p>
          <pre className="text-xs whitespace-pre-wrap">{dbError}</pre>
        </div>
      ) : null}

      {profiles.length === 0 && jobs.length === 0 ? (
        <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-6 text-sm text-neutral-500">
          No profiles seeded.
        </div>
      ) : null}

      {profiles.map((p) => (
        <ProfileSection
          key={p.id}
          profile={p}
          jobs={jobsByProfile.get(p.name) ?? []}
        />
      ))}

      {[...orphanNames].map((name) => (
        <ProfileSection
          key={name}
          profile={{
            id: -1,
            name,
            description: "(profile not found in DB)",
            active: false,
            config_jsonb: null,
          }}
          jobs={jobsByProfile.get(name) ?? []}
        />
      ))}
    </main>
  );
}

function ProfileSection({
  profile,
  jobs,
}: {
  profile: ProfileRow;
  jobs: Job[];
}) {
  const platforms = profile.config_jsonb?.output?.platforms ?? [];

  return (
    <section className="mb-12">
      <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="font-mono text-base font-semibold">{profile.name}</h2>
        {!profile.active ? (
          <span className="text-xs px-2 py-0.5 border border-neutral-300 dark:border-neutral-700 rounded text-neutral-500">
            paused
          </span>
        ) : null}
        <span className="text-xs text-neutral-500">
          {jobs.length} {jobs.length === 1 ? "render" : "renders"}
        </span>
      </header>

      {profile.description ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
          {profile.description}
        </p>
      ) : null}

      {platforms.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {platforms.map((p) => (
            <span
              key={p}
              className="text-xs px-2 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded"
            >
              {platformLabel(p)}
            </span>
          ))}
        </div>
      ) : null}

      {jobs.length === 0 ? (
        <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-4 text-sm text-neutral-500">
          No renders yet for this profile.
        </div>
      ) : (
        <ul className="space-y-2">
          {jobs.map((j) => (
            <JobCard key={j.id} job={j} />
          ))}
        </ul>
      )}
    </section>
  );
}

function JobCard({ job }: { job: Job }) {
  return (
    <li className="border border-neutral-200 dark:border-neutral-800 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900 transition">
      <Link
        href={`/jobs/${encodeURIComponent(job.id)}`}
        className="block p-4"
      >
        <div className="font-medium text-base mb-1">
          {job.title ?? <span className="font-mono text-sm">{job.id}</span>}
        </div>
        {job.description ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-2 line-clamp-2">
            {job.description}
          </p>
        ) : null}
        <div className="text-xs text-neutral-500 flex flex-wrap gap-x-4 gap-y-1">
          <span>{job.shotCount} shots</span>
          {(job.edl?.sources?.length ?? 1) > 1 ? (
            <span>{job.edl!.sources!.length} sources</span>
          ) : null}
          {job.renderCount > 1 ? (
            <span title="number of times this source has been re-rendered">
              v{job.renderCount}
            </span>
          ) : null}
          <span>{fmtMb(job.renderSizeBytes)}</span>
          <span>{fmtTime(job.renderMtime)}</span>
          <span className="font-mono">{job.id}</span>
        </div>
      </Link>
    </li>
  );
}
