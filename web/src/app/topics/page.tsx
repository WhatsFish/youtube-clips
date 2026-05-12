import Link from "next/link";
import { listPendingTopics } from "@/lib/topics";
import TopicCard from "@/components/TopicCard";

export const dynamic = "force-dynamic";

export default async function TopicsPage() {
  const topics = await listPendingTopics();
  const byProfile = new Map<string, typeof topics>();
  for (const t of topics) {
    if (!byProfile.has(t.profileName)) byProfile.set(t.profileName, []);
    byProfile.get(t.profileName)!.push(t);
  }

  return (
    <main className="max-w-3xl mx-auto px-5 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>
      <header className="mt-4 mb-8">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">
          待审批 topic
        </h1>
        <p className="text-sm text-neutral-500">
          Agent 从各 RSS 源挖出的候选选题。通过的进入 approved 状态，
          可手动复制 title 跑 produce-original.py。
        </p>
      </header>

      {topics.length === 0 ? (
        <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-6 text-sm text-neutral-500">
          目前没有待审批的 topic。运行{" "}
          <code className="text-xs bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded">
            scripts/discover-topics.py --all
          </code>{" "}
          拉一批新候选。
        </div>
      ) : (
        Array.from(byProfile.entries()).map(([profile, ts]) => (
          <section key={profile} className="mb-10">
            <h2 className="font-mono text-base font-semibold mb-3">
              {profile}{" "}
              <span className="text-xs text-neutral-500 font-sans">
                ({ts.length})
              </span>
            </h2>
            <ul className="space-y-3">
              {ts.map((t) => (
                <TopicCard key={t.id} topic={t} />
              ))}
            </ul>
          </section>
        ))
      )}
    </main>
  );
}
