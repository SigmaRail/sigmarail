import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { fetchRunOrders, fetchTickerCandles } from "../api/backtests";
import {
  CAMPAIGN_FILL_COLORS,
  campaignFillsForSymbol,
  campaignHoldingSignRuns,
  campaignMarkSeries,
  campaignPerformance,
  campaignShareTotals,
} from "../lib/campaignFills";
import type { ClosedTradeItem } from "../types";
import { CopyIdBadge } from "./CopyIdBadge";

function formatCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  const prefix = val < 0 ? "-$" : "$";
  return `${prefix}${Math.abs(val).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `${(val * 100).toFixed(2)}%`;
}

function addDays(isoDate: string, days: number): string {
  try {
    const d = new Date(isoDate);
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  } catch {
    return isoDate;
  }
}

function candleIndexOnOrAfter(
  candles: Array<{ date: string }>,
  date: string,
): number {
  const exact = candles.findIndex((c) => c.date === date);
  if (exact >= 0) return exact;
  return candles.findIndex((c) => c.date >= date);
}

function candleIndexOnOrBefore(
  candles: Array<{ date: string }>,
  date: string,
): number {
  for (let i = candles.length - 1; i >= 0; i--) {
    if (candles[i]!.date <= date) return i;
  }
  return -1;
}

export function TradeCandlestickModal({
  trade,
  runId,
  onClose,
}: {
  trade: ClosedTradeItem;
  runId?: string | null;
  onClose: () => void;
}) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const isOpen = trade.status === "OPEN" || !trade.exit_time;
  const entryDate = trade.entry_time.slice(0, 10);
  const exitDate = trade.exit_time ? trade.exit_time.slice(0, 10) : addDays(entryDate, 20);
  const currentOrExitPrice = trade.current_price ?? trade.exit_price ?? trade.entry_price;

  const ordersQuery = useQuery({
    queryKey: ["backtest-orders", runId, "campaign"],
    queryFn: () => fetchRunOrders(runId!, 2000),
    enabled: Boolean(runId),
  });
  const fills = useMemo(
    () => campaignFillsForSymbol(ordersQuery.data?.orders ?? [], trade.symbol),
    [ordersQuery.data?.orders, trade.symbol],
  );
  const shareTotals = useMemo(() => campaignShareTotals(fills), [fills]);

  const fillDates = fills.map((f) => f.date);
  const campaignStart = fillDates[0] && fillDates[0] < entryDate ? fillDates[0] : entryDate;
  const campaignEnd =
    fillDates.length > 0
      ? fillDates.reduce((a, b) => (a > b ? a : b), fillDates[0]!)
      : exitDate;
  const latestBound = campaignEnd > exitDate ? campaignEnd : exitDate;
  const startWindow = addDays(campaignStart, -25);
  const endWindow = addDays(latestBound, 15);

  const candlesQuery = useQuery({
    queryKey: ["candles", trade.symbol, startWindow, endWindow],
    queryFn: () => fetchTickerCandles(trade.symbol, startWindow, endWindow),
  });

  const candles = candlesQuery.data?.candles ?? [];
  const meta = candlesQuery.data?.meta;
  const markPrice =
    candles.length > 0
      ? candles[candles.length - 1]!.close
      : (trade.current_price ?? trade.exit_price ?? null);
  const campaign = useMemo(
    () => campaignPerformance(fills, markPrice),
    [fills, markPrice],
  );
  const markSeries = useMemo(
    () => campaignMarkSeries(fills, candles),
    [fills, candles],
  );
  const holdingRuns = useMemo(
    () => campaignHoldingSignRuns(markSeries),
    [markSeries],
  );
  const markByDate = useMemo(() => {
    const m = new Map<string, (typeof markSeries)[number]>();
    for (const row of markSeries) m.set(row.date, row);
    return m;
  }, [markSeries]);

  // Chart layout calculations
  const chartMetrics = useMemo(() => {
    if (candles.length === 0) return null;

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVolume = 0;

    for (const c of candles) {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (c.volume > maxVolume) maxVolume = c.volume;
    }

    // Include trade execution prices and campaign fills in vertical scale
    minPrice = Math.min(minPrice, trade.entry_price, currentOrExitPrice);
    maxPrice = Math.max(maxPrice, trade.entry_price, currentOrExitPrice);
    for (const fill of fills) {
      if (fill.price > 0) {
        minPrice = Math.min(minPrice, fill.price);
        maxPrice = Math.max(maxPrice, fill.price);
      }
    }

    const pricePadding = (maxPrice - minPrice) * 0.08 || 1.0;
    minPrice -= pricePadding;
    maxPrice += pricePadding;

    const width = 760;
    const priceHeight = 280;
    const volumeHeight = 60;
    const padding = { top: 20, right: 60, bottom: 25, left: 10 };

    const chartWidth = width - padding.left - padding.right;
    const slotWidth = chartWidth / candles.length;
    const candleWidth = Math.max(3, Math.min(14, slotWidth * 0.7));

    const scaleY = (p: number) =>
      padding.top +
      priceHeight -
      ((p - minPrice) / (maxPrice - minPrice)) * priceHeight;

    const scaleVol = (v: number) =>
      maxVolume > 0 ? (v / maxVolume) * volumeHeight : 0;

    const entryIdx = candles.findIndex((c) => c.date >= entryDate);
    let exitIdx = -1;
    for (let i = candles.length - 1; i >= 0; i--) {
      if (candles[i].date <= exitDate) {
        exitIdx = i;
        break;
      }
    }

    let campaignStartIdx: number | null = null;
    let campaignEndIdx: number | null = null;
    if (fills.length > 0) {
      const first = fills[0]!.date;
      const last = fills[fills.length - 1]!.date;
      const start = candles.findIndex((c) => c.date >= first);
      campaignStartIdx = start >= 0 ? start : null;
      let end = -1;
      for (let i = candles.length - 1; i >= 0; i--) {
        if (candles[i].date <= last) {
          end = i;
          break;
        }
      }
      const remaining = fills[fills.length - 1]!.openAfter;
      campaignEndIdx = remaining > 0 ? candles.length - 1 : end >= 0 ? end : null;
    }

    return {
      width,
      height: priceHeight + volumeHeight + padding.top + padding.bottom + 20,
      priceHeight,
      volumeHeight,
      padding,
      minPrice,
      maxPrice,
      maxVolume,
      slotWidth,
      candleWidth,
      scaleY,
      scaleVol,
      entryIdx: entryIdx >= 0 ? entryIdx : null,
      exitIdx: exitIdx >= 0 ? exitIdx : null,
      campaignStartIdx,
      campaignEndIdx,
    };
  }, [candles, trade, entryDate, exitDate, currentOrExitPrice, fills]);

  const activeCandle =
    hoverIndex != null && candles[hoverIndex]
      ? candles[hoverIndex]
      : candles[candles.length - 1] ?? null;
  const hoverMark = activeCandle ? markByDate.get(activeCandle.date) : undefined;

  const isLong =
    trade.direction.toLowerCase() === "buy" ||
    trade.direction.toLowerCase() === "long";
  const isShort = !isLong;
  const isWin = trade.is_win;

  const [copiedLink, setCopiedLink] = useState(false);

  const hoverGainLoss = useMemo(() => {
    if (!activeCandle) return null;
    if (hoverMark) {
      const isClosed = hoverMark.remaining === 0;
      const dollars = hoverMark.totalPnl;
      const pct = hoverMark.returnPct;
      return {
        dollars,
        pct,
        shares: hoverMark.remaining,
        avgCost: hoverMark.avgEntry,
        isClosed,
        isCampaign: true,
      };
    }
    const barDate = activeCandle.date;
    const isPreEntry = barDate < entryDate;
    const isPostExit = exitDate ? barDate > exitDate : false;

    if (!isPreEntry && !isPostExit) {
      const diff = (activeCandle.close - trade.entry_price) * (isLong ? 1 : -1);
      const dollars = diff * trade.quantity;
      const pct = trade.entry_price > 0 ? (diff / trade.entry_price) * 100 : 0;
      return {
        dollars,
        pct,
        shares: trade.quantity,
        avgCost: trade.entry_price,
        isClosed: false,
        isCampaign: false,
      };
    }
    if (isPostExit) {
      return {
        dollars: trade.profit_loss,
        pct: trade.return_pct * 100,
        shares: 0,
        avgCost: trade.entry_price,
        isClosed: true,
        isCampaign: false,
      };
    }
    return null;
  }, [activeCandle, hoverMark, entryDate, exitDate, trade, isLong]);

  const handleShareLink = async () => {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("trade", trade.id);
      url.searchParams.set("campaign", trade.symbol);
      await navigator.clipboard.writeText(url.toString());
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    } catch {
      // Fallback if clipboard API restricted
      const textarea = document.createElement("textarea");
      const url = new URL(window.location.href);
      url.searchParams.set("trade", trade.id);
      url.searchParams.set("campaign", trade.symbol);
      textarea.value = url.toString();
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col rounded-lg border border-line bg-surface shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-raised px-5 py-3.5">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h2 className="font-mono text-lg font-bold text-ink">
                {trade.symbol}
              </h2>
              <span
                className={`rounded px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${
                  isLong
                    ? "bg-sky-500/20 text-sky-400 border border-sky-500/30"
                    : "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                }`}
              >
                {isLong ? "LONG" : "SHORT"}
              </span>
              {campaign ? (
                <span className="rounded border border-line bg-surface-sunk px-2 py-0.5 font-mono text-[11px] font-bold text-ink-muted">
                  CAMPAIGN
                </span>
              ) : null}
              {campaign && campaign.remaining > 0 ? (
                <span className="rounded border border-cyan-500/30 bg-cyan-500/20 px-2 py-0.5 font-mono text-[11px] font-bold text-cyan-300">
                  RUNNER {campaign.remaining.toLocaleString()} sh
                </span>
              ) : campaign ? (
                <span
                  className={`rounded px-2 py-0.5 font-mono text-[11px] font-bold ${
                    campaign.totalPnl >= 0
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-rose-500/20 text-rose-400"
                  }`}
                >
                  {campaign.totalPnl >= 0 ? "CAMPAIGN WIN" : "CAMPAIGN LOSS"}
                </span>
              ) : isOpen ? (
                <span className="rounded border border-cyan-500/30 bg-cyan-500/20 px-2 py-0.5 font-mono text-[11px] font-bold text-cyan-300 animate-pulse">
                  OPEN
                </span>
              ) : (
                <span
                  className={`rounded px-2 py-0.5 font-mono text-[11px] font-bold ${
                    trade.is_win
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-rose-500/20 text-rose-400"
                  }`}
                >
                  {trade.is_win ? "WIN" : "LOSS"}
                </span>
              )}
              {trade.id ? (
                <CopyIdBadge
                  id={trade.id}
                  label="Trade"
                  head={6}
                  tail={4}
                  sqlQuery={`SELECT * FROM strategy_run_artifacts WHERE artifact_json LIKE '%${trade.id}%'`}
                />
              ) : null}
            </div>
            {meta?.name ? (
              <p className="mt-0.5 truncate text-[11.5px] text-ink-muted">
                {meta.name} · {meta.category === "ETF" ? "ETF / Index Proxy" : (meta.sector || "Equity")} {meta.industry ? `(${meta.industry})` : ""}
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <span className="text-[10px] uppercase font-semibold text-ink-faint">
                {campaign ? "Campaign P&L" : isOpen ? "Unrealized PnL" : "Trade PnL"}
              </span>
              <p
                className={`font-mono text-base font-bold ${
                  (campaign ? campaign.totalPnl : trade.profit_loss) >= 0
                    ? "text-accent"
                    : "text-danger"
                }`}
              >
                {formatCurrency(campaign ? campaign.totalPnl : trade.profit_loss)}
              </p>
              <span
                className={`font-mono text-[11px] font-semibold ${
                  (campaign ? campaign.returnPct : trade.return_pct) >= 0
                    ? "text-accent"
                    : "text-danger"
                }`}
              >
                {(campaign ? campaign.returnPct : trade.return_pct) >= 0 ? "+" : ""}
                {formatPct(campaign ? campaign.returnPct : trade.return_pct)}
              </span>
              {campaign ? (
                <p className="mt-0.5 font-mono text-[9.5px] text-ink-muted">
                  Realized {formatCurrency(campaign.realizedPnl)}
                  {campaign.remaining > 0
                    ? ` · leftover ${formatCurrency(campaign.unrealizedPnl)}`
                    : ""}
                </p>
              ) : null}
            </div>

            <button
              type="button"
              onClick={handleShareLink}
              title="Copy deep-link to this trade and campaign"
              className="flex items-center gap-1.5 rounded border border-line bg-surface-sunk px-2.5 py-1 text-xs font-mono font-medium text-ink hover:bg-surface-raised transition-colors"
            >
              {copiedLink ? (
                <span className="text-emerald-400 font-bold">✓ Copied</span>
              ) : (
                <>
                  <span>🔗</span>
                  <span>Share</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={onClose}
              className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-sm font-medium text-ink hover:bg-surface-raised transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Campaign / lot details */}
        <div className="grid grid-cols-2 gap-2 border-b border-line/60 bg-surface-sunk/50 px-5 py-2.5 sm:grid-cols-6 text-[11px]">
          {campaign ? (
            <>
              <div>
                <span className="text-[10px] text-ink-faint">Avg cost</span>
                <p className="font-mono font-semibold text-ink">
                  ${campaign.avgEntry.toFixed(2)}
                </p>
                <span className="font-mono text-[9.5px] text-ink-muted">
                  {campaign.firstDate ?? "—"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-ink-faint">
                  {campaign.remaining > 0 ? "Mark (last bar)" : "Last sell"}
                </span>
                <p className="font-mono font-semibold text-ink">
                  ${(campaign.markPrice ?? campaign.cashOut / Math.max(campaign.sold, 1)).toFixed(2)}
                </p>
                <span className="font-mono text-[9.5px] text-ink-muted">
                  {campaign.remaining > 0 ? "runner still open" : campaign.lastFillDate}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-ink-faint">Shares</span>
                <p className="font-mono font-semibold text-ink">
                  {campaign.bought.toLocaleString()} in / {campaign.sold.toLocaleString()} out
                </p>
                <span className="font-mono text-[9.5px] text-ink-muted">
                  {campaign.remaining.toLocaleString()} left · ${campaign.cashIn.toLocaleString(undefined, { maximumFractionDigits: 0 })} in
                </span>
              </div>
              <div>
                <span className="text-[10px] text-ink-faint">Campaign window</span>
                <p className="font-mono font-semibold text-ink">
                  {campaign.firstDate ?? "—"} → {campaign.remaining > 0 ? "open" : campaign.lastFillDate}
                </p>
                <span className="text-[9.5px] text-ink-muted">all fills, not one FIFO lot</span>
              </div>
              <div>
                <span className="text-[10px] text-ink-faint">Realized</span>
                <p className={`font-mono font-semibold ${campaign.realizedPnl >= 0 ? "text-accent" : "text-danger"}`}>
                  {formatCurrency(campaign.realizedPnl)}
                </p>
                <span className="font-mono text-[9.5px] text-ink-muted">from sells vs avg cost</span>
              </div>
              <div>
                <span className="text-[10px] text-ink-faint">Leftover mark</span>
                <p className={`font-mono font-semibold ${campaign.unrealizedPnl >= 0 ? "text-accent" : "text-danger"}`}>
                  {campaign.remaining > 0 ? formatCurrency(campaign.unrealizedPnl) : "—"}
                </p>
                <span className="font-mono text-[9.5px] text-ink-muted">
                  {campaign.remaining > 0 ? "not a stop — test ended" : "flat"}
                </span>
              </div>
            </>
          ) : (
            <>
          <div>
            <span className="text-[10px] text-ink-faint">
              {isLong ? "Entry Level (Buy)" : "Entry Level (Short)"}
            </span>
            <p className="font-mono font-semibold text-ink">
              ${trade.entry_price.toFixed(2)}
            </p>
            <span className="font-mono text-[9.5px] text-ink-muted">
              {entryDate}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-ink-faint">
              {isOpen ? "Current Price (Mark)" : (isLong ? "Exit Level (Sell)" : "Exit Level (Cover)")}
            </span>
            <p className="font-mono font-semibold text-ink">
              ${(currentOrExitPrice ?? 0).toFixed(2)}
            </p>
            <span className="font-mono text-[9.5px] text-ink-muted">
              {isOpen ? "Active / Open" : exitDate}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-ink-faint">Position Size</span>
            <p className="font-mono font-semibold text-ink">
              {trade.quantity.toLocaleString()} shs
            </p>
            <span className="font-mono text-[9.5px] text-ink-muted">
              ${(trade.quantity * trade.entry_price).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-ink-faint">Holding Duration</span>
            <p className="font-mono font-semibold text-ink">
              {trade.duration ? `${trade.duration.split(".")[0]}d` : (isOpen ? "Open" : "—")}
            </p>
            <span className="text-[9.5px] text-ink-muted">trade window</span>
          </div>

          <div>
            <span className="text-[10px] text-ink-faint">Max Excursion (MAE)</span>
            <p className="font-mono font-semibold text-danger">
              -{trade.mae != null && trade.mae > 0 ? `$${trade.mae.toFixed(2)}` : "$0.00"}
            </p>
            <span className="font-mono text-[9.5px] text-danger/80">
              {trade.mae != null && trade.entry_price > 0
                ? `-${((trade.mae / trade.entry_price) * 100).toFixed(1)}%`
                : "—"}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-ink-faint">Max Potential (MFE)</span>
            <p className="font-mono font-semibold text-accent">
              +{trade.mfe != null && trade.mfe > 0 ? `$${trade.mfe.toFixed(2)}` : "$0.00"}
            </p>
            <span className="font-mono text-[9.5px] text-accent/80">
              {trade.mfe != null && trade.entry_price > 0
                ? `+${((trade.mfe / trade.entry_price) * 100).toFixed(1)}%`
                : "—"}
            </span>
          </div>
            </>
          )}
        </div>
        {campaign ? (
          <p className="border-b border-line/40 bg-surface px-5 py-1.5 font-mono text-[10px] text-ink-muted">
            Clicked table row is one LEAN FIFO lot: {formatCurrency(trade.profit_loss)} (
            {trade.return_pct >= 0 ? "+" : ""}
            {formatPct(trade.return_pct)}). Numbers above are the whole campaign.
          </p>
        ) : null}

        {/* Educational Callout for Short Trades */}
        {isShort ? (
          <div className="mx-5 mt-2.5 rounded border border-purple-500/30 bg-purple-500/10 px-3 py-1.5 text-[11px] text-purple-300">
            <span className="font-semibold">ℹ️ Short Position Mechanics:</span> Opened SHORT at ${trade.entry_price.toFixed(2)} and COVERED at ${(currentOrExitPrice ?? 0).toFixed(2)}. Price {trade.return_pct >= 0 ? "fell" : "rose"} by {(Math.abs(trade.return_pct) * 100).toFixed(2)}% during the holding window, resulting in a {trade.is_win ? "profit" : "loss"}.
          </div>
        ) : null}

        {/* Notice for Mock / Synthetic Price Divergence */}
        {candles.length > 0 && (trade.entry_price < Math.min(...candles.map(c => c.low)) * 0.85 || trade.entry_price > Math.max(...candles.map(c => c.high)) * 1.15) ? (
          <div className="mx-5 mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300">
            <span className="font-semibold">⚠️ Synthetic Test Record:</span> This trade record is from an earlier simulated/mock sweep with test prices (${trade.entry_price.toFixed(2)} → ${(currentOrExitPrice ?? 0).toFixed(2)}) that differ from the actual ClickHouse historical market candles (${Math.min(...candles.map(c => c.low)).toFixed(2)}–${Math.max(...candles.map(c => c.high)).toFixed(2)}). Real LEAN execution backtests execute against ClickHouse candle prices directly.
          </div>
        ) : null}

        {/* Candlestick Interactive Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {candlesQuery.isLoading ? (
            <div className="flex h-72 items-center justify-center text-[12px] text-ink-muted">
              Fetching daily OHLCV candles from ClickHouse <code className="font-mono ml-1">vera.sep</code>…
            </div>
          ) : candlesQuery.isError ? (
            <div className="flex h-72 items-center justify-center text-[12px] text-danger">
              {(candlesQuery.error as Error).message}
            </div>
          ) : !chartMetrics || candles.length === 0 ? (
            <div className="flex h-72 items-center justify-center text-[12px] text-ink-muted">
              No historical price candles found for ticker {trade.symbol} in this time window.
            </div>
          ) : (
            <div className="space-y-2">
              {/* Active Candle Hover Info Bar */}
              {activeCandle ? (
                <div className="flex flex-wrap items-center gap-4 font-mono text-[11px] text-ink-muted bg-surface-sunk/80 rounded px-3 py-1.5 border border-line/60">
                  <span className="text-ink font-semibold">{activeCandle.date}</span>
                  <span>O: <span className="text-ink">${activeCandle.open.toFixed(2)}</span></span>
                  <span>H: <span className="text-ink">${activeCandle.high.toFixed(2)}</span></span>
                  <span>L: <span className="text-ink">${activeCandle.low.toFixed(2)}</span></span>
                  <span>C: <span className="text-ink">${activeCandle.close.toFixed(2)}</span></span>
                  <span>Vol: <span className="text-ink">{activeCandle.volume.toLocaleString()}</span></span>
                  <span
                    className={
                      activeCandle.close >= activeCandle.open
                        ? "text-emerald-400 font-semibold"
                        : "text-rose-400 font-semibold"
                    }
                  >
                    {activeCandle.close >= activeCandle.open ? "+" : ""}
                    {(
                      ((activeCandle.close - activeCandle.open) /
                        activeCandle.open) *
                      100
                    ).toFixed(2)}
                    %
                  </span>
                  {hoverGainLoss != null ? (
                    <span
                      className={`inline-flex items-center gap-1.5 rounded px-2.5 py-0.5 font-bold ${
                        hoverGainLoss.dollars >= 0
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                          : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                      }`}
                    >
                      <span>{hoverGainLoss.dollars >= 0 ? "Gain:" : "Loss:"}</span>
                      <span>
                        {hoverGainLoss.dollars >= 0 ? "+" : ""}
                        {formatCurrency(hoverGainLoss.dollars)}
                      </span>
                      <span>
                        ({hoverGainLoss.pct >= 0 ? "+" : ""}
                        {hoverGainLoss.pct.toFixed(2)}%)
                      </span>
                      {hoverGainLoss.shares > 0 ? (
                        <span className="text-[10px] font-normal opacity-85">
                          · {hoverGainLoss.shares.toLocaleString()} sh @ $
                          {hoverGainLoss.avgCost.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-[10px] font-normal opacity-85">
                          · flat / closed
                        </span>
                      )}
                    </span>
                  ) : activeCandle ? (
                    <span className="text-ink-faint italic text-[10px]">
                      Pre-entry base setup candle
                    </span>
                  ) : null}
                  {fills
                    .filter((f) => f.date === activeCandle.date)
                    .map((f) => (
                      <span
                        key={`${f.kind}-${f.qty}-${f.price}`}
                        className="font-semibold"
                        style={{ color: CAMPAIGN_FILL_COLORS[f.kind] }}
                      >
                        {f.label} ${f.price.toFixed(2)}
                      </span>
                    ))}
                </div>
              ) : null}

              {/* SVG Candlestick Canvas */}
              <div className="relative overflow-x-auto rounded border border-line bg-surface-raised p-2">
                <svg
                  viewBox={`0 0 ${chartMetrics.width} ${chartMetrics.height}`}
                  className="w-full h-auto select-none"
                  onMouseLeave={() => setHoverIndex(null)}
                >
                  <defs>
                    <linearGradient id="holdingSpanPos" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.18" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.04" />
                    </linearGradient>
                    <linearGradient id="holdingSpanNeg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.18" />
                      <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.04" />
                    </linearGradient>
                  </defs>

                  {/* Horizontal Grid lines & Price Labels */}
                  {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
                    const price =
                      chartMetrics.minPrice +
                      (1 - ratio) *
                        (chartMetrics.maxPrice - chartMetrics.minPrice);
                    const y =
                      chartMetrics.padding.top + ratio * chartMetrics.priceHeight;
                    return (
                      <g key={ratio}>
                        <line
                          x1={chartMetrics.padding.left}
                          y1={y}
                          x2={chartMetrics.width - chartMetrics.padding.right}
                          y2={y}
                          stroke="currentColor"
                          className="text-line/40"
                          strokeDasharray="3 3"
                        />
                        <text
                          x={chartMetrics.width - chartMetrics.padding.right + 6}
                          y={y + 3.5}
                          className="font-mono text-[9px] fill-ink-faint"
                        >
                          ${price.toFixed(2)}
                        </text>
                      </g>
                    );
                  })}

                  {/* Holding Period Span Overlay — campaign MTM by bar, else FIFO lot */}
                  {holdingRuns.length > 0
                    ? holdingRuns.map((run) => {
                        const startIdx = candleIndexOnOrAfter(candles, run.startDate);
                        const endIdx = candleIndexOnOrBefore(candles, run.endDate);
                        if (startIdx < 0 || endIdx < 0) return null;
                        const x1 =
                          chartMetrics.padding.left + startIdx * chartMetrics.slotWidth;
                        const x2 =
                          chartMetrics.padding.left +
                          (endIdx + 1) * chartMetrics.slotWidth;
                        return (
                          <rect
                            key={`${run.startDate}-${run.endDate}-${run.positive ? "pos" : "neg"}`}
                            x={x1}
                            y={chartMetrics.padding.top}
                            width={Math.max(12, x2 - x1)}
                            height={chartMetrics.priceHeight}
                            fill={run.positive ? "url(#holdingSpanPos)" : "url(#holdingSpanNeg)"}
                            stroke={run.positive ? "#10b981" : "#f43f5e"}
                            strokeOpacity="0.35"
                            strokeDasharray="2 2"
                          />
                        );
                      })
                    : (() => {
                        const startIdx =
                          chartMetrics.campaignStartIdx ?? chartMetrics.entryIdx;
                        const endIdx =
                          chartMetrics.campaignEndIdx ?? chartMetrics.exitIdx;
                        if (startIdx == null || endIdx == null) return null;
                        const x1 =
                          chartMetrics.padding.left + startIdx * chartMetrics.slotWidth;
                        const x2 =
                          chartMetrics.padding.left +
                          (endIdx + 1) * chartMetrics.slotWidth;
                        const lotWin = trade.is_win;
                        return (
                          <rect
                            x={x1}
                            y={chartMetrics.padding.top}
                            width={Math.max(12, x2 - x1)}
                            height={chartMetrics.priceHeight}
                            fill={lotWin ? "url(#holdingSpanPos)" : "url(#holdingSpanNeg)"}
                            stroke={lotWin ? "#10b981" : "#f43f5e"}
                            strokeOpacity="0.35"
                            strokeDasharray="2 2"
                          />
                        );
                      })()}

                  {/* FIFO lot levels — hidden when campaign MTM is on the chart */}
                  {markSeries.length === 0 ? (
                    <>
                      <line
                        x1={chartMetrics.padding.left}
                        y1={chartMetrics.scaleY(trade.entry_price)}
                        x2={chartMetrics.width - chartMetrics.padding.right}
                        y2={chartMetrics.scaleY(trade.entry_price)}
                        stroke={isLong ? "#10b981" : "#a855f7"}
                        strokeWidth="1.5"
                        strokeDasharray="4 3"
                      />
                      <line
                        x1={chartMetrics.padding.left}
                        y1={chartMetrics.scaleY(currentOrExitPrice)}
                        x2={chartMetrics.width - chartMetrics.padding.right}
                        y2={chartMetrics.scaleY(currentOrExitPrice)}
                        stroke={isOpen ? "#06b6d4" : trade.is_win ? "#10b981" : "#f43f5e"}
                        strokeWidth="1.5"
                        strokeDasharray="4 3"
                      />
                    </>
                  ) : null}

                  {/* Volume Separator Line */}
                  <line
                    x1={chartMetrics.padding.left}
                    y1={chartMetrics.padding.top + chartMetrics.priceHeight + 15}
                    x2={chartMetrics.width - chartMetrics.padding.right}
                    y2={chartMetrics.padding.top + chartMetrics.priceHeight + 15}
                    stroke="currentColor"
                    className="text-line"
                  />

                  {/* Candlesticks and Volume Bars */}
                  {candles.map((c, i) => {
                    const isBull = c.close >= c.open;
                    const color = isBull ? "#10b981" : "#f43f5e";
                    const xCenter =
                      chartMetrics.padding.left +
                      i * chartMetrics.slotWidth +
                      chartMetrics.slotWidth / 2;
                    const xBox = xCenter - chartMetrics.candleWidth / 2;

                    const yHigh = chartMetrics.scaleY(c.high);
                    const yLow = chartMetrics.scaleY(c.low);
                    const yOpen = chartMetrics.scaleY(c.open);
                    const yClose = chartMetrics.scaleY(c.close);

                    const boxTop = Math.min(yOpen, yClose);
                    const boxHeight = Math.max(2, Math.abs(yClose - yOpen));

                    // Volume bar
                    const volBarHeight = chartMetrics.scaleVol(c.volume);
                    const volY =
                      chartMetrics.padding.top +
                      chartMetrics.priceHeight +
                      15 +
                      chartMetrics.volumeHeight -
                      volBarHeight;

                    const isHovered = hoverIndex === i;

                    return (
                      <g
                        key={c.date}
                        className="cursor-pointer"
                        onMouseEnter={() => setHoverIndex(i)}
                      >
                        {/* Hover vertical crosshair */}
                        {isHovered ? (
                          <line
                            x1={xCenter}
                            y1={chartMetrics.padding.top}
                            x2={xCenter}
                            y2={
                              chartMetrics.padding.top +
                              chartMetrics.priceHeight +
                              15 +
                              chartMetrics.volumeHeight
                            }
                            stroke="currentColor"
                            className="text-accent-ink/60"
                            strokeDasharray="2 2"
                          />
                        ) : null}

                        {/* High/Low Wick line */}
                        <line
                          x1={xCenter}
                          y1={yHigh}
                          x2={xCenter}
                          y2={yLow}
                          stroke={color}
                          strokeWidth="1.2"
                        />

                        {/* Candle Body Rect */}
                        <rect
                          x={xBox}
                          y={boxTop}
                          width={chartMetrics.candleWidth}
                          height={boxHeight}
                          fill={isBull ? "#10b981" : "#f43f5e"}
                          stroke={color}
                          strokeWidth="0.5"
                          rx="0.5"
                        />

                        {/* Volume Bar */}
                        <rect
                          x={xBox}
                          y={volY}
                          width={chartMetrics.candleWidth}
                          height={Math.max(1, volBarHeight)}
                          fill={color}
                          opacity={isHovered ? "0.8" : "0.35"}
                        />

                        {/* Date label tick every few bars */}
                        {i % Math.max(1, Math.floor(candles.length / 7)) === 0 ? (
                          <text
                            x={xCenter}
                            y={
                              chartMetrics.padding.top +
                              chartMetrics.priceHeight +
                              chartMetrics.volumeHeight +
                              32
                            }
                            textAnchor="middle"
                            className="font-mono text-[8.5px] fill-ink-faint"
                          >
                            {c.date.slice(5)}
                          </text>
                        ) : null}
                      </g>
                    );
                  })}
                  {markSeries.length > 0 ? (
                    <polyline
                      points={markSeries
                        .map((m) => {
                          const i = candleIndexOnOrAfter(candles, m.date);
                          if (i < 0) return null;
                          const x =
                            chartMetrics.padding.left +
                            i * chartMetrics.slotWidth +
                            chartMetrics.slotWidth / 2;
                          return `${x},${chartMetrics.scaleY(m.avgEntry)}`;
                        })
                        .filter(Boolean)
                        .join(" ")}
                      fill="none"
                      stroke="#38bdf8"
                      strokeWidth="1.4"
                      strokeDasharray="4 3"
                    />
                  ) : (
                    <line
                      x1={chartMetrics.padding.left}
                      y1={chartMetrics.scaleY(currentOrExitPrice)}
                      x2={chartMetrics.width - chartMetrics.padding.right}
                      y2={chartMetrics.scaleY(currentOrExitPrice)}
                      stroke={isOpen ? "#06b6d4" : trade.is_win ? "#10b981" : "#f43f5e"}
                      strokeWidth="1.5"
                      strokeDasharray="4 3"
                    />
                  )}

                  {/* Volume Separator Line */}
                  <line
                    x1={chartMetrics.padding.left}
                    y1={chartMetrics.padding.top + chartMetrics.priceHeight + 15}
                    x2={chartMetrics.width - chartMetrics.padding.right}
                    y2={chartMetrics.padding.top + chartMetrics.priceHeight + 15}
                    stroke="#334155"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />

                  {/* Entry Execution Badge Overlay (lot-only when no campaign fills) */}
                  {fills.length < 2 && chartMetrics.entryIdx != null && chartMetrics.entryIdx >= 0 ? (
                    (() => {
                      const x =
                        chartMetrics.padding.left +
                        chartMetrics.entryIdx * chartMetrics.slotWidth +
                        chartMetrics.slotWidth / 2;
                      const y = chartMetrics.scaleY(trade.entry_price);
                      const entryLabel = isLong
                        ? `BUY $${trade.entry_price.toFixed(1)}`
                        : `SHORT $${trade.entry_price.toFixed(1)}`;
                      const bgFill = isLong ? "#0369a1" : "#7e22ce";
                      const borderCol = isLong ? "#38bdf8" : "#c084fc";

                      return (
                        <g transform={`translate(${x}, ${y})`}>
                          <circle r="4" fill={borderCol} />
                          <polygon
                            points={isLong ? "-4,-7 4,-7 0,-1" : "-4,7 4,7 0,1"}
                            fill={borderCol}
                          />
                          <rect
                            x="-28"
                            y={isLong ? "-22" : "9"}
                            width="56"
                            height="14"
                            rx="3"
                            fill={bgFill}
                            stroke={borderCol}
                            strokeWidth="1"
                          />
                          <text
                            x="0"
                            y={isLong ? "-12" : "19"}
                            textAnchor="middle"
                            fill="#ffffff"
                            fontSize="8.5"
                            fontWeight="bold"
                            fontFamily="monospace"
                          >
                            {entryLabel}
                          </text>
                        </g>
                      );
                    })()
                  ) : null}

                  {/* Exit Execution Badge Overlay (lot-only when no campaign fills) */}
                  {fills.length < 2 && chartMetrics.exitIdx != null && chartMetrics.exitIdx >= 0 ? (
                    (() => {
                      const x =
                        chartMetrics.padding.left +
                        chartMetrics.exitIdx * chartMetrics.slotWidth +
                        chartMetrics.slotWidth / 2;
                      const y = chartMetrics.scaleY(currentOrExitPrice);
                      const exitLabel = isOpen
                        ? `MARK $${currentOrExitPrice.toFixed(1)}`
                        : isLong
                        ? `SELL $${currentOrExitPrice.toFixed(1)}`
                        : `COVER $${currentOrExitPrice.toFixed(1)}`;
                      const bgFill = isOpen ? "#0e7490" : (isWin ? "#065f46" : "#881337");
                      const borderCol = isOpen ? "#22d3ee" : (isWin ? "#10b981" : "#f43f5e");

                      return (
                        <g transform={`translate(${x}, ${y})`}>
                          <circle r="4" fill={borderCol} />
                          <polygon
                            points={isLong ? "-4,7 4,7 0,1" : "-4,-7 4,-7 0,-1"}
                            fill={borderCol}
                          />
                          <rect
                            x="-30"
                            y={isLong ? "9" : "-22"}
                            width="60"
                            height="14"
                            rx="3"
                            fill={bgFill}
                            stroke={borderCol}
                            strokeWidth="1"
                          />
                          <text
                            x="0"
                            y={isLong ? "19" : "-12"}
                            textAnchor="middle"
                            className="font-mono text-[8.5px] font-bold fill-slate-100"
                          >
                            {exitLabel}
                          </text>
                        </g>
                      );
                    })()
                  ) : null}

                  {fills.map((fill, i) => {
                    let idx = candles.findIndex((c) => c.date === fill.date);
                    if (idx < 0) {
                      idx = candles.findIndex((c) => c.date >= fill.date);
                    }
                    if (idx < 0) return null;
                    const stack = fills
                      .filter((f) => f.date === fill.date)
                      .findIndex((f) => f === fill);
                    const x =
                      chartMetrics.padding.left +
                      idx * chartMetrics.slotWidth +
                      chartMetrics.slotWidth / 2;
                    const y = chartMetrics.scaleY(fill.price);
                    const color = CAMPAIGN_FILL_COLORS[fill.kind];
                    const isBuy = fill.side === "buy";
                    const labelY = (isBuy ? -16 : 22) + (isBuy ? -1 : 1) * stack * 14;
                    const labelW = Math.max(52, fill.label.length * 6.2);
                    return (
                      <g
                        key={`${fill.date}-${fill.kind}-${i}`}
                        transform={`translate(${x}, ${y})`}
                      >
                        <polygon
                          points={isBuy ? "-5,6 5,6 0,-5" : "-5,-6 5,-6 0,5"}
                          fill={color}
                          stroke="#0f172a"
                          strokeWidth="0.6"
                        />
                        <rect
                          x={-labelW / 2}
                          y={labelY - 10}
                          width={labelW}
                          height="13"
                          rx="3"
                          fill="#0f172a"
                          stroke={color}
                          strokeWidth="1"
                          opacity="0.92"
                        />
                        <text
                          x="0"
                          y={labelY}
                          textAnchor="middle"
                          fill={color}
                          fontSize="8"
                          fontWeight="bold"
                          fontFamily="monospace"
                        >
                          {fill.label}
                        </text>
                      </g>
                    );
                  })}

                  {/* Interactive Floating Hover Gain/Loss Crosshair Badge */}
                  {hoverIndex != null && candles[hoverIndex] && hoverGainLoss != null && chartMetrics ? (() => {
                    const c = candles[hoverIndex]!;
                    const xCenter = chartMetrics.padding.left + hoverIndex * chartMetrics.slotWidth + chartMetrics.slotWidth / 2;
                    const tooltipW = 190;
                    const tooltipH = 34;
                    const clampX = Math.max(
                      chartMetrics.padding.left + tooltipW / 2 + 6,
                      Math.min(chartMetrics.width - chartMetrics.padding.right - tooltipW / 2 - 6, xCenter)
                    );
                    const tooltipY = chartMetrics.padding.top + 6;
                    const isPositive = hoverGainLoss.dollars >= 0;
                    const badgeColor = isPositive ? "#10b981" : "#f43f5e";
                    const pnlText = `${isPositive ? "+" : ""}${formatCurrency(hoverGainLoss.dollars)} (${isPositive ? "+" : ""}${hoverGainLoss.pct.toFixed(2)}%)`;

                    return (
                      <g pointerEvents="none" transform={`translate(${clampX}, ${tooltipY})`}>
                        <rect
                          x={-tooltipW / 2}
                          y={0}
                          width={tooltipW}
                          height={tooltipH}
                          rx={5}
                          fill="#090d16"
                          stroke={badgeColor}
                          strokeWidth="1.2"
                          opacity="0.96"
                        />
                        <text
                          x={-tooltipW / 2 + 8}
                          y={13}
                          fill="#94a3b8"
                          fontSize="9"
                          fontFamily="monospace"
                          fontWeight="bold"
                        >
                          {c.date} · C ${c.close.toFixed(2)}
                        </text>
                        <text
                          x={-tooltipW / 2 + 8}
                          y={26}
                          fill={badgeColor}
                          fontSize="10"
                          fontFamily="monospace"
                          fontWeight="bold"
                        >
                          {isPositive ? "Gain: " : "Loss: "}{pnlText}
                        </text>
                      </g>
                    );
                  })() : null}
                </svg>
              </div>
              {fills.length > 0 ? (
                <div className="overflow-x-auto rounded border border-line">
                  <table className="w-full text-left text-[11px] font-mono">
                    <thead className="bg-surface-sunk text-[10px] uppercase tracking-wider text-ink-faint">
                      <tr>
                        <th className="px-2 py-1.5">Date</th>
                        <th className="px-2 py-1.5">Side</th>
                        <th className="px-2 py-1.5">Role</th>
                        <th className="px-2 py-1.5 text-right">Qty</th>
                        <th className="px-2 py-1.5 text-right">Fill</th>
                        <th className="px-2 py-1.5 text-right">Open after</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fills.map((f, i) => (
                        <tr key={`${f.date}-${f.kind}-${i}`} className="border-t border-line/70">
                          <td className="px-2 py-1 text-ink">{f.date}</td>
                          <td
                            className={`px-2 py-1 font-semibold ${
                              f.side === "buy" ? "text-emerald-400" : "text-rose-400"
                            }`}
                          >
                            {f.side.toUpperCase()}
                          </td>
                          <td className="px-2 py-1" style={{ color: CAMPAIGN_FILL_COLORS[f.kind] }}>
                            {f.label}
                          </td>
                          <td className="px-2 py-1 text-right tabular-nums text-ink">
                            {f.side === "buy" ? "+" : "-"}
                            {f.qty.toLocaleString()}
                          </td>
                          <td className="px-2 py-1 text-right tabular-nums text-ink">
                            ${f.price.toFixed(2)}
                          </td>
                          <td className="px-2 py-1 text-right tabular-nums text-ink">
                            {f.openAfter.toLocaleString()} sh
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="border-t border-line bg-surface-sunk/60 text-ink">
                      <tr>
                        <td className="px-2 py-1.5" colSpan={3}>
                          Bought {shareTotals.bought.toLocaleString()} · sold{" "}
                          {shareTotals.sold.toLocaleString()}
                          {shareTotals.remaining > 0
                            ? ` · runner still open ${shareTotals.remaining.toLocaleString()} sh (LEAN FIFO lots hide this)`
                            : " · flat"}
                        </td>
                        <td className="px-2 py-1.5 text-right tabular-nums" colSpan={3}>
                          Net {shareTotals.remaining.toLocaleString()} sh
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              ) : ordersQuery.isFetching ? (
                <p className="px-1 font-mono text-[10px] text-ink-faint">
                  Loading campaign fills…
                </p>
              ) : null}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-raised px-5 py-2.5 text-[11px] text-ink-muted font-mono">
          <div className="flex items-center gap-3">
            <span>
              ClickHouse source:{" "}
              <code className="text-ink font-semibold">
                {candlesQuery.data?.source || "vera.daily_prices"}
              </code>
              {candles.length > 0 ? ` · ${candles.length} bars` : ""}
            </span>
            {candlesQuery.data?.source ? (
              <CopyIdBadge
                id={`${trade.symbol} (${startWindow}..${endWindow})`}
                label="Query SQL"
                truncate={false}
                sqlQuery={`SELECT date, open, high, low, close, volume FROM ${candlesQuery.data.source} FINAL WHERE ticker = '${trade.symbol}' AND date >= '${startWindow}' AND date <= '${endWindow}' ORDER BY date ASC`}
              />
            ) : null}
            {runId ? (
              <>
                <CopyIdBadge
                  id={`/api/backtests/runs/${runId}/closed-trades?campaign=${trade.symbol}`}
                  label="Campaign Trades API"
                  truncate={false}
                />
                <CopyIdBadge
                  id={`/api/backtests/runs/${runId}/orders?campaign=${trade.symbol}`}
                  label="Campaign Orders API"
                  truncate={false}
                />
              </>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line bg-surface px-3 py-1 font-medium text-ink hover:bg-surface-sunk transition-colors"
          >
            Close Chart (Esc)
          </button>
        </div>
      </div>
    </div>
  );
}
