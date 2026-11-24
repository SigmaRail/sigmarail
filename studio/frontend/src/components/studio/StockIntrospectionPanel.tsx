import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStockIntrospection } from "../../api/screens";
import {
  loadFundamentalsRailOpen,
  saveFundamentalsRailOpen,
} from "../../lib/fundamentalsRailStorage";
import type { ChartCandlePoint } from "../../types";
import { FundamentalsRail } from "./FundamentalsRail";
import { QuoteHeader } from "./QuoteHeader";
import { StockChartEngine } from "./StockChartEngine";
import { Button } from "../ui/primitives";

export function StockChartLoadError({
  ticker,
  error,
  onRetry,
}: {
  ticker: string;
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="flex h-full min-w-0 flex-col items-center justify-center gap-3 px-4 text-center">
      <p className="text-sm font-semibold text-ink">Chart unavailable for {ticker}</p>
      <Button
        type="button"
        variant="secondary"
        onClick={onRetry}
        className="text-xs"
      >
        Retry chart
      </Button>
      <details className="w-full max-w-full text-left">
        <summary className="cursor-pointer text-[11px] text-ink-muted">Technical details</summary>
        <pre className="mt-2 max-h-32 max-w-full overflow-auto whitespace-pre-wrap break-all rounded border border-line bg-surface-raised p-2 font-mono text-[10px] text-rose-500">
          {error instanceof Error ? error.message : "Failed to load chart"}
        </pre>
      </details>
    </div>
  );
}

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
  const [railOpen, setRailOpen] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(min-width: 640px)").matches
      ? loadFundamentalsRailOpen()
      : false,
  );

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
              <Button
                type="button"
                variant="secondary"
                onClick={() => setActiveTicker(ticker)}
                className="min-h-8 px-2 py-0.5 font-mono text-[10px]"
              >
                ← {ticker}
              </Button>
            ) : null}
            {onClose ? (
              <Button
                type="button"
                variant="ghost"
                aria-label="Close stock chart"
                onClick={onClose}
                className="min-h-8 min-w-8 px-2 py-1 text-xs"
              >
                ✕
              </Button>
            ) : null}
          </div>
        }
      />

      <div
        className={`flex min-h-0 flex-1 overflow-hidden ${
          compact ? "min-h-[360px]" : "min-h-[420px]"
        }`}
      >
        <FundamentalsRail
          data={data}
          open={railOpen}
          onToggle={() => {
            const next = !railOpen;
            setRailOpen(next);
            saveFundamentalsRailOpen(next);
          }}
          onSelectTicker={(t) => setActiveTicker(t)}
        />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col p-2">
          {overviewQuery.isLoading && !data ? (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted animate-pulse">
              Loading ClickHouse candlestick series…
            </div>
          ) : overviewQuery.isError ? (
            <StockChartLoadError
              ticker={activeTicker}
              error={overviewQuery.error}
              onRetry={() => void overviewQuery.refetch()}
            />
          ) : data?.chart_series && data.chart_series.length > 0 ? (
            <StockChartEngine
              compact={compact}
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
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted">
              No chart data available for {activeTicker}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
