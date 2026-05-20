import Link from "next/link";
import { listArchivalCache, fmtBytes, fmtDuration } from "@/lib/assets";

export const dynamic = "force-dynamic";

export default async function AssetsPage() {
  const assets = await listArchivalCache();

  const totalSize = assets.reduce((a, b) => a + b.fileSizeBytes, 0);
  const ytCount = assets.filter((a) => a.source === "youtube").length;
  const biliCount = assets.filter((a) => a.source === "bilibili").length;
  const reusedCount = assets.filter((a) => a.usedCount > 1).length;
  const orphanCount = assets.filter((a) => a.usedCount === 0).length;

  return (
    <main className="max-w-6xl mx-auto px-5 py-10">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← back
      </Link>
      <header className="mt-4 mb-6">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">archival 缓存池</h1>
        <p className="text-sm text-neutral-500">
          已下载的 YouTube / B站 源视频。agent 写脚本时优先从这里挑，省下重复下载。
        </p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <Stat label="总数" value={assets.length.toString()} />
        <Stat label="占盘" value={fmtBytes(totalSize)} />
        <Stat label="YouTube" value={ytCount.toString()} />
        <Stat label="B 站" value={biliCount.toString()} />
        <Stat label="未被使用" value={orphanCount.toString()} hint={`${reusedCount} 个被多次使用`} />
      </div>

      <div className="overflow-x-auto border border-neutral-200 dark:border-neutral-800 rounded-md">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 dark:bg-neutral-900 text-neutral-500 text-xs uppercase tracking-wider">
            <tr>
              <th className="text-left px-3 py-2 font-medium">源</th>
              <th className="text-left px-3 py-2 font-medium">标题 / 频道</th>
              <th className="text-right px-3 py-2 font-medium">时长</th>
              <th className="text-right px-3 py-2 font-medium">盘</th>
              <th className="text-right px-3 py-2 font-medium">用过</th>
              <th className="text-left px-3 py-2 font-medium">profile</th>
              <th className="text-left px-3 py-2 font-medium">抓取</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {assets.map((a) => (
              <tr key={`${a.source}-${a.videoId}`} className="hover:bg-neutral-50 dark:hover:bg-neutral-900">
                <td className="px-3 py-2">
                  <span
                    className={
                      a.source === "youtube"
                        ? "text-xs font-mono text-red-700 dark:text-red-400"
                        : "text-xs font-mono text-pink-700 dark:text-pink-400"
                    }
                  >
                    {a.source === "youtube" ? "YT" : "B站"}
                  </span>
                </td>
                <td className="px-3 py-2 max-w-md">
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline"
                  >
                    {a.title ?? <span className="text-neutral-400 italic">(无标题)</span>}
                  </a>
                  <div className="text-xs text-neutral-500 truncate">
                    {a.channel ?? "—"}
                    <span className="ml-2 font-mono text-neutral-400">{a.videoId}</span>
                  </div>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs text-neutral-600 dark:text-neutral-400">
                  {fmtDuration(a.durationSec)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs text-neutral-600 dark:text-neutral-400">
                  {fmtBytes(a.fileSizeBytes)}
                </td>
                <td className="px-3 py-2 text-right">
                  <span
                    className={
                      a.usedCount === 0
                        ? "text-neutral-400"
                        : a.usedCount === 1
                          ? "text-neutral-700 dark:text-neutral-300"
                          : "text-emerald-700 dark:text-emerald-400 font-medium"
                    }
                  >
                    {a.usedCount}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs text-neutral-500">
                  {a.profileName ?? <span className="italic text-neutral-400">—</span>}
                </td>
                <td className="px-3 py-2 text-xs text-neutral-500 font-mono">
                  {fmtFetchedAt(a.fetchedAt)}
                </td>
              </tr>
            ))}
            {assets.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-neutral-500">
                  缓存池还没东西。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="border border-neutral-200 dark:border-neutral-800 rounded-md px-3 py-2">
      <div className="text-xs uppercase tracking-wider text-neutral-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-neutral-500 mt-0.5">{hint}</div>}
    </div>
  );
}

function fmtFetchedAt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toISOString().slice(0, 10);
}
