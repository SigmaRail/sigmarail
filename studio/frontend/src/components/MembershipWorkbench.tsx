import type { UIEvent } from "react";
import { cn } from "../lib/utils";
import type { OrderDirection } from "../types";
import { StockIntrospectionPanel } from "./studio/StockIntrospectionPanel";

export type MembershipRow = Record<string, unknown>;

function tickerOf(row: MembershipRow): string {
  return String(row.ticker ?? "")
    .trim()
    .toUpperCase();
}

/** MarketSurge chart under membership tables — Universe, Alpha, Screens. */
export function MembershipTickerInspect({
  ticker,
  asOfDate,
  onClose,
}: {
  ticker: string;
  asOfDate: string;
  onClose: () => void;
  /** @deprecated Unused — kept so callers can drop props gradually. */
  row?: MembershipRow | null;
  /** @deprecated Unused. */
  conditionCols?: string[];
  /** @deprecated Unused. */
  boolAliases?: ReadonlySet<string> | readonly string[];
  /** @deprecated Unused. */
  chartHeight?: number;
}) {
  return (
    <div className="mt-2 overflow-hidden rounded border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-surface-raised px-2.5 py-1.5">
        <span className="font-mono text-[10.5px] text-ink-muted">
          <span className="font-semibold text-ink">{ticker}</span>
          {" · "}
          as of <span className="text-ink">{asOfDate || "—"}</span>
          <span className="text-ink-faint"> (pinned time slice)</span>
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-danger hover:text-danger"
        >
          close chart
        </button>
      </div>
      <div className="min-h-[420px]">
        <StockIntrospectionPanel
          ticker={ticker}
          asOfDate={asOfDate}
          compact
          className="h-full min-h-[420px]"
        />
      </div>
    </div>
  );
}

/** Compact as-of membership table with clickable tickers (shared surfaces). */
export function MembershipAsOfTable({
  columns,
  rows,
  sortField,
  sortDir,
  sortableCols,
  selectedTicker,
  onSelectTicker,
  onSort,
  onScroll,
  loading = false,
  emptyLabel = "No members for this date.",
  hint,
}: {
  columns: string[];
  rows: MembershipRow[];
  sortField: string;
  sortDir: OrderDirection;
  sortableCols?: ReadonlySet<string>;
  selectedTicker: string | null;
  onSelectTicker: (ticker: string) => void;
  onSort: (col: string) => void;
  onScroll?: (e: UIEvent<HTMLDivElement>) => void;
  loading?: boolean;
  emptyLabel?: string;
  hint?: string;
}) {
  const canSort = (col: string) =>
    sortableCols ? sortableCols.has(col) : col !== "exchange";

  return (
    <div className="space-y-1">
      <div
        className="max-h-52 overflow-auto rounded border border-line bg-surface"
        onScroll={onScroll}
      >
        <table className="w-full text-left font-mono text-[10px]">
          <thead>
            <tr>
              {columns.map((col) => {
                const sortable = canSort(col);
                const active = sortField === col;
                if (!sortable) {
                  return (
                    <th
                      key={col}
                      className="sticky top-0 bg-surface px-1 py-0.5 font-normal text-ink-faint"
                    >
                      {col}
                    </th>
                  );
                }
                return (
                  <th
                    key={col}
                    className="sticky top-0 bg-surface px-1 py-0.5 font-normal"
                  >
                    <button
                      type="button"
                      onClick={() => onSort(col)}
                      className={cn(
                        "inline-flex items-center gap-0.5 hover:text-ink",
                        active ? "text-ink font-semibold" : "text-ink-faint",
                      )}
                      title={`Sort by ${col}`}
                    >
                      {col}
                      {active ? (
                        <span aria-hidden>{sortDir === "desc" ? "▼" : "▲"}</span>
                      ) : null}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const ticker = tickerOf(row);
              const selected = selectedTicker === ticker;
              return (
                <tr
                  key={`${ticker}-${i}`}
                  className={cn(
                    "border-t border-line/60",
                    selected && "bg-accent/10",
                  )}
                >
                  {columns.map((col) =>
                    col === "ticker" ? (
                      <td key={col} className="px-1 py-0.5">
                        <button
                          type="button"
                          onClick={() => onSelectTicker(ticker)}
                          className={cn(
                            "font-mono font-semibold underline-offset-2 hover:underline hover:text-accent",
                            selected ? "text-accent" : "text-ink",
                          )}
                          title={`Chart ${ticker}`}
                        >
                          {ticker}
                        </button>
                      </td>
                    ) : (
                      <td key={col} className="px-1 py-0.5 text-ink">
                        {String(row[col] ?? "")}
                      </td>
                    ),
                  )}
                </tr>
              );
            })}
            {!loading && !rows.length && (
              <tr>
                <td
                  colSpan={Math.max(columns.length, 1)}
                  className="px-1 py-2 text-ink-faint"
                >
                  {emptyLabel}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {hint ? (
        <p className="font-mono text-[10px] text-ink-faint">{hint}</p>
      ) : null}
    </div>
  );
}
