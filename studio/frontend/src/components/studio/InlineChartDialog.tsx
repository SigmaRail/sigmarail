import { useEffect } from "react";
import { TradingViewEmbed } from "../TradingViewEmbed";
import type { RankedRow } from "../../types";

interface InlineChartDialogProps {
  row: RankedRow | null;
  onClose: () => void;
}

export function InlineChartDialog({ row, onClose }: InlineChartDialogProps) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!row) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex w-[min(900px,92vw)] flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden"
           style={{ height: "min(640px, 80vh)" }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-4 py-2.5">
          <div className="flex items-center gap-3">
            <span className="text-[15px] font-bold text-ink">{row.ticker}</span>
            <div className="flex items-center gap-2 text-[11px]">
              {row.close != null && (
                <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono font-semibold text-ink">
                  ${Number(row.close).toFixed(2)}
                </span>
              )}
              {row.rs_rating != null && (
                <span className="rounded bg-emerald-500/15 px-2 py-0.5 font-mono font-bold text-emerald-400">
                  RS {Math.round(Number(row.rs_rating))}
                </span>
              )}
              {row.technical_rating != null && (
                <span className="rounded bg-accent/15 px-2 py-0.5 font-mono font-bold text-accent-ink">
                  TA {Math.round(Number(row.technical_rating))}
                </span>
              )}
              {row.sector != null && (
                <span className="text-ink-muted">{String(row.sector)}</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(row.ticker)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11px] font-semibold text-ink-muted hover:text-ink hover:border-accent transition-colors"
            >
              Open in TradingView ↗
            </a>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11px] font-semibold text-ink-muted hover:text-ink transition-colors"
            >
              ✕ Close
            </button>
          </div>
        </div>

        {/* Chart */}
        <div className="flex-1 min-h-0 bg-[#131722]">
          <TradingViewEmbed
            symbol={row.ticker}
            exchange={typeof row.exchange === "string" ? row.exchange : null}
            className="h-full w-full"
          />
        </div>
      </div>
    </div>
  );
}
