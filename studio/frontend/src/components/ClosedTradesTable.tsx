import { useMemo, useState } from "react";
import type { ClosedTradeItem } from "../types";

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
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-line/80 bg-surface-sunk p-0.5 text-[11px]">
            <button
              type="button"
              onClick={() => setActiveTab("closed")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-all ${
                activeTab === "closed"
                  ? "bg-surface font-semibold text-ink shadow-sm"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              <span>Closed Trades</span>
              <span className="rounded-full bg-surface-sunk px-1.5 py-0.2 font-mono text-[10px] text-ink-faint">
                {total ?? trades.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("open")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-all ${
                activeTab === "open"
                  ? "bg-surface font-semibold text-ink shadow-sm"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
              </span>
              <span>Open Trades</span>
              <span className="rounded-full bg-surface-sunk px-1.5 py-0.2 font-mono text-[10px] text-ink-faint">
                {openTotal ?? openTrades.length}
              </span>
            </button>
          </div>

          {/* Subfilters */}
          {activeTab === "closed" ? (
            <div className="flex gap-1 rounded bg-surface-sunk p-0.5 text-[10px]">
              <button
                type="button"
                onClick={() => setClosedFilterMode("all")}
                className={`rounded px-2 py-0.5 font-medium transition-colors ${
                  closedFilterMode === "all"
                    ? "bg-surface font-semibold text-ink shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                All ({trades.length})
              </button>
              <button
                type="button"
                onClick={() => setClosedFilterMode("wins")}
                className={`rounded px-2 py-0.5 font-medium transition-colors ${
                  closedFilterMode === "wins"
                    ? "bg-emerald-500/20 font-semibold text-emerald-400 shadow-sm"
                    : "text-ink-muted hover:text-emerald-400"
                }`}
              >
                Wins ({winCount})
              </button>
              <button
                type="button"
                onClick={() => setClosedFilterMode("losses")}
                className={`rounded px-2 py-0.5 font-medium transition-colors ${
                  closedFilterMode === "losses"
                    ? "bg-rose-500/20 font-semibold text-rose-400 shadow-sm"
                    : "text-ink-muted hover:text-rose-400"
                }`}
              >
                Losses ({lossCount})
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex gap-1 rounded bg-surface-sunk p-0.5 text-[10px]">
                <button
                  type="button"
                  onClick={() => setOpenFilterMode("all")}
                  className={`rounded px-2 py-0.5 font-medium transition-colors ${
                    openFilterMode === "all"
                      ? "bg-surface font-semibold text-ink shadow-sm"
                      : "text-ink-muted hover:text-ink"
                  }`}
                >
                  All Open ({openTrades.length})
                </button>
                <button
                  type="button"
                  onClick={() => setOpenFilterMode("gains")}
                  className={`rounded px-2 py-0.5 font-medium transition-colors ${
                    openFilterMode === "gains"
                      ? "bg-emerald-500/20 font-semibold text-emerald-400 shadow-sm"
                      : "text-ink-muted hover:text-emerald-400"
                  }`}
                >
                  In Profit ({openGainCount})
                </button>
                <button
                  type="button"
                  onClick={() => setOpenFilterMode("drawdowns")}
                  className={`rounded px-2 py-0.5 font-medium transition-colors ${
                    openFilterMode === "drawdowns"
                      ? "bg-rose-500/20 font-semibold text-rose-400 shadow-sm"
                      : "text-ink-muted hover:text-rose-400"
                  }`}
                >
                  In Drawdown ({openLossCount})
                </button>
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
        <input
          type="search"
          placeholder="Filter ticker (e.g. SOLS, MU)…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border border-line bg-surface px-2 py-1 text-[11px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
        />
      </div>

      {/* Trades Table */}
      <div className="mt-2 max-h-72 overflow-auto rounded border border-line bg-surface">
        <table className="w-full text-left text-[11px]">
          <thead className="sticky top-0 z-10 border-b border-line bg-surface-sunk text-ink-faint">
            <tr>
              <th
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("time")}
              >
                {activeTab === "closed" ? "Exit Date" : "Entry Date"}{" "}
                {sortKey === "time" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("symbol")}
              >
                Symbol {sortKey === "symbol" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th className="px-2 py-1.5">Side</th>
              <th className="px-2 py-1.5">Qty</th>
              <th className="px-2 py-1.5">Entry Px</th>
              <th className="px-2 py-1.5">
                {activeTab === "closed" ? "Exit Px" : "Mark Px"}
              </th>
              <th
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("profit_loss")}
              >
                {activeTab === "closed" ? "PnL ($)" : "Unrealized ($)"}{" "}
                {sortKey === "profit_loss" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2 py-1.5 hover:text-ink"
                onClick={() => handleSort("return_pct")}
              >
                Return % {sortKey === "return_pct" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              {activeTab === "closed" ? (
                <>
                  <th className="px-2 py-1.5 text-right">MAE</th>
                  <th className="px-2 py-1.5 text-right">MFE</th>
                </>
              ) : null}
              <th
                className="cursor-pointer px-2 py-1.5 text-right hover:text-ink"
                onClick={() => handleSort("duration")}
              >
                {activeTab === "closed" ? "Duration" : "Status"}{" "}
                {sortKey === "duration" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th className="px-2 py-1.5 text-center">Chart</th>
            </tr>
          </thead>
          <tbody>
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
                <tr
                  key={t.id || idx}
                  onClick={() => onSelectTrade?.(t)}
                  className="border-t border-line/60 transition-colors hover:bg-surface-sunk/50 cursor-pointer"
                >
                  <td className="px-2 py-1 font-mono text-[10px] text-ink-muted">
                    {displayDate}
                  </td>
                  <td className="px-2 py-1 font-mono font-bold text-ink">
                    {t.symbol}
                  </td>
                  <td className="px-2 py-1">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${
                        isLong
                          ? "bg-sky-500/15 text-sky-400 border border-sky-500/30"
                          : "bg-purple-500/15 text-purple-400 border border-purple-500/30"
                      }`}
                    >
                      {isLong ? "LONG" : "SHORT"}
                    </span>
                  </td>
                  <td className="px-2 py-1 tabular-nums text-ink-muted">
                    {t.quantity.toLocaleString()}
                  </td>
                  <td className="px-2 py-1 tabular-nums text-ink">
                    ${t.entry_price.toFixed(2)}
                  </td>
                  <td className="px-2 py-1 tabular-nums text-ink">
                    ${targetPx.toFixed(2)}
                  </td>
                  <td
                    className={`px-2 py-1 font-mono font-semibold tabular-nums ${
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isProfit ? "+" : ""}${t.profit_loss.toFixed(2)}
                  </td>
                  <td
                    className={`px-2 py-1 font-mono font-medium tabular-nums ${
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isProfit ? "+" : ""}{retPct}%
                  </td>
                  {activeTab === "closed" ? (
                    <>
                      <td className="px-2 py-1 text-right font-mono text-[10px] tabular-nums text-rose-400/80">
                        {t.mae != null ? `-$${Math.abs(t.mae).toFixed(1)}` : "—"}
                      </td>
                      <td className="px-2 py-1 text-right font-mono text-[10px] tabular-nums text-emerald-400/80">
                        {t.mfe != null ? `+$${t.mfe.toFixed(1)}` : "—"}
                      </td>
                    </>
                  ) : null}
                  <td className="px-2 py-1 text-right font-mono text-[10px]">
                    {activeTab === "closed" ? (
                      <span className="text-ink-faint">
                        {t.duration ? `${t.duration.split(".")[0]}d` : "—"}
                      </span>
                    ) : (
                      <span className="inline-block rounded border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">
                        ACTIVE OPEN
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1 text-center">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectTrade?.(t);
                      }}
                      className="rounded bg-surface-sunk px-1.5 py-0.5 text-[10px] font-medium text-ink hover:bg-accent/20 hover:text-accent-ink transition-colors"
                      title="View trade candlestick chart"
                    >
                      📊 View
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
