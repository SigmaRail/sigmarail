import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTickerCandles } from "../../api/backtests";
import type { ChartCandlePoint } from "../../types";
import { StockChartEngine } from "./StockChartEngine";

function shiftDate(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** Shared chart-engine view for a point-in-time candidate in the backtest report. */
export function CandidatePriceChart({
  ticker,
  asOfDate,
}: {
  ticker: string;
  asOfDate?: string;
}) {
  const anchorDate = asOfDate || new Date().toISOString().slice(0, 10);
  const startDate = useMemo(() => shiftDate(anchorDate, -120), [anchorDate]);
  const endDate = useMemo(() => shiftDate(anchorDate, 20), [anchorDate]);
  const candlesQuery = useQuery({
    queryKey: ["candidate-candles", ticker, startDate, endDate],
    queryFn: () => fetchTickerCandles(ticker, startDate, endDate),
    enabled: Boolean(ticker),
  });
  const candles = useMemo<ChartCandlePoint[]>(
    () =>
      (candlesQuery.data?.candles ?? []).map((candle) => ({
        time: candle.date,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
        is_future: candle.date > anchorDate,
      })),
    [candlesQuery.data?.candles, anchorDate],
  );

  if (!ticker) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Select a ticker to preview its chart.
      </div>
    );
  }

  if (candlesQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading historical candles…
      </div>
    );
  }

  if (candlesQuery.isError) {
    return (
      <div role="alert" className="flex h-full items-center justify-center p-4 text-center text-sm text-destructive">
        {candlesQuery.error instanceof Error ? candlesQuery.error.message : "Unable to load historical candles."}
      </div>
    );
  }

  if (candles.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No historical candles found for {ticker}.
      </div>
    );
  }

  return (
    <StockChartEngine
      ticker={ticker}
      candles={candles}
      screenAsOfDate={anchorDate}
      inspectedDate={anchorDate}
      onSelectDate={() => {}}
      revealFuture
      className="min-h-0 w-full"
    />
  );
}
