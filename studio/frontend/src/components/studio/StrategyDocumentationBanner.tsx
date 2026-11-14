import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { BacktestSpecSummary, BacktestRunSummary } from "../../types";

interface StrategyDocumentationBannerProps {
  spec?: BacktestSpecSummary | null;
  defaultExpanded?: boolean;
}

/** Lightweight safe markdown-like line renderer without heavy dependencies. */
function renderMarkdownContent(text: string) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: string[] = [];

  function flushList(keyPrefix: string) {
    if (currentList.length === 0) return;
    elements.push(
      <ul key={`${keyPrefix}-list`} className="my-2 space-y-1 pl-5 list-disc text-ink/90 text-[12.5px]">
        {currentList.map((item, idx) => (
          <li key={idx} className="leading-relaxed">
            {renderInlineSpans(item)}
          </li>
        ))}
      </ul>
    );
    currentList = [];
  }

  function renderInlineSpans(lineText: string): React.ReactNode[] {
    // Basic inline formatting for **bold** and `code`
    const parts = lineText.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={i} className="font-semibold text-ink">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return (
          <code
            key={i}
            className="rounded bg-surface-sunk border border-line px-1 py-0.5 font-mono text-[11px] text-accent font-medium"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
  }

  lines.forEach((line, idx) => {
    const trimmed = line.trim();

    // Empty line separates paragraphs and flushes lists
    if (!trimmed) {
      flushList(`flush-${idx}`);
      return;
    }

    // Unordered list item
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      currentList.push(trimmed.slice(2));
      return;
    }

    flushList(`flush-${idx}`);

    // Headers
    if (trimmed.startsWith("# ")) {
      elements.push(
        <h2 key={idx} className="mt-3 mb-2 text-[15px] font-bold text-ink border-b border-line pb-1">
          {renderInlineSpans(trimmed.slice(2))}
        </h2>
      );
      return;
    }
    if (trimmed.startsWith("## ")) {
      elements.push(
        <h3 key={idx} className="mt-3.5 mb-1.5 text-[13.5px] font-semibold text-accent flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-accent/80" />
          <span>{renderInlineSpans(trimmed.slice(3))}</span>
        </h3>
      );
      return;
    }
    if (trimmed.startsWith("### ")) {
      elements.push(
        <h4 key={idx} className="mt-2.5 mb-1 text-[12.5px] font-semibold text-ink-muted">
          {renderInlineSpans(trimmed.slice(4))}
        </h4>
      );
      return;
    }

    // Standard paragraph line
    elements.push(
      <p key={idx} className="my-1.5 text-[12px] leading-relaxed text-ink/80">
        {renderInlineSpans(trimmed)}
      </p>
    );
  });

  flushList("final");
  return elements;
}

