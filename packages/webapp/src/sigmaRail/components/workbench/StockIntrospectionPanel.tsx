import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStockIntrospection } from "../../api/screens";
import { loadFundamentalsRailOpen, saveFundamentalsRailOpen } from "../../lib/fundamentalsRailStorage";
import { FundamentalsRail } from "./FundamentalsRail";
import { QuoteHeader } from "./QuoteHeader";
import { StockOverviewPanel } from "./StockOverviewPanel";
import { WeeklyPriceChart } from "./WeeklyPriceChart";
import { Button } from "@sb/webapp-core/components/ui/button";
import { StrategyDecisionTimeline } from "./StrategyDecisionTimeline";
import type { StrategyDecisionEvent } from "../../types";

/** Shared compact stock context used by screener and strategy membership review. */
export function StockIntrospectionPanel({
  ticker,
  asOfDate,
  onClose,
  className = "",
  compact = false,
  showOverview = true,
  decisionEvents,
  strategyHash,
  sourceLabel,
  markContext,
  contextLabel,
  decisionStart,
  decisionEnd,
}: {
  ticker: string;
  asOfDate: string;
  onClose?: () => void;
  className?: string;
  compact?: boolean;
  showOverview?: boolean;
  decisionEvents?: StrategyDecisionEvent[];
  strategyHash?: string | null;
  sourceLabel?: string;
  markContext?: { label: string; value: string; timestamp: string };
  contextLabel?: string;
  decisionStart?: string;
  decisionEnd?: string;
}) {
  const [activeTicker, setActiveTicker] = useState(ticker);
  const [inspectedDate, setInspectedDate] = useState(asOfDate);
  const [railOpen, setRailOpen] = useState(() => {
    const narrow = typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
    return loadFundamentalsRailOpen(undefined, !narrow);
  });

  useEffect(() => {
    setActiveTicker(ticker);
    setInspectedDate(asOfDate);
  }, [ticker, asOfDate]);

  const overviewQuery = useQuery({
    queryKey: ["stock-introspection-panel", activeTicker, inspectedDate],
    queryFn: () => fetchStockIntrospection(activeTicker, inspectedDate, 2500, 10000, true),
    enabled: Boolean(activeTicker && inspectedDate),
    staleTime: 300_000,
  });
  const data = overviewQuery.data;

  return (
    <div className={`flex min-h-0 flex-col overflow-hidden bg-surface ${className}`}>
      <QuoteHeader
        ticker={activeTicker}
        asOfDate={inspectedDate}
        trailing={
          <div className="flex items-center gap-1.5">
            {activeTicker !== ticker ? (
              <Button type="button" onClick={() => setActiveTicker(ticker)} variant="outline" size="sm" className="h-7 px-2 font-mono text-[10px]" aria-label={`Return to ${ticker}`}>
                ← {ticker}
              </Button>
            ) : null}
            {onClose ? (
              <Button type="button" onClick={onClose} variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" aria-label={`Close ${activeTicker} review`} title="Close stock review">
                ✕
              </Button>
            ) : null}
          </div>
        }
      />

      <div className={`flex min-h-0 flex-1 flex-col overflow-y-auto ${compact ? "min-h-[360px]" : "min-h-[420px]"}`}>
        {markContext ? (
          <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 border-b border-line bg-surface-raised px-3 py-2 text-[10px] sm:px-4">
            <span className="text-ink-muted">{markContext.label}</span>
            <span className="text-right font-mono font-semibold text-ink">{markContext.value}</span>
            <span className="text-ink-muted">Snapshot</span>
            <time className="text-right font-mono text-ink-muted" dateTime={markContext.timestamp}>{markContext.timestamp}</time>
          </div>
        ) : null}
        {decisionEvents ? (
          <StrategyDecisionTimeline
            events={decisionEvents}
            asOf={inspectedDate}
            startAt={decisionStart}
            endAt={decisionEnd}
            strategyHash={strategyHash}
            sourceLabel={sourceLabel}
          />
        ) : null}
        {contextLabel ? (
          <div className="border-b border-line px-3 py-1.5 font-mono text-[9px] text-ink-muted sm:px-4">{contextLabel}</div>
        ) : null}
        {overviewQuery.isLoading && !data ? (
          <div className="flex h-36 items-center justify-center font-mono text-xs text-ink-muted animate-pulse">Loading weekly price history…</div>
        ) : overviewQuery.isError ? (
          <div className="flex h-36 items-center justify-center px-4 text-center font-mono text-xs text-rose-500">
            {overviewQuery.error instanceof Error ? overviewQuery.error.message : "Failed to load stock context"}
          </div>
        ) : data ? (
          <>
            <WeeklyPriceChart ticker={activeTicker} asOfDate={inspectedDate} candles={data.chart_series ?? []} />
            {showOverview ? <StockOverviewPanel ticker={activeTicker} data={data} showYearlyEarnings={false} /> : null}
          </>
        ) : null}

        <FundamentalsRail
          data={data}
          open={railOpen}
          onToggle={() => {
            const next = !railOpen;
            setRailOpen(next);
            saveFundamentalsRailOpen(next);
          }}
          showOverviewTab={!showOverview}
        />
      </div>
    </div>
  );
}
