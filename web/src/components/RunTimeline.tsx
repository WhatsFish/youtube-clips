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

/** Infer the actual asset strategy from a source's video_id. The pipeline
 *  stamps a stable prefix on every external_id: pexels- / cogview- /
 *  person- / doubao- / cogvideox- — see _acquire_one_* in produce-original. */
function strategyFromVideoId(vid: string | undefined | null): string | null {
  if (!vid) return null;
  if (vid.startsWith("pexels-")) return "pexels";
  if (vid.startsWith("cogview-")) return "image";
  if (vid.startsWith("person-")) return "person";
  if (vid.startsWith("doubao-") || vid.startsWith("cogvideox-")) return "ai";
  return null;
}

/** Walk events forward for each fail event; if there's a matching same-shot
 *  done event downstream (same stage), that fail was auto-recovered. Return a
 *  map keyed by the fail event id → recovery info. */
function buildRecoveryMap(events: RunEvent[]): Map<number, { recoveredBy: string }> {
  const out = new Map<number, { recoveredBy: string }>();
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (e.status !== "fail") continue;
    const md = e.metadata ?? {};
    const shotIdx = typeof md.shot_idx === "number" ? md.shot_idx : null;
    if (shotIdx === null) continue;
    for (let j = i + 1; j < events.length; j++) {
      const later = events[j];
      if (later.stage !== e.stage) continue;
      const lm = later.metadata ?? {};
      const lShot = typeof lm.shot_idx === "number" ? lm.shot_idx : null;
      if (lShot !== shotIdx) continue;
      if (later.status === "done") {
        const inferred = strategyFromVideoId(lm.video_id as string | null | undefined);
        out.set(e.id, { recoveredBy: inferred ?? "(unknown)" });
        break;
      }
    }
  }
  return out;
}

type ShotState = {
  shotIdx: number;
  plannedStrategy: string | null;
  actualStrategy: string | null;
  videoId: string | null;
  status: "pending" | "ok" | "fallback" | "fail";
  failReason: string | null;
};

/** Reduce all acquire events into one row per shot — used by the top-of-page
 *  AcquireGrid. plannedStrategy comes from the `start` event's metadata.
 *  actualStrategy is inferred from the final done's video_id prefix; if it
 *  differs from planned, that shot fell back. */
function buildShotGrid(events: RunEvent[]): ShotState[] {
  const map = new Map<number, ShotState>();
  for (const e of events) {
    if (e.stage !== "acquire") continue;
    const md = e.metadata ?? {};
    const shotIdx = typeof md.shot_idx === "number" ? md.shot_idx : null;
    if (shotIdx === null) continue;
    let s = map.get(shotIdx);
    if (!s) {
      s = {
        shotIdx,
        plannedStrategy: null,
        actualStrategy: null,
        videoId: null,
        status: "pending",
        failReason: null,
      };
      map.set(shotIdx, s);
    }
    if (e.status === "start") {
      const strat = md.strategy;
      if (typeof strat === "string") s.plannedStrategy = strat;
    } else if (e.status === "done") {
      const vid = md.video_id as string | undefined;
      if (vid) s.videoId = vid;
      const actual = strategyFromVideoId(vid);
      if (actual) s.actualStrategy = actual;
      s.status =
        s.plannedStrategy && s.actualStrategy && s.plannedStrategy !== s.actualStrategy
          ? "fallback"
          : "ok";
    } else if (e.status === "fail") {
      if (s.status === "pending") {
        s.status = "fail";
        s.failReason = e.message;
      }
    }
  }
  return Array.from(map.values()).sort((a, b) => a.shotIdx - b.shotIdx);
}

/** Compact chip helper. */
function Chip({
  children,
  tone = "neutral",
  mono = false,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "red" | "amber" | "green" | "blue";
  mono?: boolean;
}) {
  const toneCls = {
    neutral: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
    red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    green: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
    blue: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  }[tone];
  return (
    <span
      className={
        "inline-block text-[10px] px-1.5 py-0.5 rounded " +
        toneCls +
        (mono ? " font-mono" : "")
      }
    >
      {children}
    </span>
  );
}

