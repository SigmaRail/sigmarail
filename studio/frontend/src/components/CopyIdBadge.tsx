import { useState } from "react";

export function CopyIdBadge({
  id,
  label,
  truncate = true,
  head = 8,
  tail = 6,
  sqlQuery,
  className = "",
}: {
  id: string;
  label?: string;
  truncate?: boolean;
  head?: number;
  tail?: number;
  sqlQuery?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [copiedSql, setCopiedSql] = useState(false);

  if (!id) return null;

  const displayId =
    truncate && id.length > head + tail + 2
      ? `${id.slice(0, head)}…${id.slice(-tail)}`
      : id;

  const handleCopyId = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API is restricted
      const textarea = document.createElement("textarea");
      textarea.value = id;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCopySql = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!sqlQuery) return;
    try {
      await navigator.clipboard.writeText(sqlQuery);
      setCopiedSql(true);
      setTimeout(() => setCopiedSql(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border border-line bg-surface-sunk/80 px-2 py-0.5 font-mono text-[10.5px] text-ink transition-colors hover:border-accent/40 ${className}`}
      title={`Click to copy full ID: ${id}`}
    >
      {label ? (
        <span className="text-[9px] uppercase font-bold text-ink-faint tracking-wider">
          {label}:
        </span>
      ) : null}
      <span className="font-semibold select-all">{displayId}</span>

      <button
        type="button"
        onClick={handleCopyId}
        className="rounded px-1 py-0.2 hover:bg-surface text-[10px] text-ink-muted hover:text-accent transition-colors"
        title="Copy ID to clipboard"
      >
        {copied ? "✓ Copied" : "📋"}
      </button>

      {sqlQuery ? (
        <button
          type="button"
          onClick={handleCopySql}
          className="rounded px-1 py-0.2 hover:bg-surface text-[9px] font-sans font-medium text-ink-faint hover:text-accent transition-colors"
          title={`Copy SQL query: ${sqlQuery}`}
        >
          {copiedSql ? "✓ SQL" : "SQL"}
        </button>
      ) : null}
    </span>
  );
}
