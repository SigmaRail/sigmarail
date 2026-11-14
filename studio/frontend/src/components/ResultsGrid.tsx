import { formatNum, formatVol } from "../lib/utils";
import type { RankedRow } from "../types";
import { TradingViewMiniEmbed } from "./TradingViewMiniEmbed";

const GRID_CHUNK = 12;

export function ResultsGrid({
  rows,
  selectedTicker,
  onSelect,
  visibleCount,
  onLoadMore,
  loading,
}: {
  rows: RankedRow[];
  selectedTicker: string | null;
  onSelect: (row: RankedRow) => void;
  visibleCount: number;
  onLoadMore: () => void;
  loading?: boolean;
}) {
  const visible = rows.slice(0, visibleCount);
  const hasMore = visibleCount < rows.length;

  return (
    <div className="relative min-h-0 flex-1 overflow-auto p-3">
      {loading ? (
        <div className="absolute inset-0 z-10 flex items-start justify-center bg-surface-raised/60 pt-16 text-xs text-ink-muted">
          Loading preview…
        </div>
      ) : null}

      {rows.length === 0 && !loading ? (
        <p className="py-8 text-center text-xs text-ink-muted">
          No names for this as-of / screen
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visible.map((row) => {
              const selected = row.ticker === selectedTicker;
              const dropped = row.delta === "dropped";
              const exchange =
                typeof row.exchange === "string" ? row.exchange : null;
              return (
                <div
                  key={`${row.ticker}-${row.rank}-${row.delta}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(row)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(row);
                    }
                  }}
                  className={`flex cursor-pointer flex-col overflow-hidden rounded border text-left transition-colors ${
                    selected
                      ? "border-highlight bg-highlight-soft ring-2 ring-highlight/40 ring-offset-1 ring-offset-surface-raised"
                      : "border-line bg-surface-sunk hover:border-ink-faint"
                  } ${dropped ? "opacity-55" : ""}`}
                >
                  <div className="flex items-baseline justify-between gap-2 px-2.5 pt-2">
                    <span className="font-mono text-[13px] font-semibold tracking-wide text-ink">
                      {row.ticker}
                    </span>
                    <span className="font-mono text-[10px] text-ink-faint">
                      #{dropped ? "—" : row.rank}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 px-2.5 pb-1.5 pt-0.5 font-mono text-[10px] text-ink-muted">
                    <span>RS {formatNum(row.rs_rating, 0)}</span>
                    <span>TA {formatNum(row.technical_rating, 0)}</span>
                    <span>Setup {formatNum(row.setup_quality_rating, 0)}</span>
                    <span>
                      HGM {formatNum(row.high_growth_momentum_rating, 0)}
                    </span>
                    <span>Vol {formatVol(row.avg_vol_50d)}</span>
                  </div>
                  <div className="w-full border-t border-line/60 bg-[#131722]">
                    <TradingViewMiniEmbed
                      symbol={row.ticker}
                      exchange={exchange}
                      height={168}
                      dateRange="12M"
                      className="w-full"
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {hasMore ? (
            <div className="mt-3 flex justify-center">
              <button
                type="button"
                onClick={onLoadMore}
                className="rounded border border-line bg-surface-raised px-3 py-1.5 text-[12px] font-medium text-ink hover:border-accent hover:bg-accent-soft"
              >
                Load more ({Math.min(GRID_CHUNK, rows.length - visibleCount)} of{" "}
                {rows.length - visibleCount} remaining)
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export const RESULTS_GRID_CHUNK = GRID_CHUNK;
