"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Topic } from "@/lib/topics";

const FEED_LABEL: Record<string, string> = {
  zhihu_hot: "知乎热榜",
  thepaper_featured: "澎湃 featured",
  "36kr_latest": "36氪",
  weibo_hot: "微博热搜",
};

export default function TopicCard({ topic }: { topic: Topic }) {
  const router = useRouter();
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [hidden, setHidden] = useState(false);

  async function act(action: "approve" | "reject") {
    setPending(action);
    try {
      const r = await fetch(`/youtube-clips/api/topics/${topic.id}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (r.ok) {
        setHidden(true);
        // give the server a moment then revalidate so other tabs refresh too
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

  return (
    <li className="border border-neutral-200 dark:border-neutral-800 rounded-md p-4">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-1">
        <h3 className="font-medium text-base">{topic.title}</h3>
        <span className="text-xs text-neutral-500 font-mono">
          {topic.profileName}
        </span>
      </div>
      {topic.description && (
        <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-2">
          {topic.description}
        </p>
      )}
      {topic.metadata?.suggested_angle && (
        <div className="text-sm bg-neutral-50 dark:bg-neutral-900 rounded p-2.5 mb-3">
          <div className="text-xs text-neutral-500 mb-1">建议角度</div>
          {topic.metadata.suggested_angle}
        </div>
      )}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs text-neutral-500 flex flex-wrap gap-x-3">
          {feedLabel && <span>来源: {feedLabel}</span>}
          {topic.metadata?.source_link && (
            <a
              href={topic.metadata.source_link}
              target="_blank"
              rel="noopener"
              className="underline hover:text-neutral-700"
            >
              原文 ↗
            </a>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => act("reject")}
            disabled={pending !== null}
            className="px-3 py-1 text-sm rounded border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-50"
          >
            {pending === "reject" ? "..." : "✗ 删除"}
          </button>
          <button
            onClick={() => act("approve")}
            disabled={pending !== null}
            className="px-3 py-1 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
          >
            {pending === "approve" ? "..." : "✓ 通过"}
          </button>
        </div>
      </div>
    </li>
  );
}
