"use client";

import { useEffect, useRef, useState } from "react";
import { stageLabel, type Run, type RunEvent, type EventStatus } from "@/lib/runs-shared";

type Props = {
  initialRun: Run;
  initialEvents: RunEvent[];
};

const STATUS_DOT: Record<EventStatus, string> = {
  start: "bg-blue-500",
  done: "bg-green-500",
  fail: "bg-red-500",
  skip: "bg-amber-500",
  info: "bg-neutral-400",
};

const STATUS_LABEL: Record<EventStatus, string> = {
  start: "▶",
  done: "✓",
  fail: "✗",
  skip: "⊘",
  info: "·",
};

const RUN_STATUS_LABEL: Record<Run["status"], string> = {
  running: "进行中",
  completed: "已完成",
  failed: "失败",
  skipped: "跳过",
};

function fmtAgo(ts: Date | string): string {
  const d = typeof ts === "string" ? new Date(ts) : ts;
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return `${Math.floor(sec)}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${(sec / 3600).toFixed(1)}h ago`;
}

function fmtDelta(a: Date | string, b: Date | string): string {
  const da = typeof a === "string" ? new Date(a) : a;
  const db = typeof b === "string" ? new Date(b) : b;
  const sec = (db.getTime() - da.getTime()) / 1000;
  if (sec < 1) return `${(sec * 1000).toFixed(0)}ms`;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  return `${Math.floor(sec / 60)}m${Math.round(sec % 60)}s`;
}

export default function RunTimeline({ initialRun, initialEvents }: Props) {
  const [run, setRun] = useState(initialRun);
  const [events, setEvents] = useState(initialEvents);
  const [, setTick] = useState(0);
  const stopped = useRef(false);

  useEffect(() => {
    if (run.status !== "running") return;
    const poll = async () => {
      try {
        const r = await fetch(`/youtube-clips/api/runs/${run.id}/events`, {
          cache: "no-store",
        });
        if (!r.ok) return;
        const data = (await r.json()) as { run: Run; events: RunEvent[] };
        setRun(data.run);
        setEvents(data.events);
        if (data.run.status !== "running") stopped.current = true;
      } catch {
        /* swallow — next tick retries */
      }
    };
    const interval = setInterval(() => {
      if (!stopped.current) poll();
    }, 2500);
    poll();
    return () => clearInterval(interval);
  }, [run.id, run.status]);

  // Re-render the "Xs ago" labels every 10s while running.
  useEffect(() => {
    if (run.status !== "running") return;
    const t = setInterval(() => setTick((n) => n + 1), 10000);
    return () => clearInterval(t);
  }, [run.status]);

  const isRunning = run.status === "running";
  const lastEvent = events[events.length - 1];

  return (
    <div className="mt-6">
      <div className="flex items-center gap-3 mb-4">
        <span
          className={
            "inline-flex items-center gap-2 px-2 py-1 text-xs rounded-md " +
            (isRunning
              ? "bg-blue-500/10 text-blue-700 dark:text-blue-300"
              : run.status === "completed"
                ? "bg-green-500/10 text-green-700 dark:text-green-300"
                : run.status === "failed"
                  ? "bg-red-500/10 text-red-700 dark:text-red-300"
                  : "bg-amber-500/10 text-amber-700 dark:text-amber-300")
          }
        >
          {isRunning && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
          )}
          {RUN_STATUS_LABEL[run.status]}
        </span>
        {isRunning && lastEvent && (
          <span className="text-xs text-neutral-500">
            {stageLabel(lastEvent.stage)} · {fmtAgo(lastEvent.createdAt)}
          </span>
        )}
        {run.errorMessage && (
          <span className="text-xs text-red-600 dark:text-red-400">
            {run.errorMessage}
          </span>
        )}
      </div>

      <ol className="relative border-l border-neutral-200 dark:border-neutral-800 ml-2 pl-5 space-y-2">
        {events.map((e, i) => {
          const prev = i > 0 ? events[i - 1] : null;
          const delta = prev ? fmtDelta(prev.createdAt, e.createdAt) : null;
          return (
            <li key={e.id} className="relative">
              <span
                className={
                  "absolute -left-[26px] top-1.5 flex items-center justify-center " +
                  "h-3 w-3 rounded-full " +
                  STATUS_DOT[e.status]
                }
              />
              <div className="text-sm">
                <span className="font-medium">
                  {STATUS_LABEL[e.status]} {stageLabel(e.stage)}
                </span>
                {delta && (
                  <span className="ml-2 text-xs text-neutral-500">
                    +{delta}
                  </span>
                )}
                <span className="ml-2 text-xs text-neutral-400">
                  {new Date(e.createdAt).toLocaleTimeString("zh-CN", {
                    timeZone: "Asia/Tokyo",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
              </div>
              {e.message && (
                <div className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5 break-words">
                  {e.message}
                </div>
              )}
            </li>
          );
        })}
        {isRunning && (
          <li className="relative">
            <span className="absolute -left-[26px] top-1.5 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-50" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500/40" />
            </span>
            <span className="text-xs text-neutral-500 italic">working...</span>
          </li>
        )}
      </ol>
    </div>
  );
}
