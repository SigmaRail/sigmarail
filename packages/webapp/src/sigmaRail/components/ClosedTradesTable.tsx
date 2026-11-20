import { useMemo, useState } from "react";
import type { ClosedTradeItem } from "../types";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

type ViewTab = "closed" | "open";
type SortKey = "time" | "symbol" | "profit_loss" | "return_pct" | "duration";
type ClosedFilterMode = "all" | "wins" | "losses";
type OpenFilterMode = "all" | "gains" | "drawdowns";

export function ClosedTradesTable({
  trades,
  openTrades = [],
  total,
  openTotal,
  isLoading,
  onSelectTrade,
}: {
  trades: ClosedTradeItem[];
  openTrades?: ClosedTradeItem[];
  total?: number;
  openTotal?: number;
  isLoading?: boolean;
  onSelectTrade?: (trade: ClosedTradeItem) => void;
}) {
  const [activeTab, setActiveTab] = useState<ViewTab>("closed");
  const [search, setSearch] = useState("");
  const [closedFilterMode, setClosedFilterMode] = useState<ClosedFilterMode>("all");
  const [openFilterMode, setOpenFilterMode] = useState<OpenFilterMode>("all");
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [sortDesc, setSortDesc] = useState(true);

  // Closed metrics
  const winCount = useMemo(() => trades.filter((t) => t.is_win).length, [trades]);
  const lossCount = useMemo(() => trades.filter((t) => !t.is_win).length, [trades]);

  // Open metrics
  const openGainCount = useMemo(() => openTrades.filter((t) => t.profit_loss >= 0).length, [openTrades]);
  const openLossCount = useMemo(() => openTrades.filter((t) => t.profit_loss < 0).length, [openTrades]);
  const totalOpenPnL = useMemo(
    () => openTrades.reduce((acc, t) => acc + (t.profit_loss || 0), 0),
    [openTrades]
  );

  const currentList = activeTab === "closed" ? trades : openTrades;

  const filtered = useMemo(() => {
    let list = [...currentList];
    if (search.trim()) {
      const q = search.trim().toUpperCase();
      list = list.filter((t) => t.symbol.toUpperCase().includes(q));
    }

    if (activeTab === "closed") {
      if (closedFilterMode === "wins") {
        list = list.filter((t) => t.is_win);
      } else if (closedFilterMode === "losses") {
        list = list.filter((t) => !t.is_win);
      }
    } else {
      if (openFilterMode === "gains") {
        list = list.filter((t) => t.profit_loss >= 0);
      } else if (openFilterMode === "drawdowns") {
        list = list.filter((t) => t.profit_loss < 0);
      }
    }

    list.sort((a, b) => {
      let vA: any = a[sortKey as keyof ClosedTradeItem];
      let vB: any = b[sortKey as keyof ClosedTradeItem];
      if (sortKey === "time") {
        const tA = activeTab === "closed" ? (a.exit_time || a.entry_time) : a.entry_time;
        const tB = activeTab === "closed" ? (b.exit_time || b.entry_time) : b.entry_time;
        vA = new Date(tA || 0).getTime() || 0;
        vB = new Date(tB || 0).getTime() || 0;
      }
      if (vA < vB) return sortDesc ? 1 : -1;
      if (vA > vB) return sortDesc ? -1 : 1;
      return 0;
    });

    return list;
  }, [currentList, search, activeTab, closedFilterMode, openFilterMode, sortKey, sortDesc]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  if (isLoading) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
        Loading trade log…
      </div>
    );
  }

  if (trades.length === 0 && openTrades.length === 0) {
    return null;
  }

  return (
    <section className="mb-4">
      {/* Top Header: Primary Tabs (Closed vs Open) + Subfilters + Search */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 pb-2">
        {/* Left: View Tabs */}
          <div className="flex flex-wrap items-center gap-2">
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as ViewTab)}>
            <TabsList className="h-9">
            <TabsTrigger value="closed" className="gap-1.5 px-3 text-xs">
              <span>Closed Trades</span>
              <span className="rounded-full bg-surface-sunk px-1.5 py-0.2 font-mono text-[10px] text-ink-faint">
                {total ?? trades.length}
              </span>
            </TabsTrigger>

            <TabsTrigger value="open" className="gap-1.5 px-3 text-xs">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
              </span>
              <span>Open Trades</span>
              <span className="rounded-full bg-surface-sunk px-1.5 py-0.2 font-mono text-[10px] text-ink-faint">
                {openTotal ?? openTrades.length}
              </span>
            </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Subfilters */}
          {activeTab === "closed" ? (
            <div className="flex gap-1 rounded bg-surface-sunk p-0.5 text-[10px]">
              <Button
                type="button"
                onClick={() => setClosedFilterMode("all")}
                variant={closedFilterMode === "all" ? "secondary" : "ghost"}
                size="sm"
                className="h-8 px-2 text-xs"
              >
                All ({trades.length})
              </Button>
              <Button
                type="button"
                onClick={() => setClosedFilterMode("wins")}
                variant={closedFilterMode === "wins" ? "secondary" : "ghost"}
                size="sm"
                className="h-8 px-2 text-xs text-emerald-500"
              >
                Wins ({winCount})
              </Button>
              <Button
                type="button"
                onClick={() => setClosedFilterMode("losses")}
                variant={closedFilterMode === "losses" ? "secondary" : "ghost"}
                size="sm"
                className="h-8 px-2 text-xs text-rose-500"
              >
                Losses ({lossCount})
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex gap-1 rounded bg-surface-sunk p-0.5 text-[10px]">
                <Button
                  type="button"
                  onClick={() => setOpenFilterMode("all")}
                  variant={openFilterMode === "all" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-8 px-2 text-xs"
                >
                  All Open ({openTrades.length})
                </Button>
                <Button
                  type="button"
                  onClick={() => setOpenFilterMode("gains")}
                  variant={openFilterMode === "gains" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-8 px-2 text-xs text-emerald-500"
                >
                  In Profit ({openGainCount})
                </Button>
                <Button
                  type="button"
                  onClick={() => setOpenFilterMode("drawdowns")}
                  variant={openFilterMode === "drawdowns" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-8 px-2 text-xs text-rose-500"
                >
                  In Drawdown ({openLossCount})
                </Button>
              </div>

              <div className="rounded border border-line bg-surface px-2 py-0.5 text-[10.5px]">
                <span className="text-ink-muted">Unrealized PnL: </span>
                <span className={`font-mono font-bold ${totalOpenPnL >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {totalOpenPnL >= 0 ? "+" : ""}${totalOpenPnL.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right: Search Filter */}
        <Input
          type="search"
          placeholder="Filter ticker (e.g. SOLS, MU)…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Filter trades by ticker"
          className="h-9 w-full text-xs sm:w-64"
        />
      </div>

      {/* Trades Table */}
      <div className="mt-2 space-y-2 md:hidden">
        <div className="flex items-center gap-2">
          <Select value={sortKey} onValueChange={(value) => setSortKey(value as SortKey)}>
            <SelectTrigger aria-label="Sort trades by" className="min-w-0 flex-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="time">Date</SelectItem>
              <SelectItem value="symbol">Symbol</SelectItem>
              <SelectItem value="profit_loss">Profit / loss</SelectItem>
              <SelectItem value="return_pct">Return</SelectItem>
              <SelectItem value="duration">Duration</SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSortDesc((descending) => !descending)}
            aria-label="Reverse sort order"
          >
            {sortDesc ? "Descending" : "Ascending"}
          </Button>
        </div>
        {filtered.map((trade, index) => {
          const displayDate = activeTab === "closed"
            ? trade.exit_time?.slice(0, 10) || "—"
            : trade.entry_time?.slice(0, 10) || "—";
          const isProfit = trade.profit_loss >= 0;
          const isLong = trade.direction.toLowerCase() === "buy" || trade.direction.toLowerCase() === "long";
          const targetPx = activeTab === "closed"
            ? trade.exit_price ?? 0
            : trade.current_price ?? trade.exit_price ?? trade.entry_price;
          const side = isLong ? "LONG" : "SHORT";
          return (
            <Card key={trade.id || index} data-testid={`trade-card-${trade.id || index}`} className="space-y-3 p-3 shadow-none">
              <div className="flex min-w-0 items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-mono text-sm font-semibold text-ink">{trade.symbol}</div>
                  <div className="text-xs text-muted-foreground">{displayDate}</div>
                </div>
                <Badge variant={isLong ? "info" : "secondary"} className="shrink-0">{side}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                <span className="text-muted-foreground">{activeTab === "closed" ? "Exit price" : "Mark price"}</span>
                <span className="text-right tabular-nums">${targetPx.toFixed(2)}</span>
                <span className="text-muted-foreground">Quantity</span>
                <span className="text-right tabular-nums">{trade.quantity.toLocaleString()}</span>
                <span className="text-muted-foreground">P/L</span>
                <span className={`text-right font-semibold tabular-nums ${isProfit ? "text-emerald-500" : "text-rose-500"}`}>
                  {isProfit ? "+" : ""}${trade.profit_loss.toFixed(2)}
                </span>
                <span className="text-muted-foreground">Return</span>
                <span className={`text-right tabular-nums ${isProfit ? "text-emerald-500" : "text-rose-500"}`}>
                  {isProfit ? "+" : ""}{(trade.return_pct * 100).toFixed(2)}%
                </span>
                {activeTab === "closed" ? (
                  <>
                    <span className="text-muted-foreground">MAE / MFE</span>
                    <span className="text-right tabular-nums">{trade.mae != null ? `-$${Math.abs(trade.mae).toFixed(1)}` : "—"} / {trade.mfe != null ? `+$${trade.mfe.toFixed(1)}` : "—"}</span>
                  </>
                ) : (
                  <>
                    <span className="text-muted-foreground">Status</span>
                    <span className="text-right">Active</span>
                  </>
                )}
              </div>
              <Button type="button" variant="outline" size="sm" onClick={() => onSelectTrade?.(trade)}>
                View chart
              </Button>
            </Card>
          );
        })}
        {filtered.length === 0 ? (
          <Card className="p-4 text-center text-sm text-muted-foreground shadow-none">No trades match this filter.</Card>
        ) : null}
      </div>

      <div className="mt-2 hidden rounded border border-line bg-surface md:block">
        <WorkspaceTable containerClassName="max-h-72" className="min-w-[720px] text-left text-[11px]">
          <WorkspaceTableHeader className="sticky top-0 z-10 border-b border-line bg-surface-sunk text-ink-faint">
            <WorkspaceTableRow>
              <WorkspaceTableHead
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("time")}
              >
                {activeTab === "closed" ? "Exit Date" : "Entry Date"}{" "}
                {sortKey === "time" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("symbol")}
              >
                Symbol {sortKey === "symbol" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5">Side</WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5">Qty</WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5">Entry Px</WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5">
                {activeTab === "closed" ? "Exit Px" : "Mark Px"}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("profit_loss")}
              >
                {activeTab === "closed" ? "PnL ($)" : "Unrealized ($)"}{" "}
                {sortKey === "profit_loss" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("return_pct")}
              >
                Return % {sortKey === "return_pct" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              {activeTab === "closed" ? (
                <>
                  <WorkspaceTableHead className="px-2 py-1.5 text-right">MAE</WorkspaceTableHead>
                  <WorkspaceTableHead className="px-2 py-1.5 text-right">MFE</WorkspaceTableHead>
                </>
              ) : null}
              <WorkspaceTableHead
                className="cursor-pointer px-2 py-1.5 text-right hover:text-ink"
                onClick={() => handleSort("duration")}
              >
                {activeTab === "closed" ? "Duration" : "Status"}{" "}
                {sortKey === "duration" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5 text-center">Chart</WorkspaceTableHead>
            </WorkspaceTableRow>
          </WorkspaceTableHeader>
          <WorkspaceTableBody>
            {filtered.map((t, idx) => {
              const displayDate =
                activeTab === "closed"
                  ? t.exit_time ? t.exit_time.slice(0, 10) : "—"
                  : t.entry_time ? t.entry_time.slice(0, 10) : "—";
              const isProfit = t.profit_loss >= 0;
              const retPct = (t.return_pct * 100).toFixed(2);
              const isLong =
                t.direction.toLowerCase() === "buy" ||
                t.direction.toLowerCase() === "long";
              const targetPx =
                activeTab === "closed"
                  ? t.exit_price ?? 0
                  : t.current_price ?? t.exit_price ?? t.entry_price;

              return (
                <WorkspaceTableRow
                  key={t.id || idx}
                  onClick={() => onSelectTrade?.(t)}
                  className="border-t border-line/60 transition-colors hover:bg-surface-sunk/50 cursor-pointer"
                >
                  <WorkspaceTableCell className="px-2 py-1 font-mono text-[10px] text-ink-muted">
                    {displayDate}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1 font-mono font-bold text-ink">
                    {t.symbol}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${
                        isLong
                          ? "bg-sky-500/15 text-sky-400 border border-sky-500/30"
                          : "bg-purple-500/15 text-purple-400 border border-purple-500/30"
                      }`}
                    >
                      {isLong ? "LONG" : "SHORT"}
                    </span>
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1 tabular-nums text-ink-muted">
                    {t.quantity.toLocaleString()}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1 tabular-nums text-ink">
                    ${t.entry_price.toFixed(2)}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1 tabular-nums text-ink">
                    ${targetPx.toFixed(2)}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell
                    className={`px-2 py-1 font-mono font-semibold tabular-nums ${
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isProfit ? "+" : ""}${t.profit_loss.toFixed(2)}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell
                    className={`px-2 py-1 font-mono font-medium tabular-nums ${
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isProfit ? "+" : ""}{retPct}%
                  </WorkspaceTableCell>
                  {activeTab === "closed" ? (
                    <>
                      <WorkspaceTableCell className="px-2 py-1 text-right font-mono text-[10px] tabular-nums text-rose-400/80">
                        {t.mae != null ? `-$${Math.abs(t.mae).toFixed(1)}` : "—"}
                      </WorkspaceTableCell>
                      <WorkspaceTableCell className="px-2 py-1 text-right font-mono text-[10px] tabular-nums text-emerald-400/80">
                        {t.mfe != null ? `+$${t.mfe.toFixed(1)}` : "—"}
                      </WorkspaceTableCell>
                    </>
                  ) : null}
                  <WorkspaceTableCell className="px-2 py-1 text-right font-mono text-[10px]">
                    {activeTab === "closed" ? (
                      <span className="text-ink-faint">
                        {t.duration ? `${t.duration.split(".")[0]}d` : "—"}
                      </span>
                    ) : (
                      <span className="inline-block rounded border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">
                        ACTIVE OPEN
                      </span>
                    )}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1 text-center">
                    <Button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectTrade?.(t);
                      }}
                      variant="outline"
                      size="sm"
                      className="h-8 whitespace-nowrap px-2 text-xs"
                      title="View trade candlestick chart"
                    >
                      📊 View
                    </Button>
                  </WorkspaceTableCell>
                </WorkspaceTableRow>
              );
            })}
          </WorkspaceTableBody>
        </WorkspaceTable>
      </div>
    </section>
  );
}
