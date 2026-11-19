import { useState, useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  createChart,
  IChartApi,
  LineSeries,
  HistogramSeries,
  ColorType,
  type LineData,
  type HistogramData,
  type Time,
  type MouseEventParams,
} from "lightweight-charts";
import { fetchMarketContext, type MarketContextPoint } from "../../api/screens";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Card } from "@sb/webapp-core/components/ui/card";
import { PageHeadline } from "@sb/webapp-core/components/pageHeadline";

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

interface MarketViewProps {
  initialAsOfDate?: string;
  onSelectDate?: (date: string) => void;
  className?: string;
}

export function MarketView({
  initialAsOfDate = todayIso(),
  onSelectDate,
  className,
}: MarketViewProps) {
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  const [endDate, setEndDate] = useState(initialAsOfDate);
  const [asOfDate, setAsOfDate] = useState(initialAsOfDate);
  const [isDarkMode, setIsDarkMode] = useState(() => document.documentElement.classList.contains("dark"));
  const [submittedRange, setSubmittedRange] = useState<{ start: string; end: string } | null>(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return {
      start: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`,
      end: initialAsOfDate,
    };
  });

  const query = useQuery({
    queryKey: ["market-context", submittedRange?.start, submittedRange?.end],
    queryFn: () => fetchMarketContext(submittedRange!.start, submittedRange!.end, 2000),
    enabled: !!submittedRange?.start && !!submittedRange?.end,
    staleTime: 60_000,
  });

  const handleRangeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittedRange({ start: startDate, end: endDate });
  };

  const handleInspectChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setAsOfDate(newDate);
    onSelectDate?.(newDate);

    const currentRange = submittedRange ?? { start: startDate, end: endDate };
    if (newDate < currentRange.start) {
      setStartDate(newDate);
      setSubmittedRange({ start: newDate, end: currentRange.end });
    } else if (newDate > currentRange.end) {
      setEndDate(newDate);
      setSubmittedRange({ start: currentRange.start, end: newDate });
    }
  };

  const data = query.data ?? [];

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => setIsDarkMode(root.classList.contains("dark")));
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container || data.length === 0) return;

    const chartBg = isDarkMode ? "#09090b" : "#ffffff";
    const chartText = isDarkMode ? "#a1a1aa" : "#52525b";
    const chartGrid = isDarkMode ? "#27272a" : "#e4e4e7";
    const chart = createChart(container, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: chartBg }, textColor: chartText },
      grid: { vertLines: { color: chartGrid }, horzLines: { color: chartGrid } },
      rightPriceScale: { borderColor: chartGrid },
      leftPriceScale: { borderColor: chartGrid },
      timeScale: { borderColor: chartGrid, timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1 },
    });

    chartApiRef.current = chart;

    // The chart starts with one pane. Add only the three additional panes used
    // below, then give the main price pane most of the available height.
    chart.addPane();
    chart.addPane();
    chart.addPane();
    const [pricePane, breadthPane, allocationPane, volatilityPane] = chart.panes();
    pricePane?.setStretchFactor(4);
    breadthPane?.setStretchFactor(1);
    allocationPane?.setStretchFactor(1);
    volatilityPane?.setStretchFactor(1);

    const spyLine = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 2, priceScaleId: "right", title: "SPY" }, 0);
    const vixLine = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 1, priceScaleId: "left", title: "VIX" }, 0);

    const breadth200d = chart.addSeries(LineSeries, { color: "#22c55e", lineWidth: 1, priceScaleId: "right", title: "Breadth 200d" }, 1);
    const breadth50d = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 1, priceScaleId: "right", title: "Breadth 50d" }, 1);

    const allocationTier = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 2, priceScaleId: "right", title: "Alloc Tier" }, 2);
    const compositeScore = chart.addSeries(LineSeries, { color: "#22d3ee", lineWidth: 1, priceScaleId: "left", title: "Composite" }, 2);
    const maStackScore = chart.addSeries(LineSeries, { color: "#a855f7", lineWidth: 1, priceScaleId: "ma_stack", title: "MA Stack" }, 2);

    const vixClose = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 2, priceScaleId: "right", title: "VIX Close" }, 3);
    const vixContango = chart.addSeries(HistogramSeries, { color: "#ef4444", priceScaleId: "vix_contango", title: "VIX Contango" }, 3);
    const vixVsSma = chart.addSeries(LineSeries, { color: "#22d3ee", lineWidth: 1, priceScaleId: "left", title: "VIX vs SMA20" }, 3);

    const spyLines: LineData<Time>[] = [];
    const vixLines: LineData<Time>[] = [];
    const breadth200dLines: LineData<Time>[] = [];
    const breadth50dLines: LineData<Time>[] = [];
    const allocationTierLines: LineData<Time>[] = [];
    const compositeScoreLines: LineData<Time>[] = [];
    const maStackScoreLines: LineData<Time>[] = [];
    const vixCloseLines: LineData<Time>[] = [];
    const vixContangoData: HistogramData<Time>[] = [];
    const vixVsSmaLines: LineData<Time>[] = [];

    data.forEach((d) => {
      const time = d.date as Time;
      if (d.spy_close !== null) spyLines.push({ time, value: d.spy_close });
      if (d.vix_close !== null) vixLines.push({ time, value: d.vix_close });
      if (d.breadth_200d !== null) breadth200dLines.push({ time, value: d.breadth_200d * 100 });
      if (d.breadth_50d !== null) breadth50dLines.push({ time, value: d.breadth_50d * 100 });
      if (d.weekly_allocation_tier !== null) allocationTierLines.push({ time, value: d.weekly_allocation_tier });
      if (d.composite_score_normalized !== null) compositeScoreLines.push({ time, value: d.composite_score_normalized });
      if (d.ma_stack_score !== null) maStackScoreLines.push({ time, value: d.ma_stack_score });
      if (d.vix_close !== null) vixCloseLines.push({ time, value: d.vix_close });
      if (d.vix_contango_proxy !== null) vixContangoData.push({ time, value: d.vix_contango_proxy ? 1 : 0, color: d.vix_contango_proxy ? "#ef4444" : "#22c55e" });
      if (d.vix_vs_sma20d_pct !== null) vixVsSmaLines.push({ time, value: d.vix_vs_sma20d_pct * 100 });
    });

    spyLine.setData(spyLines);
    vixLine.setData(vixLines);
    breadth200d.setData(breadth200dLines);
    breadth50d.setData(breadth50dLines);
    allocationTier.setData(allocationTierLines);
    compositeScore.setData(compositeScoreLines);
    maStackScore.setData(maStackScoreLines);
    vixClose.setData(vixCloseLines);
    vixContango.setData(vixContangoData);
    vixVsSma.setData(vixVsSmaLines);

    const handleChartClick = (param: MouseEventParams<Time>) => {
      if (param.time && onSelectDate) {
        onSelectDate(param.time as string);
        setAsOfDate(param.time as string);
      }
    };

    chart.subscribeClick(handleChartClick);

    return () => {
      chart.unsubscribeClick(handleChartClick);
      chart.remove();
      chartApiRef.current = null;
    };
  }, [data, onSelectDate, isDarkMode]);

  const metrics: { key: keyof MarketContextPoint; label: string; type: "tier" | "pct" | "flag" | "score" | "price" | "vix" }[] = useMemo(
    () => [
      { key: "weekly_allocation_tier", label: "Allocation Tier", type: "tier" },
      { key: "weekly_allocation_fraction", label: "Allocation Fraction", type: "pct" },
      { key: "composite_score_normalized", label: "Composite Score", type: "score" },
      { key: "market_regime_signal", label: "Regime Signal", type: "score" },
      { key: "is_bear_market_active", label: "Bear Market Active", type: "flag" },
      { key: "breadth_200d", label: "Breadth 200d", type: "pct" },
      { key: "breadth_50d", label: "Breadth 50d", type: "pct" },
      { key: "spy_close", label: "SPY Close", type: "price" },
      { key: "spy_above200d", label: "SPY > 200d", type: "flag" },
      { key: "spy_below200d_3d", label: "SPY < 200d 3d", type: "flag" },
      { key: "ma_stack_score", label: "MA Stack Score", type: "score" },
      { key: "risk_on_fast_flags", label: "Risk-On Flags", type: "score" },
      { key: "risk_off_fast_flags", label: "Risk-Off Flags", type: "score" },
      { key: "clamp_risk_off", label: "Clamp Risk-Off", type: "flag" },
      { key: "distribution_count_25d", label: "Distribution Count 25d", type: "score" },
      { key: "trend_score", label: "Trend Score", type: "score" },
      { key: "vix_close", label: "VIX Close", type: "vix" },
      { key: "vix_spike_flag", label: "VIX Spike", type: "flag" },
      { key: "vix_contango_proxy", label: "VIX Contango", type: "flag" },
      { key: "vix_vs_sma20d_pct", label: "VIX vs SMA20 %", type: "pct" },
    ],
    [],
  );

  const formatValue = (point: MarketContextPoint, key: keyof MarketContextPoint): string => {
    const val = point[key];
    if (val === null || val === undefined) return "—";
    const metric = metrics.find((m) => m.key === key);
    if (!metric) return String(val);
    switch (metric.type) {
      case "pct":
        return typeof val === "number" ? `${(val * 100).toFixed(1)}%` : String(val);
      case "tier":
        return typeof val === "number" ? `${val}%` : String(val);
      case "flag":
        return typeof val === "number" ? (val ? "●" : "○") : String(val);
      case "score":
        return typeof val === "number" ? val.toFixed(1) : String(val);
      case "price":
        return typeof val === "number" ? `$${val.toFixed(2)}` : String(val);
      case "vix":
        return typeof val === "number" ? val.toFixed(2) : String(val);
      default:
        return String(val);
    }
  };

  const getColor = (point: MarketContextPoint | null, key: keyof MarketContextPoint): string => {
    if (!point) return "text-ink-muted";
    const val = point[key];
    if (val === null || val === undefined) return "text-ink-muted";
    const metric = metrics.find((m) => m.key === key);
    if (!metric) return "text-ink-muted";
    if (metric.type === "flag") return typeof val === "number" && val ? "text-green-400" : "text-red-400";
    if (metric.type === "tier" && typeof val === "number") return val >= 67 ? "text-green-400" : val >= 33 ? "text-amber-400" : "text-red-400";
    if (metric.type === "score" && typeof val === "number") return val >= 50 ? "text-green-400" : "text-red-400";
    if (metric.type === "vix" && typeof val === "number") return val > 30 ? "text-red-400" : val > 20 ? "text-amber-400" : "text-green-400";
    return "text-ink-muted";
  };

  const asOfPoint = data.find((d) => d.date === asOfDate) ?? null;

  return (
    <div className={cn("flex h-full min-h-0 flex-col overflow-y-auto bg-background lg:overflow-hidden", className)}>
      <header className="shrink-0 space-y-3 border-b px-3 py-3 sm:px-4">
        <PageHeadline
          header="Market context"
          subheader="Review regime, breadth, and volatility through time."
          className="space-y-1"
        />

        <Card className="flex flex-col gap-3 p-3 shadow-none sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
        <form onSubmit={handleRangeSubmit} aria-label="Market history date range" className="grid min-w-0 grid-cols-[1fr_auto_1fr_auto] items-end gap-2 sm:flex sm:items-end">
          <label className="min-w-0 text-xs font-medium text-muted-foreground">From
          <Input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="mt-1 block h-9 min-w-0 w-full font-mono text-xs sm:mt-1 sm:w-auto"
          />
          </label>
          <span className="pb-2 text-muted-foreground">to</span>
          <label className="min-w-0 text-xs font-medium text-muted-foreground">Through
          <Input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="mt-1 block h-9 min-w-0 w-full font-mono text-xs sm:mt-1 sm:w-auto"
          />
          </label>
          <Button
            type="submit"
            variant="outline"
            className="h-9 px-3 text-xs"
          >
            Load
          </Button>
        </form>

        </Card>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-visible lg:flex-row lg:overflow-hidden">
        <Card aria-label="Market history chart" className="relative min-h-[34rem] w-full min-w-0 flex-1 overflow-hidden rounded-none border-0 bg-background shadow-none lg:min-h-0">
          {query.isLoading && <div className="absolute inset-0 z-[1] grid place-items-center bg-surface/70 text-sm text-ink-muted">Loading market history…</div>}
          {query.isError && <div className="absolute inset-x-3 top-3 z-[2] rounded-md border border-danger/30 bg-danger-soft p-3 text-sm text-danger">Market data could not be loaded: {(query.error as Error).message}</div>}
          <div ref={chartContainerRef} className="h-[34rem] w-full sm:h-[38rem] lg:h-full" />
        </Card>

        <Card className="w-full shrink-0 rounded-none border-x-0 border-b-0 border-t p-3 shadow-none lg:w-80 lg:overflow-y-auto lg:border-b lg:border-l lg:border-t-0">
          <div className="space-y-2 border-b border-line pb-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Current Session</h2>
              <label className="flex items-center gap-2 text-[11px] font-medium text-muted-foreground">
                <span>As of</span>
                <Input
                  aria-label="Inspect date"
                  type="date"
                  value={asOfDate}
                  onChange={handleInspectChange}
                  className="h-8 w-36 px-2 font-mono text-xs"
                />
              </label>
            </div>
            {asOfPoint ? (
              <>
              <div className="grid grid-cols-2 gap-2 font-mono sm:grid-cols-3 lg:grid-cols-2">
                {metrics.slice(0, 6).map((m) => (
                  <Card key={m.key} className={cn("rounded-md p-2 shadow-none", getColor(asOfPoint, m.key).replace("text-", "border-") + "/30")}>
                    <span className="text-[10px] uppercase font-medium text-muted-foreground">{m.label}</span>
                    <div className={cn("mt-0.5 text-sm font-semibold", getColor(asOfPoint, m.key))}>
                      {formatValue(asOfPoint, m.key)}
                    </div>
                  </Card>
                ))}
              </div>
              <details className="group pt-1">
                <summary className="min-h-10 cursor-pointer list-none rounded-md border border-line px-3 py-2 text-xs font-medium text-ink-muted hover:bg-surface-raised [&::-webkit-details-marker]:hidden">All session metrics <span className="float-right group-open:rotate-180">⌄</span></summary>
                <div className="grid grid-cols-2 gap-2 pt-2 font-mono sm:grid-cols-3 lg:grid-cols-2">
                  {metrics.slice(6).map((m) => (
                  <Card key={m.key} className={cn("rounded-md p-2 shadow-none", getColor(asOfPoint, m.key).replace("text-", "border-") + "/30")}>
                    <span className="text-[10px] uppercase font-medium text-muted-foreground">{m.label}</span>
                    <div className={cn("mt-0.5 text-sm font-semibold", getColor(asOfPoint, m.key))}>{formatValue(asOfPoint, m.key)}</div>
                  </Card>
                  ))}
                </div>
              </details>
              </>
            ) : (
              <p className="text-xs text-ink-muted">Choose a date on the chart to inspect its available metrics.</p>
            )}
          </div>

          <details className="group pt-3">
            <summary className="min-h-10 cursor-pointer list-none rounded-md border border-line px-3 py-2 text-xs font-medium text-ink-muted hover:bg-surface-raised [&::-webkit-details-marker]:hidden">Metric guide <span className="float-right group-open:rotate-180">⌄</span></summary>
            <div className="grid grid-cols-1 gap-1 pt-2 font-mono text-[10px] text-ink-muted">
              {metrics.map((m) => (
                <div key={m.key} className="flex items-center gap-1.5 p-1 rounded border border-line/50 hover:bg-surface-raised transition-colors">
                  <span className="w-8 text-center font-bold" style={{ color: getColor({ date: "", [m.key]: 1 } as unknown as MarketContextPoint, m.key).replace("text-", "") }}>
                    {m.type === "flag" ? "●" : m.type === "tier" ? "▲" : "■"}
                  </span>
                  <span className="font-semibold truncate">{m.label}</span>
                  <span className="text-[9px] truncate flex-1">{getMetricDescription(m.key)}</span>
                </div>
              ))}
            </div>
          </details>
        </Card>
      </div>
    </div>
  );
}

function getMetricDescription(key: keyof MarketContextPoint): string {
  const descriptions: Record<string, string> = {
    weekly_allocation_tier: "Weekly regime allocation tier (0/33/67/100)",
    weekly_allocation_fraction: "Continuous allocation fraction 0..1",
    composite_score_normalized: "Regime composite score normalized 0..100",
    market_regime_signal: "Regime bucket signal (0/50/100)",
    is_bear_market_active: "Bear market override active",
    breadth_200d: "Fraction of universe above 200d SMA",
    breadth_50d: "Fraction of universe above 50d SMA",
    spy_close: "SPY official close price",
    spy_above200d: "SPY above 200d SMA",
    spy_below200d_3d: "SPY below 200d for 3+ days",
    ma_stack_score: "MA stack score 0..5",
    risk_on_fast_flags: "Fast risk-on diagnostic count 0..4",
    risk_off_fast_flags: "Fast risk-off diagnostic count 0..4",
    clamp_risk_off: "Daily clamp forcing risk-off",
    distribution_count_25d: "Distribution days in last 25 sessions",
    trend_score: "Weekly trend template score 0..6",
    vix_close: "VIX index close",
    vix_spike_flag: "VIX ATR% > 1.5x 20d avg",
    vix_contango_proxy: "UVXY basis > SVXY basis (contango)",
    vix_vs_sma20d_pct: "VIX vs 20d SMA percentage",
  };
  return descriptions[key] || "";
}