export function StrategyDocumentationBanner({
  spec,
  defaultExpanded = true,
}: StrategyDocumentationBannerProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const navigate = useNavigate();

  const irId = spec?.ir_id;
  const lineage = (spec?.lineage as {
    parent_ir_id?: string;
    parent_content_hash?: string;
    mutation_type?: string;
    changelog_notes?: string;
    author_agent?: string;
  } | undefined);
  const parentIrId = lineage?.parent_ir_id;

  const currentRunQuery = useQuery({
    queryKey: ["latest-run-for-spec", irId],
    queryFn: async () => {
      if (!irId) return null;
      const res = await fetch(`/api/backtests/runs?ir_id=${encodeURIComponent(irId)}&limit=1`);
      if (!res.ok) return null;
      const json = await res.json();
      return (json.runs?.[0] as BacktestRunSummary) ?? null;
    },
    enabled: Boolean(irId),
  });

  const parentRunQuery = useQuery({
    queryKey: ["latest-run-for-spec", parentIrId],
    queryFn: async () => {
      if (!parentIrId) return null;
      const res = await fetch(`/api/backtests/runs?ir_id=${encodeURIComponent(parentIrId)}&limit=1`);
      if (!res.ok) return null;
      const json = await res.json();
      return (json.runs?.[0] as BacktestRunSummary) ?? null;
    },
    enabled: Boolean(parentIrId),
  });

  if (!spec) return null;

  const notes = typeof spec.notes === "string" ? spec.notes.trim() : "";
  const hasDocumentation = Boolean(notes || lineage?.changelog_notes);
  if (!hasDocumentation && !currentRunQuery.data) return null;

  // TL;DR preview is the first non-header line
  const firstParagraph = notes
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.length > 0 && !l.startsWith("#")) || lineage?.changelog_notes || "";

  const currentRun = currentRunQuery.data;
  const parentRun = parentRunQuery.data;

  return (
    <div className="rounded-lg border border-accent/25 bg-surface-raised shadow-sm overflow-hidden transition-all">
      {/* Banner Header */}
      <div
        className="flex items-center justify-between px-3.5 py-2.5 bg-surface-sunk/60 cursor-pointer select-none border-b border-line hover:bg-surface-sunk transition-colors"
        onClick={() => setIsExpanded((prev) => !prev)}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px]">📖</span>
          <span className="text-[12px] font-bold text-ink">Strategy Rationale & Notes</span>

          {lineage?.mutation_type && (
            <span className="rounded bg-accent/10 border border-accent/30 px-1.5 py-0.5 text-[10px] font-semibold text-accent capitalize">
              {lineage.mutation_type}
            </span>
          )}

          {lineage?.parent_ir_id && (
            <span className="rounded bg-surface-raised border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
              parent: {lineage.parent_ir_id}
            </span>
          )}

          {lineage?.author_agent && (
            <span className="rounded bg-surface-raised border border-line px-1.5 py-0.5 text-[10px] text-ink-muted">
              author: {lineage.author_agent}
            </span>
          )}
        </div>

        <button
          type="button"
          className="text-[11px] font-medium text-accent hover:underline flex items-center gap-1"
          onClick={(e) => {
            e.stopPropagation();
            setIsExpanded((prev) => !prev);
          }}
        >
          <span>{isExpanded ? "Collapse" : "Show Rationale"}</span>
          <span className="text-[10px]">{isExpanded ? "▲" : "▼"}</span>
        </button>
      </div>

      {/* Live Performance & Compare Parent Bar */}
      {currentRun && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/60 bg-surface-sunk/30 px-3.5 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-ink-muted">📊 Latest Backtest:</span>

            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[11px] font-bold ${
                (currentRun.total_return ?? 0) >= 0
                  ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                  : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
              }`}
            >
              Return: {((currentRun.total_return ?? 0) * 100).toFixed(1)}%
            </span>

            <span className="rounded bg-surface-raised border border-line px-1.5 py-0.5 font-mono text-[11px] text-ink">
              Sharpe: {(currentRun.sharpe_ratio ?? 0).toFixed(2)}
            </span>

            <span className="rounded bg-surface-raised border border-line px-1.5 py-0.5 font-mono text-[11px] text-ink">
              Win: {((currentRun.win_rate ?? 0) * 100).toFixed(0)}%
            </span>

            <span className="rounded bg-surface-raised border border-line px-1.5 py-0.5 font-mono text-[11px] text-ink">
              DD: {((currentRun.max_drawdown ?? 0) * 100).toFixed(1)}%
            </span>

            <span className="rounded bg-surface-raised border border-line px-1.5 py-0.5 font-mono text-[11px] text-ink">
              Orders: {currentRun.total_orders ?? 0}
            </span>
          </div>

          {parentRun && (
            <div className="flex items-center gap-2">
              {(() => {
                const sharpeDiff = (currentRun.sharpe_ratio ?? 0) - (parentRun.sharpe_ratio ?? 0);
                const retDiff = ((currentRun.total_return ?? 0) - (parentRun.total_return ?? 0)) * 100;
                return (
                  <div className="hidden sm:flex items-center gap-1.5 text-[10.5px] font-mono">
                    <span
                      className={`font-semibold ${
                        sharpeDiff >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {sharpeDiff >= 0 ? `▲ +${sharpeDiff.toFixed(2)} Sharpe` : `▼ ${sharpeDiff.toFixed(2)} Sharpe`}
                    </span>
                    <span
                      className={`font-semibold ${
                        retDiff >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      ({retDiff >= 0 ? `+${retDiff.toFixed(1)}%` : `${retDiff.toFixed(1)}%`})
                    </span>
                    <span className="text-ink-faint">vs parent</span>
                  </div>
                );
              })()}

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/backtests?compare_runs=${currentRun.run_id},${parentRun.run_id}&view=compare`);
                }}
                className="flex items-center gap-1 rounded bg-accent/15 border border-accent/40 px-2.5 py-1 text-[11px] font-semibold text-accent hover:bg-accent/25 transition-colors cursor-pointer"
                title={`Compare ${spec.ir_id} against parent ${parentIrId}`}
              >
                <span>⚔️</span>
                <span>Compare with Parent</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Collapsed Snippet */}
      {!isExpanded && firstParagraph && (
        <div
          className="px-3.5 py-2 text-[11.5px] text-ink-muted cursor-pointer hover:bg-surface-sunk/30 transition-colors flex items-center justify-between"
          onClick={() => setIsExpanded(true)}
        >
          <span className="truncate max-w-[85%]">{firstParagraph}</span>
          <span className="text-[10px] text-accent font-medium">Read more &rarr;</span>
        </div>
      )}

      {/* Expanded Rich Notes & Changelog */}
      {isExpanded && (
        <div className="px-4 py-3.5 bg-surface text-ink text-left space-y-3 max-h-[500px] overflow-y-auto">
          {/* Changelog Callout if present */}
          {lineage?.changelog_notes && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2.5 text-[11.5px] text-amber-200 leading-snug">
              <span className="font-bold text-amber-300">Version Changelog: </span>
              <span>{lineage.changelog_notes}</span>
            </div>
          )}

          {/* Formatted Notes */}
          {notes ? (
            <div className="prose prose-sm max-w-none text-ink text-[12px]">
              {renderMarkdownContent(notes)}
            </div>
          ) : (
            <p className="text-[11.5px] text-ink-muted italic">No detailed strategy notes authored yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
