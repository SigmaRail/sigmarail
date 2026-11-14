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
    setEndDate(newDate);
    setSubmittedRange((prev) => ({ start: prev?.start || startDate, end: newDate }));
  };

  const data = query.data ?? [];

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container || data.length === 0) return;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#0f172a" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      rightPriceScale: { borderColor: "#1e293b" },
      leftPriceScale: { borderColor: "#1e293b" },
      timeScale: { borderColor: "#1e293b", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1 },
    });

    chartApiRef.current = chart;

    chart.addPane();
    chart.addPane();
    chart.addPane();
    chart.addPane();

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
  }, [data, onSelectDate]);

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
    <div className={cn("flex flex-col h-[90vh] bg-surface-sunk", className)}>
      <div className="p-3 border-b border-line flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-lg font-bold text-accent">📈 Market Context</span>
          <span className="text-xs font-semibold text-ink-muted">Market Regime & VIX Overlay Over Time</span>
        </div>

        <form onSubmit={handleRangeSubmit} className="flex items-center gap-1.5">
          <span className="text-[10px] text-ink-muted">Range:</span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="rounded-lg border border-line bg-surface-sunk px-2 py-1 font-mono text-xs text-ink focus:border-accent focus:outline-none"
          />
          <span className="text-ink-muted">→</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="rounded-lg border border-line bg-surface-sunk px-2 py-1 font-mono text-xs text-ink focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            className="rounded-lg bg-accent/20 border border-accent/30 px-2 py-1 font-mono text-xs text-accent hover:bg-accent/30 transition-colors"
          >
            Load
          </button>
        </form>

        <div className="flex items-center gap-1 rounded-lg border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 font-mono text-xs font-bold text-amber-500">
          <span>📍 Inspect:</span>
          <input
            type="date"
            value={asOfDate}
            onChange={handleInspectChange}
            className="bg-transparent text-amber-400 focus:outline-none cursor-pointer font-mono text-xs"
          />
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div ref={chartContainerRef} className="flex-1 w-full min-w-0" style={{ minHeight: 600, paddingBottom: 24 }} />

        <div className="w-80 border-l border-line bg-surface-sunk p-3 overflow-y-auto flex-shrink-0">
          <div className="space-y-2 border-b border-line pb-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold uppercase tracking-wider text-accent text-[11px]">Current Session</span>
              <span className="font-mono text-[10px] text-ink-muted">{asOfDate}</span>
            </div>
            {asOfPoint && (
              <div className="grid grid-cols-2 gap-1 text-[10px] font-mono">
                {metrics.map((m) => (
                  <div key={m.key} className={cn("rounded border p-1.5", getColor(asOfPoint, m.key).replace("text-", "border-") + "/30")}>
                    <span className="text-[8.5px] uppercase font-bold text-ink-muted">{m.label}</span>
                    <div className={cn("text-sm font-bold", getColor(asOfPoint, m.key))}>
                      {formatValue(asOfPoint, m.key)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <span className="font-bold uppercase tracking-wider text-accent text-[11px]">Metric Guide</span>
            <div className="grid grid-cols-1 gap-0.5 font-mono text-[10px] text-ink-muted">
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
          </div>
        </div>
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