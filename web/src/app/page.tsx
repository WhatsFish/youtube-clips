import Link from "next/link";
import { query } from "@/lib/db";
import {
  listJobs,
  listDraftJobs,
  groupByProfile,
  fmtMb,
  fmtTime,
  type Job,
  type DraftJob,
} from "@/lib/jobs";
import { listActiveRuns, listRecentFailures, loadRecentCost } from "@/lib/runs";
import { countPendingTopics } from "@/lib/topics";
import ActiveRunsLive from "@/components/ActiveRunsLive";

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

  const [jobs, drafts, activeRuns, recentFailures, recentCost, pendingTopics] = await Promise.all([
    listJobs(),
    listDraftJobs(),
    listActiveRuns(),
    listRecentFailures(5),
    loadRecentCost(24),
    countPendingTopics(),
  ]);
  const jobsByProfile = groupByProfile(jobs);

  // Profiles ordered by DB id; orphan jobs (Profile name not in DB) get a
  // synthetic trailing section so nothing silently disappears.
  const orphanNames = new Set<string>(jobsByProfile.keys());
  for (const p of profiles) orphanNames.delete(p.name);

  return (
    <main className="max-w-5xl mx-auto px-5 py-12">
      <header className="mb-10">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight mb-1">
              youtube-clips
            </h1>
            <p className="text-sm text-neutral-500">
              Profile-based multi-platform video remix pipeline.
            </p>
          </div>
          <div className="flex items-baseline gap-4 text-xs">
            <Link
              href="/assets"
              className="text-neutral-500 hover:underline uppercase tracking-wider"
            >
              archival 池
            </Link>
            {pendingTopics > 0 && (
              <Link
                href="/topics"
                className="text-neutral-700 dark:text-neutral-300 hover:underline"
              >
                <span className="uppercase tracking-wider text-neutral-500">
                  待审批 topic
                </span>{" "}
                <span className="font-medium">{pendingTopics}</span>
              </Link>
            )}
            {drafts.filter((d) => d.status === "script_draft" && !d.scriptApprovedAt).length > 0 && (
              <span className="text-amber-700 dark:text-amber-400">
                <span className="uppercase tracking-wider text-neutral-500">
                  待审批文案
                </span>{" "}
                <span className="font-medium">
                  {drafts.filter((d) => d.status === "script_draft" && !d.scriptApprovedAt).length}
                </span>
              </span>
            )}
            {recentCost.doubaoCalls > 0 && (
              <div className="text-neutral-500 text-right">
                <div className="uppercase tracking-wider">
                  24h Doubao 花费
                </div>
                <div className="font-mono text-neutral-700 dark:text-neutral-300">
                  ${recentCost.doubaoUsd.toFixed(2)} · {recentCost.doubaoCalls} 调用
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {dbError ? (
        <div className="mb-8 border border-red-300 dark:border-red-800 rounded-md p-4 text-sm">
          <p className="font-medium text-red-700 dark:text-red-400 mb-1">
            DB error
          </p>
          <pre className="text-xs whitespace-pre-wrap">{dbError}</pre>
        </div>
      ) : null}

      <ActiveRunsLive
        initialActive={activeRuns}
        recentFailures={recentFailures}
      />

      {drafts.length > 0 ? <DraftsSection drafts={drafts} /> : null}

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

function DraftsSection({ drafts }: { drafts: DraftJob[] }) {
  return (
    <section className="mb-10">
      <header className="mb-3 flex items-baseline gap-3">
        <h2 className="font-mono text-base font-semibold">文案 review 队列</h2>
        <span className="text-xs text-neutral-500">
          {drafts.length} {drafts.length === 1 ? "draft" : "drafts"}
        </span>
      </header>
      <ul className="space-y-2">
        {drafts.map((d) => (
          <li
            key={d.jobId}
            className="border border-neutral-200 dark:border-neutral-800 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900 transition"
          >
            <Link
              href={`/jobs/${encodeURIComponent(d.slug)}/review`}
              className="block p-3"
            >
              <div className="flex items-baseline gap-2 mb-1">
                <span className="font-medium text-sm">
                  {d.edl.title_zh ?? d.topicTitle}
                </span>
                <DraftStatusPill draft={d} />
              </div>
              <div className="text-xs text-neutral-500 flex flex-wrap gap-x-4 gap-y-1">
                <span>{d.edl.shots?.length ?? 0} shots</span>
                <span className="font-mono">{d.profileName}</span>
                <span>{fmtTime(d.createdAt)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DraftStatusPill({ draft }: { draft: DraftJob }) {
  let label = "待审批";
  let cls = "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300";
  if (draft.status === "rejected") {
    label = "已驳回";
    cls = "bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300";
  } else if (draft.scriptApprovedAt) {
    label = "approved · 等渲染";
    cls = "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300";
  }
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${cls}`}>{label}</span>
  );
}

// Profile sections with more than this many renders default to collapsed.
// Big ones can be reopened with the chevron; small ones stay expanded so
// the page is useful at first glance. Uses native <details> so no client
// JS is needed.
const PROFILE_COLLAPSE_THRESHOLD = 8;

function ProfileSection({
  profile,
  jobs,
}: {
  profile: ProfileRow;
  jobs: Job[];
}) {
  const platforms = profile.config_jsonb?.output?.platforms ?? [];
  const defaultOpen = jobs.length <= PROFILE_COLLAPSE_THRESHOLD;
  return (
    <section className="mb-6">
      <details open={defaultOpen} className="group">
        <summary className="cursor-pointer list-none mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 hover:opacity-80">
          <span className="text-xs text-neutral-400 w-3 group-open:rotate-90 inline-block transition-transform">
            ▶
          </span>
          <h2 className="font-mono text-base font-semibold">{profile.name}</h2>
          {!profile.active ? (
            <span className="text-xs px-2 py-0.5 border border-neutral-300 dark:border-neutral-700 rounded text-neutral-500">
              paused
            </span>
          ) : null}
          <span className="text-xs text-neutral-500">
            {jobs.length} {jobs.length === 1 ? "render" : "renders"}
          </span>
          {platforms.length > 0 ? (
            <span className="text-xs text-neutral-500">
              · {platforms.map(platformLabel).join(" · ")}
            </span>
          ) : null}
        </summary>
        <div className="ml-5">
          {profile.description ? (
            <p className="text-xs text-neutral-600 dark:text-neutral-400 mb-3 line-clamp-2">
              {profile.description}
            </p>
          ) : null}

          {jobs.length === 0 ? (
            <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-3 text-xs text-neutral-500">
              No renders yet for this profile.
            </div>
          ) : (
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {jobs.map((j) => (
                <JobCard key={j.id} job={j} />
              ))}
            </ul>
          )}
        </div>
      </details>
    </section>
  );
}

function JobCard({ job }: { job: Job }) {
  return (
    <li className="border border-neutral-200 dark:border-neutral-800 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900 transition">
      <Link
        href={`/jobs/${encodeURIComponent(job.id)}`}
        className="block p-3"
      >
        <div className="font-medium text-sm mb-1 line-clamp-2">
          {job.title ?? job.topicTitle ?? (
            <span className="font-mono text-xs">{job.id}</span>
          )}
        </div>
        {job.description ? (
          <p className="text-xs text-neutral-600 dark:text-neutral-400 mb-1.5 line-clamp-1">
            {job.description}
          </p>
        ) : null}
        <div className="text-[10px] text-neutral-500 flex flex-wrap gap-x-3 gap-y-0.5">
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
        </div>
      </Link>
    </li>
  );
}
