import type { ReactNode, UIEvent } from "react";
import { cn } from "../lib/utils";
import type { OrderDirection } from "../types";
import { StockIntrospectionPanel } from "./studio/StockIntrospectionPanel";
import { Button } from "@sb/webapp-core/components/ui/button";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

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
        <Button
          type="button"
          onClick={onClose}
          variant="outline"
          size="sm"
          className="h-7 px-2 font-mono text-[10px]"
        >
          close chart
        </Button>
      </div>
      <div className="min-h-[360px] md:min-h-[420px]">
        <StockIntrospectionPanel
          ticker={ticker}
          asOfDate={asOfDate}
          compact
          className="h-full min-h-[360px] md:min-h-[420px]"
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
  columnLabels,
  formatCell,
  density = "compact",
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
  columnLabels?: Readonly<Record<string, string>>;
  formatCell?: (column: string, value: unknown, row: MembershipRow) => ReactNode;
  density?: "compact" | "comfortable";
}) {
  const readable = density === "comfortable";
  const canSort = (col: string) =>
    sortableCols ? sortableCols.has(col) : col !== "exchange";
  const isNumericColumn = (col: string) => {
    const value = rows.find((row) => row[col] != null)?.[col];
    return typeof value === "number" ||
      (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value)));
  };
  const columnLabel = (col: string) =>
    columnLabels?.[col] ?? (readable ? col.replaceAll("_", " ") : col);

  return (
    <div className="space-y-1">
      <div
        className={cn("max-h-52 overflow-auto rounded border border-line bg-surface", readable && "max-h-64")}
        onScroll={onScroll}
      >
        <WorkspaceTable className={cn("w-full text-left font-mono text-[10px]", readable && "font-sans text-xs")}>
          <WorkspaceTableHeader>
            <WorkspaceTableRow>
              {columns.map((col) => {
                const sortable = canSort(col);
                const active = sortField === col;
                if (!sortable) {
                  return (
                    <WorkspaceTableHead
                      key={col}
                      className={cn("sticky top-0 bg-surface px-1 py-0.5 font-normal text-ink-faint", readable && "whitespace-nowrap px-2 py-1.5 font-medium", readable && isNumericColumn(col) && "text-right")}
                    >
                      {columnLabel(col)}
                    </WorkspaceTableHead>
                  );
                }
                return (
                  <WorkspaceTableHead
                    key={col}
                    className={cn("sticky top-0 bg-surface px-1 py-0.5 font-normal", readable && "whitespace-nowrap px-2 py-1.5 font-medium", readable && isNumericColumn(col) && "text-right")}
                  >
                    <Button
                      type="button"
                      onClick={() => onSort(col)}
                      variant="ghost"
                      size="sm"
                      className={cn(
                        "h-auto gap-0.5 p-0 text-[10px]",
                        readable && "text-xs",
                        active ? "text-ink font-semibold" : "text-ink-faint",
                      )}
                      title={`Sort by ${col}`}
                    >
                      {columnLabel(col)}
                      {active ? (
                        <span aria-hidden>{sortDir === "desc" ? "▼" : "▲"}</span>
                      ) : null}
                    </Button>
                  </WorkspaceTableHead>
                );
              })}
            </WorkspaceTableRow>
          </WorkspaceTableHeader>
          <WorkspaceTableBody>
            {rows.map((row, i) => {
              const ticker = tickerOf(row);
              const selected = selectedTicker === ticker;
              return (
                <WorkspaceTableRow
                  key={`${ticker}-${i}`}
                  className={cn(
                    "border-t border-line/60",
                    selected && "bg-accent/10",
                  )}
                >
                  {columns.map((col) =>
                    col === "ticker" ? (
                      <WorkspaceTableCell key={col} className={cn("px-1 py-0.5", readable && "whitespace-nowrap px-2 py-1.5")}>
                        <Button
                          type="button"
                          onClick={() => onSelectTicker(ticker)}
                          variant="ghost"
                          size="sm"
                          className={cn(
                            "h-auto p-0 font-mono text-[10px] font-semibold underline-offset-2 hover:underline",
                            selected ? "text-accent" : "text-ink",
                          )}
                          title={`Chart ${ticker}`}
                        >
                          {ticker}
                        </Button>
                      </WorkspaceTableCell>
                    ) : (
                      <WorkspaceTableCell key={col} className={cn("px-1 py-0.5 text-ink", readable && "whitespace-nowrap px-2 py-1.5", readable && isNumericColumn(col) && "text-right font-mono tabular-nums")}>
                        {formatCell ? formatCell(col, row[col], row) : String(row[col] ?? "")}
                      </WorkspaceTableCell>
                    ),
                  )}
                </WorkspaceTableRow>
              );
            })}
            {!loading && !rows.length && (
              <WorkspaceTableRow>
                <WorkspaceTableCell
                  colSpan={Math.max(columns.length, 1)}
                  className="px-1 py-2 text-ink-faint"
                >
                  {emptyLabel}
                </WorkspaceTableCell>
              </WorkspaceTableRow>
            )}
          </WorkspaceTableBody>
        </WorkspaceTable>
      </div>
      {hint ? (
        <p className="font-mono text-[10px] text-ink-faint">{hint}</p>
      ) : null}
    </div>
  );
}
