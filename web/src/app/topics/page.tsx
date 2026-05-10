import Link from "next/link";
import { query } from "@/lib/db";
import {
  listTopics,
  groupTopicsByProfile,
  produceCommand,
  type Topic,
  type TopicStatus,
} from "@/lib/topics";
import { addTopic, updateTopicStatus, deleteTopic } from "./actions";
import CopyButton from "./CopyButton";

export const dynamic = "force-dynamic";

type ProfileRow = {
  id: number;
  name: string;
  description: string | null;
  active: boolean;
};

const STATUS_LABEL: Record<TopicStatus, string> = {
  pending: "pending",
  approved: "approved",
  rejected: "rejected",
  done: "done",
};

const STATUS_BADGE_CLASS: Record<TopicStatus, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  approved: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  done: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  rejected: "bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-500",
};

function fmtTime(d: Date | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleString("zh-CN", {
    timeZone: "Asia/Tokyo",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function TopicsPage() {
  let profiles: ProfileRow[] = [];
  let dbError: string | null = null;
  try {
    profiles = await query<ProfileRow>(
      `SELECT id, name, description, active FROM profiles WHERE active ORDER BY id`,
    );
  } catch (e) {
    dbError = e instanceof Error ? e.message : String(e);
  }

  const topics = await listTopics();
  const byProfile = groupTopicsByProfile(topics);

  return (
    <main className="max-w-3xl mx-auto px-5 py-12">
      <header className="mb-6 flex items-baseline gap-4 flex-wrap">
        <h1 className="text-2xl font-semibold tracking-tight">topics</h1>
        <nav className="text-sm flex gap-3 text-neutral-500">
          <Link className="underline hover:text-neutral-900 dark:hover:text-neutral-100" href="/">
            renders
          </Link>
          <span className="text-neutral-900 dark:text-neutral-100">topics</span>
        </nav>
      </header>
      <p className="text-sm text-neutral-500 mb-8">
        Queue topics for any active profile. Each row shows the exact
        <code className="font-mono mx-1 text-xs">produce.py</code>
        command — copy + paste into your SSH session to run.
      </p>

      {dbError ? (
        <div className="mb-8 border border-red-300 dark:border-red-800 rounded-md p-4 text-sm">
          <p className="font-medium text-red-700 dark:text-red-400 mb-1">DB error</p>
          <pre className="text-xs whitespace-pre-wrap">{dbError}</pre>
        </div>
      ) : null}

      <AddTopicForm profiles={profiles} />

      {profiles.map((p) => {
        const ts = byProfile.get(p.name) ?? [];
        return <ProfileTopicsSection key={p.id} profile={p} topics={ts} />;
      })}
    </main>
  );
}

function AddTopicForm({ profiles }: { profiles: ProfileRow[] }) {
  return (
    <details className="mb-10 border border-neutral-200 dark:border-neutral-800 rounded-md">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium select-none">
        + add topic
      </summary>
      <form action={addTopic} className="px-4 py-4 border-t border-neutral-200 dark:border-neutral-800 grid gap-3">
        <label className="grid gap-1 text-sm">
          <span className="text-xs uppercase tracking-wider text-neutral-500">
            profile
          </span>
          <select
            name="profile_id"
            required
            defaultValue=""
            className="border border-neutral-300 dark:border-neutral-700 bg-transparent rounded px-2 py-1.5"
          >
            <option value="" disabled>
              choose…
            </option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="text-xs uppercase tracking-wider text-neutral-500">title</span>
          <input
            name="title"
            required
            placeholder='e.g. "Federal Reserve rate decision"'
            className="border border-neutral-300 dark:border-neutral-700 bg-transparent rounded px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="text-xs uppercase tracking-wider text-neutral-500">
            description (optional)
          </span>
          <textarea
            name="description"
            rows={2}
            className="border border-neutral-300 dark:border-neutral-700 bg-transparent rounded px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="text-xs uppercase tracking-wider text-neutral-500">
            keywords (comma-separated, optional)
          </span>
          <input
            name="keywords"
            placeholder="fed, rates, macro"
            className="border border-neutral-300 dark:border-neutral-700 bg-transparent rounded px-2 py-1.5"
          />
        </label>
        <div>
          <button
            type="submit"
            className="text-sm px-4 py-1.5 border border-neutral-300 dark:border-neutral-700 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            add
          </button>
        </div>
      </form>
    </details>
  );
}

function ProfileTopicsSection({
  profile,
  topics,
}: {
  profile: ProfileRow;
  topics: Topic[];
}) {
  return (
    <section className="mb-10">
      <header className="mb-3 flex items-baseline gap-3">
        <h2 className="font-mono text-base font-semibold">{profile.name}</h2>
        <span className="text-xs text-neutral-500">
          {topics.length} {topics.length === 1 ? "topic" : "topics"}
        </span>
      </header>
      {topics.length === 0 ? (
        <div className="border border-dashed border-neutral-300 dark:border-neutral-700 rounded-md p-4 text-sm text-neutral-500">
          No topics for this profile yet.
        </div>
      ) : (
        <ul className="space-y-3">
          {topics.map((t) => (
            <TopicCard key={t.id} topic={t} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TopicCard({ topic }: { topic: Topic }) {
  const cmd = produceCommand(topic.profileName, topic.title);
  const canDelete = topic.jobCount === 0;
  return (
    <li className="border border-neutral-200 dark:border-neutral-800 rounded-md p-4">
      <div className="flex items-start gap-3 flex-wrap mb-2">
        <span
          className={`text-xs px-2 py-0.5 rounded ${STATUS_BADGE_CLASS[topic.status]}`}
        >
          {STATUS_LABEL[topic.status]}
        </span>
        <span className="text-xs text-neutral-500">
          {topic.source === "human" ? "human" : "agent"}
        </span>
        {topic.jobCount > 0 ? (
          <span className="text-xs text-neutral-500">
            {topic.jobCount} run{topic.jobCount === 1 ? "" : "s"}
          </span>
        ) : null}
        <span className="text-xs text-neutral-500 ml-auto">
          {fmtTime(topic.generatedAt)}
        </span>
      </div>
      <div className="font-medium mb-1">{topic.title}</div>
      {topic.description ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-2">
          {topic.description}
        </p>
      ) : null}
      {topic.keywords.length > 0 ? (
        <div className="flex flex-wrap gap-1 mb-3">
          {topic.keywords.map((k) => (
            <span
              key={k}
              className="text-xs px-2 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded"
            >
              {k}
            </span>
          ))}
        </div>
      ) : null}

      <div className="bg-neutral-100 dark:bg-neutral-900 rounded p-2 mb-3">
        <code className="text-xs font-mono break-all">{cmd}</code>
      </div>

      <div className="flex flex-wrap gap-2">
        <CopyButton text={cmd}>copy command</CopyButton>
        {topic.status !== "done" ? (
          <form action={updateTopicStatus}>
            <input type="hidden" name="id" value={topic.id} />
            <input type="hidden" name="status" value="done" />
            <button
              type="submit"
              className="text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-700 rounded hover:bg-emerald-50 dark:hover:bg-emerald-900/40"
            >
              mark done
            </button>
          </form>
        ) : null}
        {topic.status !== "rejected" ? (
          <form action={updateTopicStatus}>
            <input type="hidden" name="id" value={topic.id} />
            <input type="hidden" name="status" value="rejected" />
            <button
              type="submit"
              className="text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-700 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500"
            >
              skip
            </button>
          </form>
        ) : null}
        {topic.status !== "pending" ? (
          <form action={updateTopicStatus}>
            <input type="hidden" name="id" value={topic.id} />
            <input type="hidden" name="status" value="pending" />
            <button
              type="submit"
              className="text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-700 rounded hover:bg-amber-50 dark:hover:bg-amber-900/40"
            >
              re-queue
            </button>
          </form>
        ) : null}
        {canDelete ? (
          <form action={deleteTopic} className="ml-auto">
            <input type="hidden" name="id" value={topic.id} />
            <button
              type="submit"
              className="text-xs px-2 py-1 text-red-600 dark:text-red-400 hover:underline"
            >
              delete
            </button>
          </form>
        ) : null}
      </div>
    </li>
  );
}
