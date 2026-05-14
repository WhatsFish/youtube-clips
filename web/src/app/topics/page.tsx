import Link from "next/link";
import { listPendingTopics, listApprovedTopics, type Topic } from "@/lib/topics";
import TopicCard from "@/components/TopicCard";

export const dynamic = "force-dynamic";

function groupByProfile(topics: Topic[]): Map<string, Topic[]> {
  const m = new Map<string, Topic[]>();
  for (const t of topics) {
    if (!m.has(t.profileName)) m.set(t.profileName, []);
    m.get(t.profileName)!.push(t);
  }
  return m;
}

export default async function TopicsPage() {
  const [pending, approved] = await Promise.all([
    listPendingTopics(),
    listApprovedTopics(),
  ]);
  const waiting = approved.filter((t) => !t.rendered);
  const rendered = approved.filter((t) => t.rendered);

  return (
    <main className="max-w-3xl mx-auto px-5 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>
      <header className="mt-4 mb-8">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">topic 选题</h1>
        <p className="text-sm text-neutral-500">
          Agent 从 RSS / YouTube 等源挖出的候选；按状态分组显示生命周期。
        </p>
      </header>

      {/* 待审批 */}
      <Section title="待审批" count={pending.length}>
        {pending.length === 0 ? (
          <Empty>
            目前没有待审批的 topic。下次 cron（09:00 UTC）会拉一批新候选；
            手动跑：
            <code className="text-xs bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded ml-1">
              scripts/run-discover-topics.sh
            </code>
          </Empty>
        ) : (
          <ProfileGrouped topics={pending} variant="pending" />
        )}
      </Section>

      {/* 已通过待制作 */}
      <Section title="已通过 · 待制作" count={waiting.length}>
        {waiting.length === 0 ? (
          <Empty>没有待制作 topic。通过的 topic 会出现在这里直到渲染完成。</Empty>
        ) : (
          <ProfileGrouped topics={waiting} variant="waiting" />
        )}
      </Section>

      {/* 已制作 */}
      <Section title="已通过 · 已制作" count={rendered.length}>
        {rendered.length === 0 ? (
          <Empty>还没有视频做出来。</Empty>
        ) : (
          <ProfileGrouped topics={rendered} variant="rendered" />
        )}
      </Section>
    </main>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-10">
      <h2 className="text-base font-semibold mb-3 flex items-baseline gap-2">
        {title}
        <span className="text-xs text-neutral-500 font-normal">({count})</span>
      </h2>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-4 text-sm text-neutral-500">
      {children}
    </div>
  );
}

function ProfileGrouped({
  topics,
  variant,
}: {
  topics: Topic[];
  variant: "pending" | "waiting" | "rendered";
}) {
  const groups = groupByProfile(topics);
  return (
    <>
      {Array.from(groups.entries()).map(([profile, ts]) => (
        <div key={profile} className="mb-5">
          <h3 className="font-mono text-sm font-semibold mb-2 text-neutral-600 dark:text-neutral-400">
            {profile}{" "}
            <span className="text-xs text-neutral-500 font-sans font-normal">
              ({ts.length})
            </span>
          </h3>
          {variant === "pending" ? (
            <ul className="space-y-3">
              {ts.map((t) => (
                <TopicCard key={t.id} topic={t} />
              ))}
            </ul>
          ) : (
            <ul className="space-y-1.5">
              {ts.map((t) => (
                <ApprovedTopicRow key={t.id} topic={t} variant={variant} />
              ))}
            </ul>
          )}
        </div>
      ))}
    </>
  );
}

function ApprovedTopicRow({
  topic,
  variant,
}: {
  topic: Topic;
  variant: "waiting" | "rendered";
}) {
  const isRendered = variant === "rendered";
  const link = isRendered && topic.renderedSlug
    ? `/youtube-clips/jobs/${encodeURIComponent(topic.renderedSlug)}`
    : null;
  const body = (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span
        className={
          "text-[10px] px-1.5 py-0.5 rounded uppercase " +
          (isRendered
            ? "bg-green-500/15 text-green-700 dark:text-green-300"
            : "bg-amber-500/15 text-amber-700 dark:text-amber-300")
        }
      >
        {isRendered ? "已制作" : "待制作"}
      </span>
      <span className="text-sm">{topic.title}</span>
      <span className="text-xs text-neutral-500 ml-auto">#{topic.id}</span>
    </div>
  );
  return (
    <li
      className={
        "border rounded-md p-2.5 text-sm " +
        "border-neutral-200 dark:border-neutral-800 " +
        (link ? "hover:bg-neutral-100 dark:hover:bg-neutral-900 transition" : "")
      }
    >
      {link ? (
        <Link href={link} className="block">
          {body}
        </Link>
      ) : (
        body
      )}
    </li>
  );
}
