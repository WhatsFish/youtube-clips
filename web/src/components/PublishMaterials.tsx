"use client";

import { useState } from "react";

type Props = {
  platform: string;
  category: string | null;
  categoryLabel: string;
  title: string | null;
  description: string | null;
  tags: string[];
  coverUrls: string[];
  publishUrl: string | null;
  renderUrl: string | null;        // download / inline-play link to this platform's mp4
  downloadFilename?: string;       // friendly basename for the download attr (no extension)
};

const PLATFORM_LABEL: Record<string, string> = {
  bilibili_long: "B 站长视频",
  bilibili_vertical: "B 站竖屏",
  douyin: "抖音",
  tiktok: "TikTok",
  youtube_long: "YouTube",
  youtube_shorts: "YouTube Shorts",
};

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          // ignore
        }
      }}
      className="text-xs px-2 py-0.5 rounded border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800"
    >
      {copied ? "✓ 已复制" : label}
    </button>
  );
}

export default function PublishMaterials({
  platform,
  category,
  categoryLabel,
  title,
  description,
  tags,
  coverUrls,
  publishUrl,
  renderUrl,
  downloadFilename,
}: Props) {
  const downloadName = downloadFilename
    ? `${downloadFilename}-${platform}.mp4`
    : undefined;
  const platformLabel = PLATFORM_LABEL[platform] ?? platform;
  const tagsString = tags.join(", ");

  // Don't render section if there's literally nothing yet (no covers + no
  // materials beyond what the basic render gave us).
  const hasMaterials = coverUrls.length > 0 || category;
  if (!hasMaterials && !title) return null;

  return (
    <section className="mb-8 border border-neutral-200 dark:border-neutral-800 rounded-md">
      <header className="px-4 py-2.5 border-b border-neutral-200 dark:border-neutral-800 flex items-baseline justify-between gap-2 flex-wrap">
        <h2 className="text-sm font-semibold">{platformLabel} 发布信息</h2>
        <div className="flex items-baseline gap-3 text-xs">
          {renderUrl ? (
            <a
              href={renderUrl}
              target="_blank"
              rel="noreferrer"
              className="underline text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100"
              download={downloadName ?? true}
            >
              下载视频 ↓
            </a>
          ) : null}
          {publishUrl ? (
            <a
              href={publishUrl}
              target="_blank"
              rel="noreferrer"
              className="underline text-green-700 dark:text-green-400"
            >
              已发布 ↗
            </a>
          ) : (
            <span className="text-neutral-500">未发布</span>
          )}
        </div>
      </header>

      <div className="p-4 space-y-4">
        {renderUrl ? (
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
              视频预览
            </div>
            <video
              controls
              preload="metadata"
              className={
                "rounded-md bg-black " +
                // Portrait platforms get a narrower max-width so the
                // 9:16 player doesn't dominate the page; landscape
                // ones fill the full container.
                (platform === "douyin" || platform === "tiktok" ||
                 platform === "youtube_shorts"
                  ? "max-h-[60vh] w-auto mx-auto block"
                  : "w-full aspect-video")
              }
              src={renderUrl}
            >
              您的浏览器不支持视频播放。
            </video>
          </div>
        ) : null}

        {coverUrls.length > 0 ? (
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-2">
              封面候选 ({coverUrls.length})
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {coverUrls.map((u, i) => (
                <a
                  key={i}
                  href={u}
                  target="_blank"
                  rel="noreferrer"
                  className="block group"
                  title="点击在新页打开原图"
                >
                  <img
                    src={u}
                    alt={`cover ${i + 1}`}
                    className="w-full aspect-[16/10] object-cover rounded border border-neutral-300 dark:border-neutral-700 group-hover:opacity-80 transition"
                  />
                  <div className="text-[10px] text-neutral-500 text-center mt-0.5">
                    #{i + 1}
                  </div>
                </a>
              ))}
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 sm:grid-cols-[120px_1fr] gap-y-2 gap-x-3 text-sm">
          <div className="text-xs uppercase tracking-wider text-neutral-500 pt-0.5">
            标题
          </div>
          <div className="flex items-start gap-2">
            <div className="font-medium">{title ?? "—"}</div>
            {title ? <CopyButton text={title} label="复制" /> : null}
          </div>

          <div className="text-xs uppercase tracking-wider text-neutral-500 pt-0.5">
            分区
          </div>
          <div>{categoryLabel}</div>

          <div className="text-xs uppercase tracking-wider text-neutral-500 pt-0.5">
            简介
          </div>
          <div>
            <div className="whitespace-pre-line text-sm text-neutral-700 dark:text-neutral-300">
              {description ?? "—"}
            </div>
            {description ? (
              <div className="mt-1">
                <CopyButton text={description} label="复制简介" />
              </div>
            ) : null}
          </div>

          <div className="text-xs uppercase tracking-wider text-neutral-500 pt-0.5">
            标签
          </div>
          <div>
            <div className="flex flex-wrap gap-1.5 mb-1">
              {tags.map((t) => (
                <span
                  key={t}
                  className="text-xs px-2 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded"
                >
                  {t}
                </span>
              ))}
            </div>
            {tags.length > 0 ? (
              <CopyButton text={tagsString} label="复制标签（逗号分隔）" />
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
