"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Topic } from "@/lib/topics";

function ageLabelFor(ageDays: number, d: Date): string {
  // Show HH:MM in Asia/Tokyo for recent ones so you can see cron tick time.
  const hhmm = d.toLocaleTimeString("zh-CN", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
  });
  if (ageDays === 0) return `今天 ${hhmm}`;
  if (ageDays === 1) return `昨天 ${hhmm}`;
  if (ageDays === 2) return `前天 ${hhmm}`;
  return `${ageDays}d`;
}

const FEED_LABEL: Record<string, string> = {
  zhihu_hot: "知乎热榜",
  thepaper_featured: "澎湃 featured",
  "36kr_latest": "36氪",
  weibo_hot: "微博热搜",
};

/** Compact one-line topic row for the pending tab.
 *  Click the row body to expand description / angle / source inline;
 *  click ✓ / ✗ to approve/reject without expanding. */
export default function TopicCompactRow({ topic }: { topic: Topic }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [hidden, setHidden] = useState(false);

  async function act(action: "approve" | "reject", e: React.MouseEvent) {
    e.stopPropagation();
    setPending(action);
    try {
      const r = await fetch(`/youtube-clips/api/topics/${topic.id}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (r.ok) {
        setHidden(true);
        setTimeout(() => router.refresh(), 200);
      } else {
        setPending(null);
        const data = await r.json().catch(() => ({}));
        alert(`error: ${data.error ?? r.status}`);
      }
    } catch (e) {
      setPending(null);
      alert(`network error: ${e}`);
    }
  }

  if (hidden) return null;

  const feed = topic.metadata?.source_feed;
  const feedLabel = feed ? (FEED_LABEL[feed] ?? feed) : null;
  const hasDetail =
    !!topic.description || !!topic.metadata?.suggested_angle || !!feedLabel;
  // Always show a time chip — operator wants to spot "today's batch" at a
  // glance. <1d = "今天 HH:MM" (so you can see the cron run time), 1d-2d
  // labelled "昨天" / "前天", else "Nd". Stale (>=7d) gets amber emphasis.
  const generatedAt = new Date(topic.generatedAt);
  const ageMs = Date.now() - generatedAt.getTime();
  const ageDays = Math.floor(ageMs / (24 * 3600 * 1000));
  const ageLabel = ageLabelFor(ageDays, generatedAt);
  const ageStale = ageDays >= 7;

  return (
    <li className="border border-neutral-200 dark:border-neutral-800 rounded-md hover:border-neutral-300 dark:hover:border-neutral-700 transition">
      <div className="flex items-center gap-2 px-2.5 py-1.5">
        <button
          onClick={() => hasDetail && setExpanded((x) => !x)}
          className={
            "flex-1 flex items-center gap-2 text-left text-sm min-w-0 " +
            (hasDetail ? "cursor-pointer" : "cursor-default")
          }
        >
          {hasDetail ? (
            <span className="text-[10px] text-neutral-400 w-3 flex-shrink-0">
              {expanded ? "▼" : "▶"}
            </span>
          ) : (
            <span className="w-3 flex-shrink-0" />
          )}
          <span className="text-xs text-neutral-400 font-mono flex-shrink-0">
            #{topic.id}
          </span>
          <span className="truncate">{topic.title}</span>
          <span
            className={
              "text-[10px] flex-shrink-0 px-1 rounded font-mono " +
              (ageStale
                ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400"
                : ageDays === 0
                  ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-400"
                  : "text-neutral-400")
            }
            title={`生成于 ${generatedAt.toLocaleString("zh-CN")}`}
          >
            {ageLabel}
          </span>
        </button>
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={(e) => act("reject", e)}
            disabled={pending !== null}
            title="删除"
            className="px-2 py-0.5 text-sm rounded border border-neutral-300 dark:border-neutral-700 hover:bg-red-50 dark:hover:bg-red-950 hover:text-red-700 dark:hover:text-red-400 disabled:opacity-50 transition"
          >
            {pending === "reject" ? "..." : "✗"}
          </button>
          <button
            onClick={(e) => act("approve", e)}
            disabled={pending !== null}
            title="通过"
            className="px-2 py-0.5 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
          >
            {pending === "approve" ? "..." : "✓"}
          </button>
        </div>
      </div>
      {expanded && hasDetail && (
        <div className="border-t border-neutral-200 dark:border-neutral-800 px-3 py-2.5 text-sm bg-neutral-50/40 dark:bg-neutral-900/40 space-y-2">
          {topic.description && (
            <p className="text-neutral-700 dark:text-neutral-300">
              {topic.description}
            </p>
          )}
          {topic.metadata?.suggested_angle && (
            <div className="text-sm bg-white dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 rounded p-2">
              <div className="text-[10px] text-neutral-500 uppercase tracking-wider mb-0.5">
                建议角度
              </div>
              <div className="text-neutral-700 dark:text-neutral-300">
                {topic.metadata.suggested_angle}
              </div>
            </div>
          )}
          {(feedLabel || topic.metadata?.source_link) && (
            <div className="text-xs text-neutral-500 flex flex-wrap gap-x-3">
              {feedLabel && <span>来源: {feedLabel}</span>}
              {topic.metadata?.source_link && (
                <a
                  href={topic.metadata.source_link}
                  target="_blank"
                  rel="noopener"
                  onClick={(e) => e.stopPropagation()}
                  className="underline hover:text-neutral-700"
                >
                  原文 ↗
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
