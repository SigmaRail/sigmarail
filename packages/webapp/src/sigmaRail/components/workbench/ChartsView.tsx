import { useState, useEffect, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStockIntrospection } from "../../api/screens";
import { StockChartEngine } from "./StockChartEngine";
import { QuoteHeader } from "./QuoteHeader";
import { StockOverviewPanel } from "./StockOverviewPanel";
import { FundamentalsRail } from "./FundamentalsRail";
import { loadFundamentalsRailOpen, saveFundamentalsRailOpen } from "../../lib/fundamentalsRailStorage";
import { QuarterlyForecastAccuracyChart } from "./QuarterlyForecastAccuracyChart";
import type { ChartCandlePoint, StockIntrospectionData } from "../../types";

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

interface ChartsViewProps {
  initialTicker?: string;
  initialAsOfDate?: string;
  onSelectTicker?: (ticker: string) => void;
  onSelectDate?: (date: string) => void;
  className?: string;
}

export function ChartsView({
  initialTicker = "UBER",
  initialAsOfDate = todayIso(),
  onSelectTicker,
  onSelectDate,
}: ChartsViewProps) {
  const [ticker, setTicker] = useState(initialTicker);
  const [searchInput, setSearchInput] = useState(initialTicker);
  const [asOfDate, setAsOfDate] = useState(initialAsOfDate);
  const [inspectedDate, setInspectedDate] = useState(initialAsOfDate);

  // Keep the first view focused on observed history; projections stay opt-in.
  const [revealFuture, setRevealFuture] = useState(false);
  const [extraHistoryCandles, setExtraHistoryCandles] = useState<ChartCandlePoint[] | null>(null);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [earningsOpen, setEarningsOpen] = useState(() => loadFundamentalsRailOpen());

  useEffect(() => {
    if (initialTicker && initialTicker !== ticker) {
      setTicker(initialTicker);
      setSearchInput(initialTicker);
    }
  }, [initialTicker]);

  useEffect(() => {
    if (initialAsOfDate && initialAsOfDate !== asOfDate) {
      setAsOfDate(initialAsOfDate);
      setInspectedDate(initialAsOfDate);
    }
  }, [initialAsOfDate]);

  const chartQuery = useQuery({
    queryKey: ["stock-introspection-chart", ticker, asOfDate],
    queryFn: () => fetchStockIntrospection(ticker, asOfDate, 2500, 10000, false),
    enabled: !!ticker && !!asOfDate,
    staleTime: 300_000,
  });

  const dossierQuery = useQuery({
    queryKey: ["stock-introspection-dossier", ticker, asOfDate],
    queryFn: () => fetchStockIntrospection(ticker, asOfDate, 10, 10, true),
    enabled: !!ticker && !!asOfDate && chartQuery.isSuccess,
    staleTime: 300_000,
  });

  const handleLoadMoreHistory = async () => {
    if (isLoadingMore || !hasMoreHistory || !ticker || !asOfDate) return;
    setIsLoadingMore(true);
    try {
      const fullData = await fetchStockIntrospection(ticker, asOfDate, 10000, 10000, false);
      if (fullData && fullData.chart_series && fullData.chart_series.length > 0) {
        setExtraHistoryCandles(fullData.chart_series);
      }
      setHasMoreHistory(false);
    } catch (err) {
      console.error("Failed to lazy load full history:", err);
    } finally {
      setIsLoadingMore(false);
    }
  };

  const handleSelectSymbol = (newTicker: string) => {
    const clean = newTicker.trim().toUpperCase();
    if (!clean) return;
    setTicker(clean);
    setSearchInput(clean);
    setExtraHistoryCandles(null);
    setHasMoreHistory(true);
    onSelectTicker?.(clean);
  };

  const data = useMemo((): StockIntrospectionData | undefined => {
    const chart = chartQuery.data;
    if (!chart) return undefined;
    const dossier = dossierQuery.data;
    if (!dossier) return chart;
    return {
      ...chart,
      as_of_kpis: { ...chart.as_of_kpis, ...dossier.as_of_kpis },
      quarterly_growth: dossier.quarterly_growth ?? chart.quarterly_growth,
      annual_growth: dossier.annual_growth ?? chart.annual_growth,
      earnings_events: dossier.earnings_events ?? chart.earnings_events,
      industry_peers: dossier.industry_peers ?? chart.industry_peers,
    };
  }, [chartQuery.data, dossierQuery.data]);

  const handleInspectDate = useCallback((newDate: string) => {
    setInspectedDate(newDate);
  }, []);

  const mergedChartSeries = useMemo(() => {
    if (!data?.chart_series) return [];
    if (!extraHistoryCandles) return data.chart_series;
    const seriesMap = new Map<string, ChartCandlePoint>();
    for (const c of extraHistoryCandles) seriesMap.set(c.time, c);
    for (const c of data.chart_series) seriesMap.set(c.time, c);
    return Array.from(seriesMap.values()).sort((a, b) => a.time.localeCompare(b.time));
  }, [data?.chart_series, extraHistoryCandles]);

  return (
    <div
      data-testid="charts-workspace"
      className="flex min-h-full w-full flex-col bg-background"
    >
      <QuoteHeader
        ticker={ticker}
        asOfDate={asOfDate}
        onAsOfDateChange={(d) => {
          setAsOfDate(d);
          setInspectedDate(d);
          onSelectDate?.(d);
        }}
        showSearch
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onSearchSubmit={handleSelectSymbol}
      />

      <div data-testid="charts-content-flow" className="relative isolate flex w-full min-w-0 flex-col">
        <StockOverviewPanel ticker={ticker} data={data} showYearlyEarnings={false} />
        <main className="relative isolate z-0 flex w-full min-w-0 flex-col border-b border-border lg:p-2">
          {chartQuery.isLoading && !data ? (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted animate-pulse">
              Loading ClickHouse candlestick series for {ticker}…
            </div>
          ) : chartQuery.isError ? (
            <div className="flex h-full items-center justify-center px-6 text-center font-mono text-xs text-rose-500">
              {chartQuery.error instanceof Error ? chartQuery.error.message : "Failed to load chart"}
            </div>
          ) : data?.chart_series && data.chart_series.length > 0 ? (
            <>
              <div data-testid="charts-primary-area" className="relative isolate flex min-h-[min(68dvh,720px)] w-full min-w-0 flex-none flex-col">
                <StockChartEngine
                  ticker={ticker}
                  candles={mergedChartSeries}
                  screenAsOfDate={asOfDate}
                  inspectedDate={inspectedDate}
                  onSelectDate={handleInspectDate}
                  historicalMedianPe={data.historical_median_pe}
                  quarterlyGrowth={data.quarterly_growth}
                  annualGrowth={data.annual_growth}
                  earningsEvents={data.earnings_events}
                  revealFuture={revealFuture}
                  onToggleRevealFuture={setRevealFuture}
                  hasMoreHistory={hasMoreHistory}
                  isLoadingMoreHistory={isLoadingMore}
                  onLoadMoreHistory={handleLoadMoreHistory}
                  className="rounded-none border-0 lg:rounded-lg lg:border"
                />
              </div>
              {data.quarterly_growth?.length ? (
                <QuarterlyForecastAccuracyChart
                  className="rounded-none border-x-0 lg:rounded-lg lg:border-x"
                  ticker={ticker}
                  asOfDate={inspectedDate}
                  quarterlyGrowth={data.quarterly_growth}
                  annualGrowth={data.annual_growth}
                />
              ) : null}
              <FundamentalsRail
                data={data}
                open={earningsOpen}
                onToggle={() => {
                  const next = !earningsOpen;
                  setEarningsOpen(next);
                  saveFundamentalsRailOpen(next);
                }}
                showOverviewTab={false}
              />
            </>
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted">
              No chart data available for {ticker}
            </div>
          )}
        </main>
      </div>

    </div>
  );
}
