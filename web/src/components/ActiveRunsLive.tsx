"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { stageLabel, type Run } from "@/lib/runs-shared";

type Props = {
  initialActive: Run[];
  recentFailures: Run[];
};

function fmtAgo(ts: Date | string): string {
  const d = typeof ts === "string" ? new Date(ts) : ts;
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return `${Math.floor(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}

export default function ActiveRunsLive({
  initialActive,
  recentFailures,
}: Props) {
  const [active, setActive] = useState(initialActive);
  const [, setTick] = useState(0);

  // Poll the active-runs list every 5s. We hit the events endpoint per run
  // because we need current_stage refreshed too. Cheap (one query each).
  useEffect(() => {
    const tickPoll = async () => {
      const updated: Run[] = [];
      for (const r of active) {
        try {
          const res = await fetch(`/youtube-clips/api/runs/${r.id}/events`, {
            cache: "no-store",
          });
          if (!res.ok) continue;
          const data = (await res.json()) as { run: Run };
          if (data.run.status === "running") updated.push(data.run);
        } catch {
          /* swallow */
        }
      }
      // Also probe the list endpoint for any *new* runs that started.
      try {
        const res = await fetch(`/youtube-clips/api/runs/active`, {
          cache: "no-store",
        });
        if (res.ok) {
          const data = (await res.json()) as { runs: Run[] };
          for (const r of data.runs) {
            if (!updated.find((u) => u.id === r.id)) updated.push(r);
          }
        }
      } catch {
        /* swallow */
      }
      setActive(updated);
    };
    const t = setInterval(tickPoll, 5000);
    return () => clearInterval(t);
  }, [active]);

  // Re-render fmtAgo every 10s.
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 10000);
    return () => clearInterval(t);
  }, []);

  if (active.length === 0 && recentFailures.length === 0) return null;

  return (
    <section className="mb-10 space-y-3">
      {active.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
            正在制作 ({active.length})
          </h2>
          <ul className="space-y-2">
            {active.map((r) => (
              <li
                key={r.id}
                className="border border-blue-200 dark:border-blue-900 bg-blue-50/40 dark:bg-blue-950/20 rounded-md"
              >
                <Link
                  href={`/runs/${r.id}`}
                  className="block p-3 hover:bg-blue-50 dark:hover:bg-blue-950/40 transition"
                >
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="font-medium text-sm">{r.topicTitle}</span>
                    <span className="text-xs text-neutral-500 font-mono">
                      {r.profileName}
                    </span>
                  </div>
                  <div className="text-xs text-neutral-600 dark:text-neutral-400 mt-1 flex flex-wrap gap-x-3">
                    <span>
                      <span className="text-blue-600 dark:text-blue-400">●</span>{" "}
                      {r.currentStage
                        ? stageLabel(r.currentStage.split(":")[0]) +
                          (r.currentStage.includes(":")
                            ? ` (${r.currentStage.split(":")[1]})`
                            : "")
                        : "启动中"}
                    </span>
                    <span>已跑 {fmtAgo(r.startedAt)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}

      {recentFailures.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mt-5">
            最近 24h 内异常 ({recentFailures.length})
          </h2>
          <ul className="space-y-1">
            {recentFailures.map((r) => (
              <li
                key={r.id}
                className={
                  "border rounded-md text-xs " +
                  (r.status === "failed"
                    ? "border-red-200 dark:border-red-900 bg-red-50/40 dark:bg-red-950/20"
                    : "border-amber-200 dark:border-amber-900 bg-amber-50/40 dark:bg-amber-950/20")
                }
              >
                <Link
                  href={`/runs/${r.id}`}
                  className="block p-2.5 hover:bg-red-50 dark:hover:bg-red-950/40 transition"
                >
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span
                      className={
                        "px-1.5 py-0.5 rounded text-[10px] uppercase " +
                        (r.status === "failed"
                          ? "bg-red-500/20 text-red-700 dark:text-red-300"
                          : "bg-amber-500/20 text-amber-700 dark:text-amber-300")
                      }
                    >
                      {r.status}
                    </span>
                    <span className="font-medium">{r.topicTitle}</span>
                    <span className="text-neutral-500 font-mono">
                      {r.profileName}
                    </span>
                  </div>
                  {r.errorMessage && (
                    <div className="text-neutral-600 dark:text-neutral-400 mt-1 line-clamp-1">
                      {r.errorMessage}
                    </div>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
