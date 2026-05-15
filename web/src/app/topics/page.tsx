import Link from "next/link";
import { listPendingTopics, listApprovedTopics } from "@/lib/topics";
import TopicsView from "@/components/TopicsView";

export const dynamic = "force-dynamic";

export default async function TopicsPage() {
  const [pending, approved] = await Promise.all([
    listPendingTopics(),
    listApprovedTopics(),
  ]);
  const waiting = approved.filter((t) => !t.rendered);
  const rendered = approved.filter((t) => t.rendered);

  return (
    <main className="max-w-5xl mx-auto px-5 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>
      <header className="mt-4 mb-6">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">topic 选题</h1>
        <p className="text-sm text-neutral-500">
          Agent 从 RSS / YouTube 等源挖出的候选；按生命周期切换。
        </p>
      </header>

      <TopicsView pending={pending} waiting={waiting} rendered={rendered} />
    </main>
  );
}
