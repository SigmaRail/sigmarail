import { useState, useEffect, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStockIntrospection } from "../../api/screens";
import { StockChartEngine } from "./StockChartEngine";
import { QuoteHeader } from "./QuoteHeader";
import { FundamentalsRail } from "./FundamentalsRail";
import { WatchlistSidebar } from "./WatchlistSidebar";
import { TradingViewForecastAccuracyChart } from "./TradingViewForecastAccuracyChart";
import { addRecentlyViewed } from "../../lib/watchlistStore";
import {
  loadFundamentalsRailOpen,
  saveFundamentalsRailOpen,
} from "../../lib/fundamentalsRailStorage";
import type { ChartCandlePoint, StockIntrospectionData } from "../../types";

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const WATCHLIST_STRIP_KEY = "vera_charts_watchlist_strip_open";
function loadWatchlistOpen(): boolean {
  try {
    const val = localStorage.getItem(WATCHLIST_STRIP_KEY);
    return val !== null ? val === "true" : false; // default collapsed to save vertical room on lower resolutions
  } catch {
    return false;
  }
}
function saveWatchlistOpen(open: boolean): void {
  try {
    localStorage.setItem(WATCHLIST_STRIP_KEY, String(open));
  } catch {}
}

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

  const [revealFuture, setRevealFuture] = useState(true);
  const [extraHistoryCandles, setExtraHistoryCandles] = useState<ChartCandlePoint[] | null>(null);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [railOpen, setRailOpen] = useState(() => loadFundamentalsRailOpen());
  const [watchlistOpen, setWatchlistOpen] = useState(() => loadWatchlistOpen());
  const [forecastModalOpen, setForecastModalOpen] = useState(false);

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
    addRecentlyViewed(clean);
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
    <div className="flex h-[calc(100vh-3.5rem)] w-full flex-col overflow-hidden bg-canvas">
      <QuoteHeader
        ticker={ticker}
        data={data}
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

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <FundamentalsRail
          data={data}
          open={railOpen}
          onToggle={() => {
            const next = !railOpen;
            setRailOpen(next);
            saveFundamentalsRailOpen(next);
          }}
          onSelectTicker={handleSelectSymbol}
          onOpenForecastModal={() => setForecastModalOpen(true)}
        />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto p-2">
          {chartQuery.isLoading && !data ? (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted animate-pulse">
              Loading ClickHouse candlestick series for {ticker}…
            </div>
          ) : chartQuery.isError ? (
            <div className="flex h-full items-center justify-center px-6 text-center font-mono text-xs text-rose-500">
              {chartQuery.error instanceof Error ? chartQuery.error.message : "Failed to load chart"}
            </div>
          ) : data?.chart_series && data.chart_series.length > 0 ? (
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
              onOpenForecastModal={() => setForecastModalOpen(true)}
            />
          ) : (
            <div className="flex h-full items-center justify-center font-mono text-xs text-ink-muted">
              No chart data available for {ticker}
            </div>
          )}
        </div>
      </div>

      <WatchlistSidebar
        variant="strip"
        activeTicker={ticker}
        onSelectTicker={handleSelectSymbol}
        asOfDate={asOfDate}
        isOpen={watchlistOpen}
        onToggleOpen={() => {
          setWatchlistOpen((open) => {
            const next = !open;
            saveWatchlistOpen(next);
            return next;
          });
        }}
        quotesEnabled={Boolean(chartQuery.data) || chartQuery.isError}
      />

      {/* TradingView Forecasts & Estimates Accuracy Modal */}
      {forecastModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-xs animate-in fade-in duration-150"
          onClick={() => setForecastModalOpen(false)}
        >
          <div
            className="relative w-full max-w-4xl max-h-[92vh] overflow-y-auto rounded-xl border border-line bg-surface shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <TradingViewForecastAccuracyChart
              ticker={ticker}
              asOfDate={inspectedDate}
              quarterlyGrowth={data?.quarterly_growth}
              annualGrowth={data?.annual_growth}
              onClose={() => setForecastModalOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