function MetadataChips({ md }: { md: Record<string, unknown> | null }) {
  if (!md) return null;
  const chips: React.ReactNode[] = [];
  if (typeof md.shot_idx === "number") {
    chips.push(<Chip key="s" mono>shot {md.shot_idx}</Chip>);
  }
  if (typeof md.strategy === "string") {
    chips.push(<Chip key="st">{md.strategy}</Chip>);
  }
  if (typeof md.video_id === "string") {
    chips.push(<Chip key="v" mono>{md.video_id}</Chip>);
  }
  if (typeof md.points === "number") {
    chips.push(<Chip key="p">{md.points} 点</Chip>);
  }
  if (typeof md.shots === "number") {
    chips.push(<Chip key="sh">{md.shots} shots</Chip>);
  }
  if (typeof md.voice === "string") {
    chips.push(<Chip key="vo" mono>{md.voice}</Chip>);
  }
  if (typeof md.sources === "number") {
    chips.push(<Chip key="src">{md.sources} sources</Chip>);
  }
  const q = md.query;
  if (typeof q === "string" && q.length > 0) {
    const trunc = q.length > 90 ? q.slice(0, 90) + "…" : q;
    chips.push(
      <span key="q" className="text-[10px] italic text-neutral-500" title={q}>
        {trunc}
      </span>,
    );
  }
  if (chips.length === 0) return null;
  return <div className="mt-1 flex flex-wrap items-center gap-1.5">{chips}</div>;
}

function AcquireGrid({ shots }: { shots: ShotState[] }) {
  if (shots.length === 0) return null;
  const fallbackCount = shots.filter((s) => s.status === "fallback").length;
  const failCount = shots.filter((s) => s.status === "fail").length;
  const okCount = shots.filter((s) => s.status === "ok").length;
  return (
    <section className="mb-4 border border-neutral-200 dark:border-neutral-800 rounded-md p-3">
      <header className="flex items-baseline gap-3 mb-2 text-xs">
        <span className="font-semibold uppercase tracking-wider text-neutral-500">
          素材采集 ({shots.length} shot)
        </span>
        <span className="text-green-700 dark:text-green-300">{okCount} 一次通过</span>
        {fallbackCount > 0 && (
          <span className="text-amber-700 dark:text-amber-300">
            {fallbackCount} 自动回退
          </span>
        )}
        {failCount > 0 && (
          <span className="text-red-700 dark:text-red-300">{failCount} 失败</span>
        )}
      </header>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-1.5">
        {shots.map((s) => {
          const cls =
            s.status === "ok"
              ? "border-green-300 dark:border-green-800 bg-green-50/50 dark:bg-green-950/30"
              : s.status === "fallback"
                ? "border-amber-300 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/30"
                : s.status === "fail"
                  ? "border-red-300 dark:border-red-800 bg-red-50/50 dark:bg-red-950/30"
                  : "border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900";
          const tail =
            s.status === "fallback"
              ? `${s.plannedStrategy} ✗→ ${s.actualStrategy} ✓`
              : s.status === "ok"
                ? `${s.actualStrategy ?? s.plannedStrategy ?? "?"} ✓`
                : s.status === "fail"
                  ? `${s.plannedStrategy ?? "?"} ✗`
                  : `${s.plannedStrategy ?? "?"}…`;
          return (
            <div
              key={s.shotIdx}
              className={"text-[10px] px-1.5 py-1 border rounded " + cls}
              title={s.failReason ?? s.videoId ?? ""}
            >
              <div className="font-mono font-semibold">
                s{String(s.shotIdx).padStart(2, "0")}
              </div>
              <div className="text-neutral-600 dark:text-neutral-400 truncate">
                {tail}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
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
  const recoveryMap = buildRecoveryMap(events);
  const shotGrid = buildShotGrid(events);

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

      <AcquireGrid shots={shotGrid} />

      <ol className="relative border-l border-neutral-200 dark:border-neutral-800 ml-2 pl-5 space-y-2">
        {events.map((e, i) => {
          const prev = i > 0 ? events[i - 1] : null;
          const delta = prev ? fmtDelta(prev.createdAt, e.createdAt) : null;
          const recovery = recoveryMap.get(e.id);
          // Visually downgrade auto-recovered fails: fail dot in amber
          // (warning) rather than red (alarm). Real fails stay red.
          const dotCls =
            e.status === "fail" && recovery
              ? "bg-amber-500"
              : STATUS_DOT[e.status];
          return (
            <li key={e.id} className="relative">
              <span
                className={
                  "absolute -left-[26px] top-1.5 flex items-center justify-center " +
                  "h-3 w-3 rounded-full " +
                  dotCls
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
                {recovery && (
                  <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300">
                    ↳ 自动回退 {recovery.recoveredBy} (recovered)
                  </span>
                )}
              </div>
              {e.message && (
                <div className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5 break-words">
                  {e.message}
                </div>
              )}
              <MetadataChips md={e.metadata} />
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
