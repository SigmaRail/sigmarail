import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStockIntrospection } from "../../api/screens";
import type { ChartCandlePoint } from "../../types";
import { StockOverviewPanel } from "./StockOverviewPanel";
import { QuoteHeader } from "./QuoteHeader";
import { StockChartEngine } from "./StockChartEngine";
import { TradingViewForecastAccuracyChart } from "./TradingViewForecastAccuracyChart";

/**
 * MarketSurge-style chart body shared by Charts tab, Screener introspection,
 * and membership ticker inspect (Universe / Alpha / Screens).
 */
export function StockIntrospectionPanel({
  ticker,
  asOfDate,
  onClose,
  className = "",
  compact = false,
}: {
  ticker: string;
  asOfDate: string;
  onClose?: () => void;
  className?: string;
  /** Tighter chrome for embed under membership tables. */
  compact?: boolean;
}) {
  const [activeTicker, setActiveTicker] = useState(ticker);
  const [revealFuture, setRevealFuture] = useState(true);
  const [inspectedDate, setInspectedDate] = useState(asOfDate);
  const [extraHistoryCandles, setExtraHistoryCandles] = useState<
    ChartCandlePoint[] | null
  >(null);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  useEffect(() => {
    setActiveTicker(ticker);
    setInspectedDate(asOfDate);
    setExtraHistoryCandles(null);
    setHasMoreHistory(true);
    setIsLoadingMore(false);
  }, [ticker, asOfDate]);

  const overviewQuery = useQuery({
    queryKey: ["stock-introspection-panel", activeTicker, inspectedDate],
    queryFn: () =>
      fetchStockIntrospection(activeTicker, inspectedDate, 2500, 10000),
    enabled: Boolean(activeTicker && inspectedDate),
    staleTime: 300_000,
  });

  const handleLoadMoreHistory = async () => {
    if (isLoadingMore || !hasMoreHistory || !activeTicker || !inspectedDate) {
      return;
    }
    setIsLoadingMore(true);
    try {
      const fullData = await fetchStockIntrospection(
        activeTicker,
        inspectedDate,
        10000,
        10000,
      );
      if (fullData?.chart_series?.length) {
        setExtraHistoryCandles(fullData.chart_series);
      }
      setHasMoreHistory(false);
    } catch (err) {
      console.error("Failed to lazy load full history:", err);
    } finally {
      setIsLoadingMore(false);
    }
  };

  const data = overviewQuery.data;

  const mergedChartSeries = useMemo(() => {
    const base = data?.chart_series || [];
    const map = new Map<string, ChartCandlePoint>();
    if (extraHistoryCandles?.length) {
      for (const c of extraHistoryCandles) map.set(c.time, c);
    }
    for (const c of base) map.set(c.time, c);
    return Array.from(map.values()).sort((a, b) => a.time.localeCompare(b.time));
  }, [data?.chart_series, extraHistoryCandles]);

  return (
    <div
      className={`flex min-h-0 flex-col overflow-hidden bg-surface ${className}`}
    >
      <QuoteHeader
        ticker={activeTicker}
        data={data}
        asOfDate={asOfDate}
        trailing={
          <div className="flex items-center gap-1.5">
            {activeTicker !== ticker ? (
              <button
                type="button"
                onClick={() => setActiveTicker(ticker)}
                className="rounded border border-accent/40 bg-accent/20 px-2 py-0.5 font-mono text-[10px] text-accent hover:bg-accent/30"
              >
                ← {ticker}
              </button>
            ) : null}
            {onClose ? (
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-line bg-surface p-1.5 text-xs text-ink-muted hover:bg-surface-sunk hover:text-ink"
              >
                ✕
              </button>
            ) : null}
          </div>
        }
      />

      <div className={`grid min-h-0 min-w-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[minmax(0,1fr)_18rem] lg:overflow-hidden ${compact ? "min-h-[360px]" : "min-h-[420px]"}`}>
        <main className={`flex min-w-0 flex-col gap-2 border-b border-line lg:min-h-0 lg:overflow-y-auto lg:p-2 ${compact ? "min-h-[360px]" : "min-h-[420px]"}`}>
          {overviewQuery.isLoading && !data ? (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted animate-pulse">
              Loading ClickHouse candlestick series…
            </div>
          ) : overviewQuery.isError ? (
            <div className="flex h-full items-center justify-center px-4 text-center font-mono text-xs text-rose-500">
              {overviewQuery.error instanceof Error
                ? overviewQuery.error.message
                : "Failed to load chart"}
            </div>
          ) : data?.chart_series && data.chart_series.length > 0 ? (
            <>
              <StockChartEngine
                className="h-auto min-h-0 rounded-none border-0 lg:rounded-lg lg:border"
                candles={mergedChartSeries}
                screenAsOfDate={asOfDate}
                inspectedDate={inspectedDate}
                onSelectDate={(newDate) => setInspectedDate(newDate)}
                historicalMedianPe={data.historical_median_pe}
                quarterlyGrowth={data.quarterly_growth}
                annualGrowth={data.annual_growth}
                earningsEvents={data.earnings_events}
                revealFuture={revealFuture}
                onToggleRevealFuture={setRevealFuture}
                hasMoreHistory={hasMoreHistory}
                isLoadingMoreHistory={isLoadingMore}
                onLoadMoreHistory={handleLoadMoreHistory}
              />
              {data.quarterly_growth?.length ? (
                <TradingViewForecastAccuracyChart
                  className="rounded-none border-x-0 lg:rounded-lg lg:border-x"
                  ticker={activeTicker}
                  asOfDate={inspectedDate}
                  quarterlyGrowth={data.quarterly_growth}
                  quarterlyOnly
                />
              ) : null}
            </>
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted">
              No chart data available for {activeTicker}
            </div>
          )}
        </main>
        <div className="min-w-0 border-line lg:min-h-0 lg:overflow-y-auto lg:border-l">
          <StockOverviewPanel data={data} />
        </div>
      </div>
    </div>
  );
}
