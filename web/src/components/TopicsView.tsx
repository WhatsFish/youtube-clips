"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import type { Topic } from "@/lib/topics";
import TopicCompactRow from "@/components/TopicCompactRow";

type Tab = "pending" | "waiting" | "rendered";

const TAB_LABEL: Record<Tab, string> = {
  pending: "待审批",
  waiting: "已通过 · 待制作",
  rendered: "已通过 · 已制作",
};

// "全部" / "all-profiles" filter sentinel — kept separate from any real
// profile name to avoid edge cases if a profile were ever literally
// named "all".
const ALL_PROFILES = "__all__";

function uniqueProfiles(topics: Topic[]): string[] {
  const set = new Set<string>();
  for (const t of topics) set.add(t.profileName);
  return Array.from(set).sort();
}

function countByProfile(topics: Topic[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const t of topics) m.set(t.profileName, (m.get(t.profileName) ?? 0) + 1);
  return m;
}

function groupByProfile(topics: Topic[]): Map<string, Topic[]> {
  const m = new Map<string, Topic[]>();
  for (const t of topics) {
    if (!m.has(t.profileName)) m.set(t.profileName, []);
    m.get(t.profileName)!.push(t);
  }
  return m;
}

export default function TopicsView({
  pending,
  waiting,
  rendered,
}: {
  pending: Topic[];
  waiting: Topic[];
  rendered: Topic[];
}) {
  const initial: Tab =
    pending.length > 0 ? "pending" : waiting.length > 0 ? "waiting" : "rendered";
  const [tab, setTab] = useState<Tab>(initial);
  const [profileFilter, setProfileFilter] = useState<string>(ALL_PROFILES);

  const buckets: Record<Tab, Topic[]> = { pending, waiting, rendered };

  // Profile chip set is derived from the CURRENT tab — switching tabs
  // resets the filter implicitly to "all" if the previously-selected
  // profile has no topics in the new tab (so you never get an empty page).
  const visibleProfiles = useMemo(() => uniqueProfiles(buckets[tab]), [tab, pending, waiting, rendered]);
  const profileCounts = useMemo(() => countByProfile(buckets[tab]), [tab, pending, waiting, rendered]);
  const effectiveFilter = visibleProfiles.includes(profileFilter)
    ? profileFilter
    : ALL_PROFILES;

  const filtered = useMemo(() => {
    return effectiveFilter === ALL_PROFILES
      ? buckets[tab]
      : buckets[tab].filter((t) => t.profileName === effectiveFilter);
  }, [tab, effectiveFilter, pending, waiting, rendered]);

  return (
    <>
      <nav className="mb-4 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800">
        {(Object.keys(TAB_LABEL) as Tab[]).map((t) => {
          const active = tab === t;
          const count = buckets[t].length;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={
                "px-3 py-2 text-sm font-medium border-b-2 -mb-px transition " +
                (active
                  ? "border-neutral-900 dark:border-neutral-100 text-neutral-900 dark:text-neutral-100"
                  : "border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300")
              }
            >
              {TAB_LABEL[t]}{" "}
              <span className={"ml-1 text-xs " + (active ? "" : "text-neutral-400")}>
                ({count})
              </span>
            </button>
          );
        })}
      </nav>

      {visibleProfiles.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          <FilterChip
            label="全部"
            count={buckets[tab].length}
            active={effectiveFilter === ALL_PROFILES}
            onClick={() => setProfileFilter(ALL_PROFILES)}
          />
          {visibleProfiles.map((p) => (
            <FilterChip
              key={p}
              label={p}
              count={profileCounts.get(p) ?? 0}
              active={effectiveFilter === p}
              onClick={() => setProfileFilter(p)}
              mono
            />
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-6 text-sm text-neutral-500">
          {tab === "pending" && (
            <>
              没有待审批 topic。下次 cron（09:00 UTC）会拉新候选；手动跑：
              <code className="text-xs bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded ml-1">
                scripts/run-discover-topics.sh
              </code>
            </>
          )}
          {tab === "waiting" && "没有待制作 topic。通过的 topic 会出现在这里直到渲染完成。"}
          {tab === "rendered" && "还没有视频做出来。"}
        </div>
      ) : (
        <ProfileGrouped topics={filtered} variant={tab} singleProfile={effectiveFilter !== ALL_PROFILES} />
      )}
    </>
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
  mono = false,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  mono?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "text-xs px-2.5 py-1 rounded-full border transition " +
        (active
          ? "border-neutral-900 dark:border-neutral-100 bg-neutral-900 dark:bg-neutral-100 text-neutral-50 dark:text-neutral-900"
          : "border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-900")
      }
    >
      <span className={mono ? "font-mono" : ""}>{label}</span>
      <span className={"ml-1 " + (active ? "opacity-70" : "text-neutral-500")}>
        {count}
      </span>
    </button>
  );
}

