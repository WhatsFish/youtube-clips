"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

type Props = {
  jobId: number;
  status: string;
  approved: boolean;
  locked: boolean;          // true once render started or finished
};

export default function ScriptReviewActions({ jobId, status, approved, locked }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [showReject, setShowReject] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function call(action: "approve" | "reject", body?: object) {
    setError(null);
    const res = await fetch(`/youtube-clips/api/jobs/${jobId}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (!res.ok) {
      const t = await res.text();
      setError(`${action} failed: ${t}`);
      return false;
    }
    return true;
  }

  if (locked) {
    return (
      <section className="border border-neutral-200 dark:border-neutral-800 rounded-md p-4 bg-neutral-50 dark:bg-neutral-950 text-sm text-neutral-600 dark:text-neutral-400">
        {status === "completed"
          ? "已完成。"
          : "渲染已启动，无法再改文案。"}
      </section>
    );
  }

  if (approved) {
    return (
      <section className="border border-blue-300 dark:border-blue-800 rounded-md p-4 bg-blue-50 dark:bg-blue-950">
        <div className="text-sm">
          已 approve，等后台渲染（每分钟轮询一次）。
        </div>
      </section>
    );
  }

  return (
    <section>
      <div className="flex gap-3 flex-wrap">
        <button
          disabled={pending}
          onClick={() => {
            startTransition(async () => {
              if (await call("approve")) {
                router.refresh();
              }
            });
          }}
          className="px-4 py-2 text-sm font-medium bg-green-600 hover:bg-green-700 text-white rounded-md disabled:opacity-50"
        >
          {pending ? "..." : "✓ 通过 → 开始渲染"}
        </button>
        <button
          disabled={pending}
          onClick={() => setShowReject((x) => !x)}
          className="px-4 py-2 text-sm font-medium border border-neutral-300 dark:border-neutral-700 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-900"
        >
          {showReject ? "取消" : "✗ 驳回（留言）"}
        </button>
      </div>

      {showReject ? (
        <div className="mt-3 border border-neutral-200 dark:border-neutral-800 rounded-md p-3 bg-neutral-50 dark:bg-neutral-950">
          <label className="text-xs uppercase tracking-wider text-neutral-500 mb-1 block">
            评论 / 需要改什么
          </label>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={4}
            placeholder="例如：第 3 个 shot 的论点太弱，再展开一层；或者 thesis 偏了"
            className="w-full text-sm p-2 border border-neutral-300 dark:border-neutral-700 rounded bg-white dark:bg-neutral-900"
          />
          <div className="mt-2 flex gap-2 items-center">
            <button
              disabled={pending || !feedback.trim()}
              onClick={() => {
                startTransition(async () => {
                  if (await call("reject", { feedback: feedback.trim() })) {
                    setFeedback("");
                    setShowReject(false);
                    router.refresh();
                  }
                });
              }}
              className="px-3 py-1.5 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded-md disabled:opacity-50"
            >
              提交驳回
            </button>
            <span className="text-xs text-neutral-500">
              评论会存进 DB；目前不会自动重跑（手动 SSH 重跑 produce-script.py 即可）。
            </span>
          </div>
        </div>
      ) : null}

      {error ? (
        <p className="mt-3 text-sm text-red-600">{error}</p>
      ) : null}
    </section>
  );
}
