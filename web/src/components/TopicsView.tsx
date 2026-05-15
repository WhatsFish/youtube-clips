"use client";

import { useState } from "react";
import Link from "next/link";
import type { Topic } from "@/lib/topics";
import TopicCard from "@/components/TopicCard";

type Tab = "pending" | "waiting" | "rendered";

const TAB_LABEL: Record<Tab, string> = {
  pending: "待审批",
  waiting: "已通过 · 待制作",
  rendered: "已通过 · 已制作",
};

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
  // Default to whichever tab has actionable content. Pending wins if non-empty.
  const initial: Tab =
    pending.length > 0 ? "pending" : waiting.length > 0 ? "waiting" : "rendered";
  const [tab, setTab] = useState<Tab>(initial);

  const buckets: Record<Tab, Topic[]> = { pending, waiting, rendered };
  const current = buckets[tab];

  return (
    <>
      <nav className="mb-6 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800">
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
              <span
                className={
                  "ml-1 text-xs " + (active ? "" : "text-neutral-400")
                }
              >
                ({count})
              </span>
            </button>
          );
        })}
      </nav>

      {current.length === 0 ? (
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
        <ProfileGrouped topics={current} variant={tab} />
      )}
    </>
  );
}

function ProfileGrouped({
  topics,
  variant,
}: {
  topics: Topic[];
  variant: Tab;
}) {
  const groups = groupByProfile(topics);
  return (
    <>
      {Array.from(groups.entries()).map(([profile, ts]) => (
        <div key={profile} className="mb-6">
          <h3 className="font-mono text-sm font-semibold mb-2 text-neutral-600 dark:text-neutral-400">
            {profile}{" "}
            <span className="text-xs text-neutral-500 font-sans font-normal">
              ({ts.length})
            </span>
          </h3>
          {variant === "pending" ? (
            <ul className="space-y-3">
              {ts.map((t) => (
                <TopicCard key={t.id} topic={t} />
              ))}
            </ul>
          ) : (
            <ul className="space-y-1.5">
              {ts.map((t) => (
                <ApprovedTopicRow key={t.id} topic={t} variant={variant} />
              ))}
            </ul>
          )}
        </div>
      ))}
    </>
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
        (link
          ? "hover:bg-neutral-100 dark:hover:bg-neutral-900 transition"
          : "")
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