function ProfileGrouped({
  topics,
  variant,
  singleProfile,
}: {
  topics: Topic[];
  variant: Tab;
  singleProfile: boolean;
}) {
  // When the user has already narrowed to one profile via the filter
  // chips, skip the per-profile section header — would just repeat the
  // chip label and waste vertical space.
  if (singleProfile) {
    if (variant === "pending") {
      return (
        <ul className="space-y-1.5">
          {topics.map((t) => (
            <TopicCompactRow key={t.id} topic={t} />
          ))}
        </ul>
      );
    }
    return (
      <ul className="space-y-1.5">
        {topics.map((t) => (
          <ApprovedTopicRow key={t.id} topic={t} variant={variant} />
        ))}
      </ul>
    );
  }

  const groups = groupByProfile(topics);
  return (
    <>
      {Array.from(groups.entries()).map(([profile, ts]) => (
        <ProfileSection
          key={profile}
          profile={profile}
          topics={ts}
          variant={variant}
        />
      ))}
    </>
  );
}

function ProfileSection({
  profile,
  topics,
  variant,
}: {
  profile: string;
  topics: Topic[];
  variant: Tab;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mb-5">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-baseline gap-2 mb-2 w-full text-left hover:opacity-80"
      >
        <span className="text-xs text-neutral-400 w-3">{open ? "▼" : "▶"}</span>
        <h3 className="font-mono text-sm font-semibold text-neutral-600 dark:text-neutral-400">
          {profile}
        </h3>
        <span className="text-xs text-neutral-500">({topics.length})</span>
      </button>
      {open &&
        (variant === "pending" ? (
          <ul className="space-y-1.5 ml-5">
            {topics.map((t) => (
              <TopicCompactRow key={t.id} topic={t} />
            ))}
          </ul>
        ) : (
          <ul className="space-y-1.5 ml-5">
            {topics.map((t) => (
              <ApprovedTopicRow key={t.id} topic={t} variant={variant} />
            ))}
          </ul>
        ))}
    </div>
  );
}

function ApprovedTopicRow({
  topic,
  variant,
}: {
  topic: Topic;
  variant: "waiting" | "rendered";
}) {
  const isRendered = variant === "rendered";
  // next/link auto-prepends basePath; don't hardcode "/youtube-clips/"
  // here or it becomes /youtube-clips/youtube-clips/jobs/... → 404.
  const link =
    isRendered && topic.renderedSlug
      ? `/jobs/${encodeURIComponent(topic.renderedSlug)}`
      : null;
  const body = (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span
        className={
          "text-[10px] px-1.5 py-0.5 rounded uppercase " +
          (isRendered
            ? "bg-green-500/15 text-green-700 dark:text-green-300"
            : "bg-amber-500/15 text-amber-700 dark:text-amber-300")
        }
      >
        {isRendered ? "已制作" : "待制作"}
      </span>
      <span className="text-sm">{topic.title}</span>
      <span className="text-xs text-neutral-500 ml-auto">#{topic.id}</span>
    </div>
  );
  return (
    <li
      className={
        "border rounded-md p-2.5 text-sm " +
        "border-neutral-200 dark:border-neutral-800 " +
        (link ? "hover:bg-neutral-100 dark:hover:bg-neutral-900 transition" : "")
      }
    >
      {link ? (
        <Link href={link} className="block">
          {body}
        </Link>
      ) : (
        body
      )}
    </li>
  );
}
