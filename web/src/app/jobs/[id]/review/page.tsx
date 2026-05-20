import Link from "next/link";
import { notFound } from "next/navigation";
import { loadDraftJob } from "@/lib/jobs";
import ScriptReviewActions from "@/components/ScriptReviewActions";

export const dynamic = "force-dynamic";

function fmtSec(sec: number): string {
  const s = Math.floor(sec);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return `${m}:${r.toString().padStart(2, "0")}`;
  const h = Math.floor(m / 60);
  return `${h}:${(m % 60).toString().padStart(2, "0")}:${r.toString().padStart(2, "0")}`;
}

export default async function ScriptReview({
  params,
}: {
  params: { id: string };
}) {
  const slug = decodeURIComponent(params.id);
  const draft = await loadDraftJob(slug);
  if (!draft) notFound();

  const edl = draft.edl;
  const shots = edl.shots ?? [];
  const isApproved = draft.scriptApprovedAt !== null;
  const isRejected = draft.status === "rejected";
  const isLocked = draft.status === "rendering" || draft.status === "completed";

  return (
    <main className="max-w-4xl mx-auto px-5 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>

      <header className="mt-4 mb-6">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <h1 className="text-2xl font-semibold tracking-tight">
            文案 review
          </h1>
          <StatusPill status={draft.status} approved={isApproved} />
        </div>
        <p className="mt-1 text-xs text-neutral-500">
          job #{draft.jobId} · profile <span className="font-mono">{draft.profileName}</span> · slug <span className="font-mono">{slug}</span>
        </p>
      </header>

      <section className="mb-6 border border-neutral-200 dark:border-neutral-800 rounded-md p-4 bg-neutral-50 dark:bg-neutral-950">
        <div className="text-xs uppercase tracking-wider text-neutral-500 mb-1">topic</div>
        <div className="text-base">{draft.topicTitle}</div>
        {edl.thesis_zh ? (
          <>
            <div className="mt-3 text-xs uppercase tracking-wider text-neutral-500 mb-1">thesis</div>
            <div className="text-sm italic text-neutral-700 dark:text-neutral-300">{edl.thesis_zh}</div>
          </>
        ) : null}
      </section>

      <section className="mb-6 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <Field label="标题" value={edl.title_zh} />
        <Field label="标签" value={edl.tags_zh?.join("、")} />
        <Field
          label="节奏"
          value={
            edl.pacing
              ? `${edl.pacing.tier ?? "normal"} · 间隔 ${edl.pacing.inter_shot_pause_sec ?? "?"}s`
              : null
          }
        />
        <Field
          label="BGM"
          value={
            edl.bgm
              ? `${edl.bgm.mode ?? "?"} · ${edl.bgm.mood ?? "?"}`
              : null
          }
        />
      </section>

      {edl.description_zh ? (
        <section className="mb-6">
          <div className="text-xs uppercase tracking-wider text-neutral-500 mb-1">简介</div>
          <p className="text-sm whitespace-pre-line text-neutral-700 dark:text-neutral-300">
            {edl.description_zh}
          </p>
        </section>
      ) : null}

      <section className="mb-8">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
          shots ({shots.length})
        </h2>
        <ol className="space-y-3">
          {shots.map((s, i) => (
            <li
              key={i}
              className="border border-neutral-200 dark:border-neutral-800 rounded-md p-3"
            >
              <div className="flex items-baseline gap-3 flex-wrap text-xs text-neutral-500 mb-1.5">
                <span className="font-mono">#{i + 1}</span>
                {s.outline_ref ? <span>↳ {s.outline_ref}</span> : null}
                {s.asset_strategy ? (
                  <span
                    className={
                      "px-1.5 py-0.5 rounded font-mono " +
                      (s.asset_strategy === "archival"
                        ? "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300"
                        : "bg-neutral-100 dark:bg-neutral-800")
                    }
                  >
                    {s.asset_strategy}
                    {s.person_name ? ` · ${s.person_name}` : ""}
                  </span>
                ) : null}
              </div>
              <div className="text-sm leading-relaxed mb-1.5">{s.narration}</div>
              {s.visual_brief_en ? (
                <div className="text-xs italic text-neutral-500">
                  visual: {s.visual_brief_en}
                </div>
              ) : null}
              {s.asset_strategy === "archival" && (s.archival_source || s.archival_video_id) ? (
                <div className="mt-1.5 text-xs border border-blue-200 dark:border-blue-900 bg-blue-50/40 dark:bg-blue-950/20 rounded p-2 space-y-0.5">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-[10px] uppercase tracking-wider text-blue-700 dark:text-blue-400 font-semibold">
                      archival
                    </span>
                    {s.archival_source ? (
                      <span className="font-mono text-[10px] bg-blue-100 dark:bg-blue-900 px-1 rounded">
                        {s.archival_source}
                      </span>
                    ) : null}
                    {s.archival_video_id ? (
                      <a
                        href={
                          s.archival_source === "bilibili"
                            ? `https://www.bilibili.com/video/${s.archival_video_id}`
                            : `https://www.youtube.com/watch?v=${s.archival_video_id}&t=${Math.floor(s.archival_start_sec ?? 0)}`
                        }
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-[10px] underline hover:text-blue-900 dark:hover:text-blue-200"
                      >
                        {s.archival_video_id}
                      </a>
                    ) : null}
                    {s.archival_start_sec !== undefined && s.archival_dur_sec !== undefined ? (
                      <span className="text-[10px] text-neutral-600 dark:text-neutral-400 font-mono">
                        @ {fmtSec(s.archival_start_sec)} for {s.archival_dur_sec}s
                      </span>
                    ) : null}
                  </div>
                  {s.archival_excerpt ? (
                    <div className="text-xs text-neutral-700 dark:text-neutral-300">
                      {s.archival_excerpt}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {s.purpose ? (
                <div className="text-xs italic text-neutral-500 mt-1">
                  purpose: {s.purpose}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </section>

      {edl.references && edl.references.length > 0 ? (
        <section className="mb-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
            Agent 查阅的资料 ({edl.references.length})
          </h2>
          <ul className="space-y-2">
            {edl.references.map((r, i) => (
              <li
                key={i}
                className="text-sm border border-neutral-200 dark:border-neutral-800 rounded-md p-2.5"
              >
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-xs font-mono text-neutral-500 uppercase">{r.type}</span>
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline font-medium hover:text-neutral-900 dark:hover:text-neutral-100"
                  >
                    {r.title ?? r.id ?? r.url}
                  </a>
                </div>
                {r.why_used ? (
                  <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">
                    {r.why_used}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {draft.feedback ? (
        <section className="mb-6 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950 rounded-md p-3">
          <div className="text-xs uppercase tracking-wider text-amber-700 dark:text-amber-300 mb-1">
            上次评论
          </div>
          <div className="text-sm whitespace-pre-line">{draft.feedback}</div>
        </section>
      ) : null}

      <ScriptReviewActions
        jobId={draft.jobId}
        status={draft.status}
        approved={isApproved}
        locked={isLocked}
      />

      <section className="mt-10">
        <details>
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-neutral-500">
            EDL JSON
          </summary>
          <pre className="text-xs overflow-x-auto bg-neutral-100 dark:bg-neutral-900 p-3 rounded-md mt-2">
            {JSON.stringify(edl, null, 2)}
          </pre>
        </details>
      </section>
    </main>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-neutral-500 uppercase tracking-wider">{label}</div>
      <div className="text-sm">{value ?? "—"}</div>
    </div>
  );
}

function StatusPill({
  status,
  approved,
}: {
  status: string;
  approved: boolean;
}) {
  let label = status;
  let cls = "bg-neutral-200 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300";
  if (status === "script_draft" && approved) {
    label = "approved · 等渲染";
    cls = "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300";
  } else if (status === "script_draft") {
    label = "待审批";
    cls = "bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300";
  } else if (status === "rejected") {
    label = "已驳回";
    cls = "bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300";
  } else if (status === "rendering") {
    label = "渲染中";
    cls = "bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300";
  } else if (status === "completed") {
    label = "已完成";
    cls = "bg-green-100 dark:bg-green-950 text-green-800 dark:text-green-300";
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>{label}</span>
  );
}
