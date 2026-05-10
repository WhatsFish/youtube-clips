"use client";

import { useState } from "react";

/** Small client component: copy a string to clipboard and flash a "copied"
 *  state for 2s. Used to copy the pre-built `produce.py` invocation. */
export default function CopyButton({
  text,
  className,
  children,
}: {
  text: string;
  className?: string;
  children?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          // Fallback: do nothing visible — operator can still hand-select
          // the <code> block. Avoids a janky alert() if clipboard access
          // is blocked (e.g. http on localhost without permission).
        }
      }}
      className={
        className ??
        "text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-700 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800"
      }
    >
      {copied ? "copied ✓" : (children ?? "copy")}
    </button>
  );
}
