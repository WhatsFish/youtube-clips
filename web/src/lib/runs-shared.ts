// Types and pure utilities shared between server components (which run
// the DB queries in runs.ts) and client components (RunTimeline,
// ActiveRunsLive). Importing the DB-bound runs.ts from a "use client"
// component drags `pg` into the browser bundle and fails the build with
// "Module not found: Can't resolve 'fs' / 'net' / 'tls'", so anything a
// client component needs (types + label maps) lives here.

export type RunStatus = "running" | "completed" | "failed" | "skipped";
export type EventStatus = "start" | "done" | "fail" | "skip" | "info";

export type Run = {
  id: number;
  profileName: string;
  kind: "commentary" | "synthesis" | "producer";
  topicTitle: string;
  urlSlug: string | null;
  status: RunStatus;
  currentStage: string | null;
  errorMessage: string | null;
  topicId: number | null;
  jobId: number | null;
  startedAt: Date | string;
  finishedAt: Date | string | null;
};

export type RunEvent = {
  id: number;
  runId: number;
  stage: string;
  status: EventStatus;
  message: string | null;
  metadata: Record<string, unknown> | null;
  createdAt: Date | string;
};

const STAGE_LABEL: Record<string, string> = {
  discover: "选源",
  discover_search: "YouTube 搜索",
  discover_pick: "Claude 选片",
  download: "下载",
  outline: "提纲 (Stage 1)",
  script: "脚本 (Stage 2)",
  assets: "素材采集",
  acquire: "单 shot 素材",
  edl_analyze: "EDL 分析 (Stage 1)",
  edl_write: "EDL 撰写 (Stage 2)",
  edl_persist: "EDL 入库",
  render: "渲染",
  render_setup: "渲染准备 (VAD)",
  render_shot: "单 shot 渲染",
  render_concat: "拼接",
  render_subs: "字幕",
  exception: "异常",
};

export function stageLabel(stage: string): string {
  return STAGE_LABEL[stage] ?? stage;
}
