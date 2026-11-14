import { useEffect, useRef, useState, useMemo } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  PriceScaleMode,
  LineType,
  LineStyle,
  CandlestickSeries,
  LineSeries,
  AreaSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type CandlestickData,
  type LineData,
  type AreaData,
  type HistogramData,
  type Time,
  type SeriesMarker,
  type LogicalRange,
} from "lightweight-charts";
import type {
  AnnualGrowthPoint,
  ChartCandlePoint,
  EarningsReportEvent,
  QuarterlyGrowthPoint,
} from "../../types";
import {
  getTfBag,
  loadChartSettings,
  saveChartSettings,
  setTfBag,
  type ChartIndicatorKey,
  type ChartRangePreset,
  type ChartSettingsV2,
  type ChartTimeframe,
} from "../../lib/chartSettings";
import { cn } from "../../lib/utils";

interface StockChartEngineProps {
  ticker?: string;
  candles: ChartCandlePoint[];
  screenAsOfDate: string;
  inspectedDate: string;
  onSelectDate: (dateStr: string) => void;
  historicalMedianPe?: number;
  quarterlyGrowth?: QuarterlyGrowthPoint[];
  annualGrowth?: AnnualGrowthPoint[];
  earningsEvents?: EarningsReportEvent[];
  revealFuture: boolean;
  onToggleRevealFuture?: (reveal: boolean) => void;
  customGrowthRate?: number | null;
  hasMoreHistory?: boolean;
  isLoadingMoreHistory?: boolean;
  onLoadMoreHistory?: () => Promise<void> | void;
  onOpenForecastModal?: () => void;
  className?: string;
}

type IndicatorOption = {
  key: ChartIndicatorKey;
  label: string;
  weeklyLabel?: string;
  category: string;
  description: string;
  weeklyOnly?: boolean;
};

/** Candles + ratio overlays (RS, SPY) share this band. Flags sit at 0.73-0.80, volume at top: 0.82. */
const PRICE_PANE_MARGINS = { top: 0.05, bottom: 0.28 } as const;

const INDICATOR_OPTIONS: IndicatorOption[] = [
  { key: "rsLine", label: "RS Line", category: "Trend", description: "Relative strength vs SPY, overlaid on price (own scale)" },
  { key: "earningsLine", label: "Earnings Line", category: "Fundamental", description: "Quarterly EPS $ on a separate scale", weeklyOnly: true },
  { key: "earningsFlags", label: "Earnings flags", category: "Events", description: "Report badges with EPS surprise %" },
  { key: "epsLine", label: "EPS Drift", category: "Fundamental", description: "TTM EPS trajectory scaled to median P/E" },
  { key: "fairValueRibbon", label: "Fair Value Ribbon", category: "Valuation", description: "±10% and ±30% intrinsic value bands" },
  { key: "valuationCorridor", label: "Valuation Corridor", category: "Valuation", description: "Graham 15x versus normal P/E corridor" },
  { key: "expectationTracks", label: "Expectation Tracks", category: "Forecast", description: "1Y and 2Y prior target tracks" },
  { key: "multipleRibbon", label: "Multiples Fan", category: "Valuation", description: "Discrete P/E bands from 10x to 25x" },
  { key: "forecast", label: "Forecast", category: "Forecast", description: "Forward 2-year valuation forecast" },
  { key: "ema10", label: "10 EMA", weeklyLabel: "10W EMA", category: "Trend", description: "Short-term exponential moving average" },
  { key: "ema21", label: "21 EMA", weeklyLabel: "21W EMA", category: "Trend", description: "Medium-term trend follow" },
  { key: "sma50", label: "50 SMA", weeklyLabel: "50W SMA", category: "Trend", description: "50-period simple moving average" },
  { key: "sma200", label: "200 SMA", weeklyLabel: "200W SMA", category: "Trend", description: "Long-term trend baseline" },
  { key: "spxOverlay", label: "SPX overlay", category: "Trend", description: "SPY close on a secondary scale" },
];

function computeSma(values: number[], period: number): Array<number | null> {
  const out: Array<number | null> = [];
  let running = 0;
  for (let i = 0; i < values.length; i++) {
    running += values[i];
    if (i >= period) running -= values[i - period];
    if (i >= period - 1) out.push(running / period);
    else out.push(null);
  }
  return out;
}

function computeEma(values: number[], period: number): Array<number | null> {
  const out: Array<number | null> = [];
  const k = 2 / (period + 1);
  let ema: number | null = null;
  let seed = 0;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) {
      seed += values[i];
      out.push(null);
      continue;
    }
    if (ema === null) {
      seed += values[i];
      ema = seed / period;
    } else {
      ema = values[i] * k + ema * (1 - k);
    }
    out.push(ema);
  }
  return out;
}

function applyWeeklyMovingAverages(weekly: ChartCandlePoint[]): void {
  const closes = weekly.map((c) => c.close ?? 0);
  const ema10 = computeEma(closes, 10);
  const ema21 = computeEma(closes, 21);
  const sma50 = computeSma(closes, 50);
  const sma200 = computeSma(closes, 200);
  for (let i = 0; i < weekly.length; i++) {
    weekly[i].sma10 = ema10[i] != null ? Math.round(ema10[i]! * 100) / 100 : null;
    weekly[i].ema21 = ema21[i] != null ? Math.round(ema21[i]! * 100) / 100 : null;
    weekly[i].sma50 = sma50[i] != null ? Math.round(sma50[i]! * 100) / 100 : null;
    weekly[i].sma200 = sma200[i] != null ? Math.round(sma200[i]! * 100) / 100 : null;
  }
}

function persistSettings(next: ChartSettingsV2): ChartSettingsV2 {
  saveChartSettings(next);
  return next;
}

function parseIsoDate(str: string): [number, number, number] {
  const parts = str.split("-").map(Number);
  return [parts[0], parts[1] - 1, parts[2]];
}

function getMondayIso(dateStr: string): string {
  const [y, m, d] = parseIsoDate(dateStr);
  const dt = new Date(Date.UTC(y, m, d));
  const day = dt.getUTCDay();
  const diff = dt.getUTCDate() - day + (day === 0 ? -6 : 1);
  const mon = new Date(Date.UTC(y, m, diff));
  return mon.toISOString().slice(0, 10);
}

function chartTimeForDate(dateStr: string, timeframe: ChartTimeframe): string {
  if (!dateStr) return dateStr;
  return timeframe === "1W" ? getMondayIso(dateStr) : dateStr;
}

/** lightweight-charts requires strictly ascending unique times. */
function dedupeByTime<T extends { time: Time | string }>(data: T[]): T[] {
  const byTime = new Map<string, T>();
  for (const point of data) {
    byTime.set(String(point.time), point);
  }
  return Array.from(byTime.values()).sort((a, b) =>
    String(a.time).localeCompare(String(b.time)),
  );
}

function nearestCandle(
  time: string,
  candles: ChartCandlePoint[],
): ChartCandlePoint | undefined {
  const exact = candles.find((c) => c.time === time);
  if (exact) return exact;
  const later = candles.find((c) => c.time >= time);
  if (later) return later;
  for (let i = candles.length - 1; i >= 0; i--) {
    if (candles[i].time <= time) return candles[i];
  }
  return undefined;
}

const CHART_HEIGHT_STORAGE_KEY = "vera_chart_canvas_height";
function loadSavedChartHeight(): number {
  try {
    const val = localStorage.getItem(CHART_HEIGHT_STORAGE_KEY);
    if (val) {
      const num = parseInt(val, 10);
      if (num >= 320 && num <= 850) return num;
    }
  } catch {}
  return 480; // Sensible default provides ample room for candles, flags, and volume
}

export function StockChartEngine({
  ticker,
  candles,
  screenAsOfDate,
  inspectedDate,
  onSelectDate,
  historicalMedianPe = 20,
  quarterlyGrowth = [],
  earningsEvents = [],
  revealFuture,
  onToggleRevealFuture,
  customGrowthRate,
  hasMoreHistory = false,
  isLoadingMoreHistory = false,
  onLoadMoreHistory,
  onOpenForecastModal,
  className,
}: StockChartEngineProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const lastLogicalRangeRef = useRef<LogicalRange | null>(null);
  const prevTickerRef = useRef<string | undefined>(ticker);

  const [settings, setSettings] = useState<ChartSettingsV2>(() => loadChartSettings());
  const timeframe = settings.lastTimeframe;
  const prevTimeframeRef = useRef<ChartTimeframe>(timeframe);
  const bag = getTfBag(settings, timeframe);
  const indicatorConfig = bag.indicators;
  const activeRange = bag.range;

  // When switching tickers or switching timeframe, reset preserved zoom range to use default preset
  useEffect(() => {
    if (ticker && prevTickerRef.current !== ticker) {
      prevTickerRef.current = ticker;
      lastLogicalRangeRef.current = null;
    }
  }, [ticker]);

  useEffect(() => {
    if (prevTimeframeRef.current !== timeframe) {
      prevTimeframeRef.current = timeframe;
      lastLogicalRangeRef.current = null;
    }
  }, [timeframe]);

  const [isLogScale, setIsLogScale] = useState(false);
  const [indicatorMenuOpen, setIndicatorMenuOpen] = useState(false);
  const [indicatorSearch, setIndicatorSearch] = useState("");
  const indicatorMenuRef = useRef<HTMLDivElement | null>(null);
  const indicatorButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        !indicatorMenuOpen ||
        !indicatorMenuRef.current ||
        !indicatorButtonRef.current ||
        indicatorMenuRef.current.contains(event.target as Node) ||
        indicatorButtonRef.current.contains(event.target as Node)
      ) {
        return;
      }
      setIndicatorMenuOpen(false);
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [indicatorMenuOpen]);

  const patchActiveBag = (partial: Partial<{ indicators: typeof indicatorConfig; range: ChartRangePreset }>) => {
    setSettings((prev) => {
      const current = getTfBag(prev, prev.lastTimeframe);
      const next = persistSettings(
        setTfBag(prev, prev.lastTimeframe, {
          indicators: partial.indicators ?? current.indicators,
          range: partial.range ?? current.range,
        }),
      );
      return next;
    });
  };

  const setIndicator = (key: ChartIndicatorKey, value: boolean) => {
    setSettings((prev) => {
      const cur = getTfBag(prev, prev.lastTimeframe);
      return persistSettings(
        setTfBag(prev, prev.lastTimeframe, {
          ...cur,
          indicators: { ...cur.indicators, [key]: value },
        }),
      );
    });
  };

  const setTimeframe = (tf: ChartTimeframe) => {
    setSettings((prev) => persistSettings({ ...prev, lastTimeframe: tf }));
  };

  const showRsLine = indicatorConfig.rsLine;
  const showEarningsLine = timeframe === "1W" && indicatorConfig.earningsLine;
  const showEpsLine = indicatorConfig.epsLine;
  const showEarningsFlags = indicatorConfig.earningsFlags;
  const showFairValueRibbon = indicatorConfig.fairValueRibbon;
  const showValuationCorridor = indicatorConfig.valuationCorridor;
  const showExpectationTracks = indicatorConfig.expectationTracks;
  const showMultipleRibbon = indicatorConfig.multipleRibbon;
  const showForecast = indicatorConfig.forecast;
  const show10Ema = indicatorConfig.ema10;
  const show21Ema = indicatorConfig.ema21;
  const show50Sma = indicatorConfig.sma50;
  const show200Sma = indicatorConfig.sma200;
  const showSpxOverlay = indicatorConfig.spxOverlay;

  const activeIndicatorCount = Object.entries(indicatorConfig).filter(([key, on]) => {
    if (!on) return false;
    if (key === "earningsLine" && timeframe !== "1W") return false;
    return true;
  }).length;
  const filteredIndicators = INDICATOR_OPTIONS.filter((option) => {
    const query = indicatorSearch.trim().toLowerCase();
    if (!query) return true;
    const label = timeframe === "1W" ? (option.weeklyLabel ?? option.label) : option.label;
    return (
      label.toLowerCase().includes(query) ||
      option.description.toLowerCase().includes(query) ||
      option.category.toLowerCase().includes(query)
    );
  });

    const [chartHeight, setChartHeight] = useState<number>(() => loadSavedChartHeight());

  const handleChartHeightChange = (newHeight: number) => {
    setChartHeight(newHeight);
    try {
      localStorage.setItem(CHART_HEIGHT_STORAGE_KEY, String(newHeight));
    } catch {}
  };


  const [hoveredCandle, setHoveredCandle] = useState<ChartCandlePoint | null>(null);
  const [isPlayingReplay, setIsPlayingReplay] = useState(false);

  // Filter candles based on blind mode (revealFuture) and apply dynamic customGrowthRate
  const displayDailyCandles = useMemo(() => {
    let list = revealFuture ? candles : candles.filter((c) => !c.is_future);
    if (customGrowthRate === null || customGrowthRate === undefined) return list;

    const isPast = inspectedDate < screenAsOfDate;
    const boundedGrowth = Math.max(-20.0, Math.min(customGrowthRate, 35.0));
    const medianPe = Math.max(10.0, Math.min(historicalMedianPe || 20.0, 30.0));
    const growthStep = Math.pow(1 + boundedGrowth / 100, 1 / 252) - 1;

    // Find anchor index at inspectedDate
    let anchorIdx = -1;
    for (let i = 0; i < list.length; i++) {
      if (list[i].time <= inspectedDate) {
        anchorIdx = i;
      } else {
        break;
      }
    }

    if (anchorIdx < 0) return list;
    const anchorCandle = list[anchorIdx];
    const baseEps = anchorCandle.eps_trailing_12m || 1.0;

    return list.map((c, idx) => {
      if (idx < anchorIdx) return c;
      const dayI = idx - anchorIdx;
      if (dayI > 505) return c;

      const projEps = baseEps * Math.pow(1 + growthStep, dayI);
      const peNorm = Math.round(projEps * medianPe * 100) / 100;
      const pe15 = Math.round(projEps * 15.0 * 100) / 100;
      const pe10 = Math.round(projEps * 10.0 * 100) / 100;
      const pe12_5 = Math.round(projEps * 12.5 * 100) / 100;
      const pe17_5 = Math.round(projEps * 17.5 * 100) / 100;
      const pe20 = Math.round(projEps * 20.0 * 100) / 100;
      const pe25 = Math.round(projEps * 25.0 * 100) / 100;

      return {
        ...c,
        ghost_fair_value_15pe: pe15,
        ghost_normal_pe: peNorm,
        ghost_pe_10_0: pe10,
        ghost_pe_12_5: pe12_5,
        ghost_pe_15_0: pe15,
        ghost_pe_17_5: pe17_5,
        ghost_pe_20_0: pe20,
        ghost_pe_25_0: pe25,
        ghost_pe_normal: peNorm,
        fair_value_15pe: isPast ? c.fair_value_15pe : pe15,
        normal_pe_val: isPast ? c.normal_pe_val : peNorm,
        pe_10_0: isPast ? c.pe_10_0 : pe10,
        pe_12_5: isPast ? c.pe_12_5 : pe12_5,
        pe_15_0: isPast ? c.pe_15_0 : pe15,
        pe_17_5: isPast ? c.pe_17_5 : pe17_5,
        pe_20_0: isPast ? c.pe_20_0 : pe20,
        pe_25_0: isPast ? c.pe_25_0 : pe25,
        pe_normal: isPast ? c.pe_normal : peNorm,
      };
    });
  }, [candles, revealFuture, customGrowthRate, historicalMedianPe, inspectedDate, screenAsOfDate]);

  // Process candles (Daily or Weekly aggregation)
  const processedCandles = useMemo(() => {
    if (timeframe === "1D") return dedupeByTime(displayDailyCandles);

    // Separate historical trading bars from forecast extension bars
    const historicalDaily = displayDailyCandles.filter(
      (c) => c.close !== null && c.close !== undefined && !c.is_forecast
    );
    const forecastDaily = displayDailyCandles.filter((c) => c.is_forecast);

    // Aggregate historical daily candles by calendar week
    const weeks: Record<string, ChartCandlePoint[]> = {};
    for (const c of historicalDaily) {
      const weekKey = getMondayIso(c.time);
      if (!weeks[weekKey]) weeks[weekKey] = [];
      weeks[weekKey].push(c);
    }

    const weeklyList: ChartCandlePoint[] = [];
    const sortedKeys = Object.keys(weeks).sort();

    for (const wKey of sortedKeys) {
      const group = weeks[wKey];
      if (group.length === 0) continue;
      const sorted = [...group].sort((a, b) => a.time.localeCompare(b.time));
      const o = sorted[0].open ?? sorted[0].close ?? 0;
      const h = Math.max(...sorted.map((x) => x.high ?? x.close ?? 0));
      const l = Math.min(...sorted.map((x) => x.low ?? x.close ?? 0));
      const cl = sorted[sorted.length - 1].close ?? o;
      const vol = sorted.reduce((acc, x) => acc + (x.volume ?? 0), 0);
      const isFut = sorted.some((x) => x.is_future);

      const lastBar = sorted[sorted.length - 1];
      const hasEarnings = sorted.some((x) => x.is_earnings_report);
      const reportBar = sorted.find((x) => x.is_earnings_report) || lastBar;

      weeklyList.push({
        ...lastBar,
        time: wKey,
        open: o,
        high: h,
        low: l,
        close: cl,
        volume: vol,
        spy_close: lastBar.spy_close,
        is_earnings_report: hasEarnings,
        earnings_growth_yoy: reportBar.earnings_growth_yoy,
        revenue_growth_yoy: reportBar.revenue_growth_yoy,
        is_future: isFut,
        is_forecast: false,
      });
    }

    applyWeeklyMovingAverages(weeklyList);

    // Aggregate forecast points by week
    const forecastWeeks: Record<string, ChartCandlePoint[]> = {};
    for (const c of forecastDaily) {
      const weekKey = getMondayIso(c.time);
      if (!forecastWeeks[weekKey]) forecastWeeks[weekKey] = [];
      forecastWeeks[weekKey].push(c);
    }
    const existingWeeks = new Set(weeklyList.map((c) => c.time));
    for (const fwKey of Object.keys(forecastWeeks).sort()) {
      if (existingWeeks.has(fwKey)) continue;
      const group = forecastWeeks[fwKey];
      const lastBar = group[group.length - 1];
      weeklyList.push({
        time: fwKey,
        open: 0,
        high: 0,
        low: 0,
        close: 0,
        volume: 0,
        eps_trailing_12m: lastBar.eps_trailing_12m,
        eps_line_val: lastBar.eps_line_val,
        fair_value_15pe: lastBar.fair_value_15pe,
        normal_pe_val: lastBar.normal_pe_val,
        is_earnings_report: group.some((x) => x.is_earnings_report),
        earnings_growth_yoy: lastBar.earnings_growth_yoy,
        revenue_growth_yoy: null,
        is_future: true,
        is_forecast: true,
      });
      existingWeeks.add(fwKey);
    }

    return dedupeByTime(weeklyList);
  }, [displayDailyCandles, timeframe]);

  const handleResetView = () => {
    lastLogicalRangeRef.current = null;
    if (chartApiRef.current) {
      applyRangeToChart(chartApiRef.current, "2Y", processedCandles);
      chartApiRef.current.priceScale("right").applyOptions({ autoScale: true });
      patchActiveBag({ range: "2Y" });
    }
  };

  // Current inspected index in processedCandles
  const inspectedIndex = useMemo(() => {
    const targetDate = timeframe === "1W" ? getMondayIso(inspectedDate) : inspectedDate;
    const idx = processedCandles.findIndex((c) => c.time === targetDate);
    if (idx !== -1) return idx;

    // Nearest past candle <= targetDate
    for (let i = processedCandles.length - 1; i >= 0; i--) {
      if (processedCandles[i].time <= targetDate) return i;
    }
    return processedCandles.length - 1;
  }, [processedCandles, inspectedDate, timeframe]);

  // Active Candle for toolbar stats display (defaults to inspectedDate, or hovered candle)
  const activeCandle = useMemo(() => {
    if (hoveredCandle) return hoveredCandle;
    if (inspectedIndex >= 0 && inspectedIndex < processedCandles.length) {
      return processedCandles[inspectedIndex];
    }
    return processedCandles[processedCandles.length - 1] || null;
  }, [hoveredCandle, processedCandles, inspectedIndex]);

  // Auto-Replay stepping effect
  useEffect(() => {
    if (!isPlayingReplay) return;
    const interval = setInterval(() => {
      if (inspectedIndex < processedCandles.length - 1) {
        const nextDate = processedCandles[inspectedIndex + 1].time;
        onSelectDate(nextDate);
      } else {
        setIsPlayingReplay(false);
      }
    }, 600);
    return () => clearInterval(interval);
  }, [isPlayingReplay, inspectedIndex, processedCandles, onSelectDate]);

  // Apply Range Preset to TimeScale
  // Apply Range Preset to TimeScale with generous right padding
  const applyRangeToChart = (chart: IChartApi, range: ChartRangePreset, candlesList: ChartCandlePoint[]) => {
    if (candlesList.length === 0) return;
    if (!candlesList || candlesList.length === 0) return;

    const totalBars = candlesList.length;
    const lastBarIdx = totalBars - 1;
    const PADDING_BARS = 18; // Generous space so candles are never covered by right-axis labels

    if (range === "ALL") {
      chart.timeScale().fitContent();
      try {
        chart.timeScale().setVisibleLogicalRange({
          from: 0,
          to: lastBarIdx + PADDING_BARS,
        });
      } catch {
        chart.timeScale().fitContent();
      }
      return;
    }

    const lastCandle = candlesList[lastBarIdx];
    const [ly, lm, ld] = parseIsoDate(lastCandle.time);
    const lastDate = new Date(Date.UTC(ly, lm, ld));

    let targetFromDate: string;
    if (range === "6Y") {
      // 4 Years of History before screen date + 2 Years Forecast to the end
      const [sy, sm, sd] = parseIsoDate(screenAsOfDate);
      const screenDateObj = new Date(Date.UTC(sy, sm, sd));
      targetFromDate = new Date(screenDateObj.getTime() - 4 * 365.25 * 86400000).toISOString().slice(0, 10);
    } else {
      let daysBack = 365;
      if (range === "3M") daysBack = 90;
      else if (range === "6M") daysBack = 180;
      else if (range === "1Y") daysBack = 365;
      else if (range === "2Y") daysBack = 730;
      else if (range === "5Y") daysBack = 1825;
      targetFromDate = new Date(lastDate.getTime() - daysBack * 86400000).toISOString().slice(0, 10);
    }

    const fromIdx = Math.max(0, candlesList.findIndex((c) => c.time >= targetFromDate));

    try {
      chart.timeScale().setVisibleLogicalRange({
        from: fromIdx,
        to: lastBarIdx + PADDING_BARS,
      });
    } catch {
      chart.timeScale().fitContent();
    }
  };

  // Initialize and mount Lightweight-Charts
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const bars = dedupeByTime(processedCandles);
    const container = chartContainerRef.current;
    const width = Math.max(container.clientWidth || 0, 400);
    const height = Math.max(container.clientHeight || 0, 300);

    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#475569",
        fontSize: 10,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.18)" },
        horzLines: { color: "rgba(148, 163, 184, 0.18)" },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: "rgba(59, 130, 246, 0.55)", width: 1, style: 1 },
        horzLine: { color: "rgba(59, 130, 246, 0.4)", width: 1, style: 1 },
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.35)",
        timeVisible: false,
        secondsVisible: false,
        rightOffset: 18,
        barSpacing: 8,
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.35)",
        autoScale: true,
        textColor: "#475569",
        mode: isLogScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
        scaleMargins: { ...PRICE_PANE_MARGINS },
      },
    });

    chartApiRef.current = chart;

    // 1. Candlestick Series (Primary)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
      priceLineColor: "rgba(37, 99, 235, 0.7)",
    });

    const candleData: CandlestickData<Time>[] = dedupeByTime(
      bars
        .filter((c) => !c.is_forecast && typeof c.close === "number" && typeof c.open === "number" && typeof c.high === "number" && typeof c.low === "number" && c.close > 0)
        .map((c) => ({
          time: c.time as Time,
          open: c.open!,
          high: c.high!,
          low: c.low!,
          close: c.close!,
        })),
    );
    candleSeries.setData(candleData);

    // 2. Volume Series (Sub-pane at bottom 16%)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "#64748b",
      priceFormat: { type: "volume" },
      priceScaleId: "volume_pane",
    });

    chart.priceScale("volume_pane").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0.0 },
      visible: false,
    });

    const volData: HistogramData<Time>[] = dedupeByTime(
      bars
        .filter((c) => c.volume !== null && c.volume !== undefined && !c.is_forecast)
        .map((c) => ({
          time: c.time as Time,
          value: c.volume,
          color: c.close >= c.open ? "rgba(16, 185, 129, 0.45)" : "rgba(239, 68, 68, 0.45)",
        })),
    );
    volumeSeries.setData(volData);

    // 3. Trailing EPS Trajectory Line (Trailing 12M EPS * Median P/E Multiple)
    if (showEpsLine) {
      const epsSeries = chart.addSeries(LineSeries, {
        color: "#10b981", // Green fundamental trajectory
        lineWidth: 2,
        title: `EPS (${historicalMedianPe}x)`,
      });
      const epsData: LineData<Time>[] = dedupeByTime(
        bars
          .filter((c) => (showForecast || !c.is_forecast) && c.eps_line_val !== null && c.eps_line_val !== undefined && c.eps_line_val > 0)
          .map((c) => ({ time: c.time as Time, value: c.eps_line_val! })),
      );
      epsSeries.setData(epsData);
    }

    // 4. Fundamental Valuation Corridor (Area Shading + Graham 15x Baseline + Normal P/E Target)
    if (showValuationCorridor) {
      const isPastInspection = inspectedDate < screenAsOfDate;
      const fair15AreaSeries = chart.addSeries(AreaSeries, {
        topColor: isPastInspection ? "rgba(34, 197, 94, 0.16)" : "rgba(34, 197, 94, 0.28)",
        bottomColor: "rgba(34, 197, 94, 0.02)",
        lineColor: "#f97316", // Graham 15x orange baseline
        lineWidth: 2,
        lineStyle: isPastInspection ? 2 : 0,
        title: "15x",
      });
      const fair15Data: AreaData<Time>[] = dedupeByTime(
        bars
          .filter((c) => {
            if (isPastInspection) {
              return c.ghost_fair_value_15pe !== null && c.ghost_fair_value_15pe !== undefined && c.ghost_fair_value_15pe > 0;
            }
            return (showForecast || !c.is_forecast) && c.fair_value_15pe !== null && c.fair_value_15pe !== undefined && c.fair_value_15pe > 0;
          })
          .map((c) => ({
            time: c.time as Time,
            value: isPastInspection ? c.ghost_fair_value_15pe! : c.fair_value_15pe!,
          })),
      );
      fair15AreaSeries.setData(fair15Data);

      const normalPeSeries = chart.addSeries(LineSeries, {
        color: "#38bdf8", // Sky blue normal P/E line
        lineWidth: 2,
        lineStyle: isPastInspection ? 2 : 0,
        title: `${historicalMedianPe}x`,
      });
      const normalData: LineData<Time>[] = bars
        .filter((c) => {
          if (isPastInspection) {
            return c.ghost_normal_pe !== null && c.ghost_normal_pe !== undefined && c.ghost_normal_pe > 0;
          }
          return (showForecast || !c.is_forecast) && c.normal_pe_val !== null && c.normal_pe_val !== undefined && c.normal_pe_val > 0;
        })
        .map((c) => ({
          time: c.time as Time,
          value: isPastInspection ? c.ghost_normal_pe! : c.normal_pe_val!,
        }));
      normalPeSeries.setData(dedupeByTime(normalData));
    }

    // 4b. Multi-Multiple Valuation Ribbon (Discrete P/E Tracks: 10x, 12.5x, 15x, 17.5x, 20x, 25x)
    if (showMultipleRibbon) {
      const isPastInspection = inspectedDate < screenAsOfDate;
      const peConfigs = [
        { key: "pe_10_0", label: "10.0x", color: "#60a5fa", width: 1, style: 2 },
        { key: "pe_12_5", label: "12.5x", color: "#22d3ee", width: 1, style: 2 },
        { key: "pe_17_5", label: "17.5x", color: "#2dd4bf", width: 1, style: 2 },
        { key: "pe_20_0", label: "20.0x", color: "#34d399", width: 1, style: 2 },
        { key: "pe_25_0", label: "25.0x", color: "#c084fc", width: 1 as const, style: 1 },
      ] as const;

      for (const cfg of peConfigs) {
        const peSeries = chart.addSeries(LineSeries, {
          color: cfg.color,
          lineWidth: cfg.width,
          lineStyle: cfg.style,
          title: cfg.label,
        });
        const fieldKey = isPastInspection ? `ghost_${cfg.key}` : cfg.key;
        const peData: LineData<Time>[] = bars
          .filter((c) => {
            const val = (c as any)[fieldKey];
            if (isPastInspection) return val !== null && val !== undefined && val > 0;
            return (showForecast || !c.is_forecast) && val !== null && val !== undefined && val > 0;
          })
          .map((c) => ({ time: c.time as Time, value: (c as any)[fieldKey] }));
        peSeries.setData(dedupeByTime(peData));
      }
    }

    // 4c. Continuous Walk-Forward Expectation Tracks (1-Year Cyan & 2-Year Purple Prior Targets)
    if (showExpectationTracks) {
      const fwd1ySeries = chart.addSeries(LineSeries, {
        color: "#06b6d4", // Cyan 1-Year Walk-Forward Prior Target
        lineWidth: 2,
        lineStyle: 2,
        lastValueVisible: false,
        title: "1Y Prior Forecast Track",
      });
      const fwd1yData: LineData<Time>[] = bars
        .filter((c) => c.fwd_track_1y !== null && c.fwd_track_1y !== undefined && c.fwd_track_1y > 0)
        .map((c) => ({ time: c.time as Time, value: c.fwd_track_1y! }));
      fwd1ySeries.setData(dedupeByTime(fwd1yData));

      const fwd2ySeries = chart.addSeries(LineSeries, {
        color: "#c084fc", // Purple 2-Year Walk-Forward Prior Target
        lineWidth: 2,
        lineStyle: 2,
        lastValueVisible: false,
        title: "2Y Prior Forecast Track",
      });
      const fwd2yData: LineData<Time>[] = bars
        .filter((c) => c.fwd_track_2y !== null && c.fwd_track_2y !== undefined && c.fwd_track_2y > 0)
        .map((c) => ({ time: c.time as Time, value: c.fwd_track_2y! }));
      fwd2ySeries.setData(dedupeByTime(fwd2yData));
    }

    // 4d. Intrinsic Fair Value Deviation Ribbon (±10% and ±30% Overvalued / Undervalued Envelope)
    if (showFairValueRibbon) {
      // +30% Upper Overvalued Band (Red / Coral Area)
      const p30Series = chart.addSeries(AreaSeries, {
        lineColor: "#f87171",
        lineWidth: 1,
        lineStyle: 2,
        topColor: "rgba(239, 68, 68, 0.18)",
        bottomColor: "rgba(239, 68, 68, 0.03)",
        lastValueVisible: false,
        title: "+30% Overvalued Band",
      });
      const p30Data: AreaData<Time>[] = bars
        .filter((c) => c.fv_band_p30 !== null && c.fv_band_p30 !== undefined && c.fv_band_p30 > 0)
        .map((c) => ({ time: c.time as Time, value: c.fv_band_p30! }));
      p30Series.setData(dedupeByTime(p30Data));

      // +10% Premium Band (Peach Line)
      const p10Series = chart.addSeries(LineSeries, {
        color: "#fb923c",
        lineWidth: 1,
        lineStyle: 2,
        lastValueVisible: false,
        title: "+10% Premium Band",
      });
      const p10Data: LineData<Time>[] = bars
        .filter((c) => c.fv_band_p10 !== null && c.fv_band_p10 !== undefined && c.fv_band_p10 > 0)
        .map((c) => ({ time: c.time as Time, value: c.fv_band_p10! }));
      p10Series.setData(dedupeByTime(p10Data));

      // Fair Value Baseline (White/Charcoal center line)
      const fvCenterSeries = chart.addSeries(LineSeries, {
        color: "#f8fafc",
        lineWidth: 2,
        lineStyle: 0,
        lastValueVisible: false,
        title: "Fair Value Line",
      });
      const fvCenterData: LineData<Time>[] = bars
        .filter((c) => c.fair_value_price !== null && c.fair_value_price !== undefined && c.fair_value_price > 0)
        .map((c) => ({ time: c.time as Time, value: c.fair_value_price! }));
      fvCenterSeries.setData(dedupeByTime(fvCenterData));

      // -10% Discount Band (Mint Green Line)
      const m10Series = chart.addSeries(LineSeries, {
        color: "#34d399",
        lineWidth: 1,
        lineStyle: 2,
        lastValueVisible: false,
        title: "-10% Discount Band",
      });
      const m10Data: LineData<Time>[] = bars
        .filter((c) => c.fv_band_m10 !== null && c.fv_band_m10 !== undefined && c.fv_band_m10 > 0)
        .map((c) => ({ time: c.time as Time, value: c.fv_band_m10! }));
      m10Series.setData(dedupeByTime(m10Data));

      // -30% Lower Bargain Band (Deep Emerald Area)
      const m30Series = chart.addSeries(AreaSeries, {
        lineColor: "#10b981",
        lineWidth: 1,
        lineStyle: 2,
        topColor: "rgba(16, 185, 129, 0.03)",
        bottomColor: "rgba(16, 185, 129, 0.18)",
        lastValueVisible: false,
        title: "-30% Bargain Band",
      });
      const m30Data: AreaData<Time>[] = bars
        .filter((c) => c.fv_band_m30 !== null && c.fv_band_m30 !== undefined && c.fv_band_m30 > 0)
        .map((c) => ({ time: c.time as Time, value: c.fv_band_m30! }));
      m30Series.setData(dedupeByTime(m30Data));
    }

    // 5. MarketSurge RS Line — overlay on the price pane with a hidden independent
    // scale so the ratio (~50 vs SPY) autoscales across candle height, not a 16% strip.
    if (showRsLine) {
      const rsLineSeries = chart.addSeries(LineSeries, {
        color: "#0284c7", // MarketSurge iconic royal blue
        lineWidth: 2,
        title: "RS",
        priceScaleId: "rs_overlay",
        priceLineVisible: false,
      });

      const rsEmaSeries = chart.addSeries(LineSeries, {
        color: "rgba(56, 189, 248, 0.6)", // Cyan 21 EMA
        lineWidth: 1,
        title: "RS21",
        priceScaleId: "rs_overlay",
        priceLineVisible: false,
      });

      chart.priceScale("rs_overlay").applyOptions({
        visible: false,
        autoScale: true,
        scaleMargins: { ...PRICE_PANE_MARGINS },
      });

      const rsData: LineData<Time>[] = dedupeByTime(
        bars
          .filter((c) => c.rs_line !== null && c.rs_line !== undefined && c.rs_line > 0)
          .map((c) => ({ time: c.time as Time, value: c.rs_line! })),
      );
      rsLineSeries.setData(rsData);

      // Compute 21 EMA for RS Line
      const emaData: LineData<Time>[] = [];
      const k = 2 / (21 + 1);
      let ema = 0;
      for (let i = 0; i < rsData.length; i++) {
        const val = rsData[i].value;
        if (i === 0) {
          ema = val;
        } else {
          ema = val * k + ema * (1 - k);
        }
        if (i >= 5) {
          emaData.push({ time: rsData[i].time, value: Math.round(ema * 10000) / 10000 });
        }
      }
      rsEmaSeries.setData(dedupeByTime(emaData));
    }

    // 6. Moving Average Series
    if (show10Ema) {
      const ema10Series = chart.addSeries(LineSeries, {
        color: "#22c55e",
        lineWidth: 1,
        title: timeframe === "1W" ? "10W" : "10D",
      });
      const data: LineData<Time>[] = bars
        .filter((c) => c.sma10 !== null && c.sma10 !== undefined)
        .map((c) => ({ time: c.time as Time, value: c.sma10! }));
      ema10Series.setData(dedupeByTime(data));
    }

    if (show21Ema) {
      const ema21Series = chart.addSeries(LineSeries, {
        color: "#38bdf8",
        lineWidth: 1,
        title: timeframe === "1W" ? "21W" : "21D",
      });
      const data: LineData<Time>[] = bars
        .filter((c) => c.ema21 !== null && c.ema21 !== undefined)
        .map((c) => ({ time: c.time as Time, value: c.ema21! }));
      ema21Series.setData(dedupeByTime(data));
    }

    if (show50Sma) {
      const sma50Series = chart.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 2,
        title: timeframe === "1W" ? "50W" : "50D",
      });
      const data: LineData<Time>[] = bars
        .filter((c) => c.sma50 !== null && c.sma50 !== undefined)
        .map((c) => ({ time: c.time as Time, value: c.sma50! }));
      sma50Series.setData(dedupeByTime(data));
    }

    if (show200Sma) {
      const sma200Series = chart.addSeries(LineSeries, {
        color: "#f43f5e",
        lineWidth: 2,
        title: timeframe === "1W" ? "200W" : "200D",
      });
      const data: LineData<Time>[] = bars
        .filter((c) => c.sma200 !== null && c.sma200 !== undefined)
        .map((c) => ({ time: c.time as Time, value: c.sma200! }));
      sma200Series.setData(dedupeByTime(data));
    }

    if (showSpxOverlay) {
      const spxSeries = chart.addSeries(LineSeries, {
        color: "#94a3b8",
        lineWidth: 1,
        title: "SPY",
        priceScaleId: "spx",
      });
      chart.priceScale("spx").applyOptions({
        visible: false,
        scaleMargins: { ...PRICE_PANE_MARGINS },
      });
      const spxData: LineData<Time>[] = dedupeByTime(
        bars
          .filter((c) => !c.is_forecast && c.spy_close != null && c.spy_close > 0)
          .map((c) => ({ time: c.time as Time, value: c.spy_close! })),
      );
      spxSeries.setData(spxData);
    }

    if (showEarningsLine) {
      const epsByTime = new Map<string, number>();
      for (const ev of earningsEvents) {
        if (ev.eps == null) continue;
        const t = chartTimeForDate(ev.date, timeframe);
        epsByTime.set(t, ev.eps);
      }
      for (const q of quarterlyGrowth) {
        if (!q.is_estimate || q.eps == null || !q.report_date) continue;
        const t = chartTimeForDate(q.report_date, timeframe);
        epsByTime.set(t, q.eps);
      }
      const earningsPoints: LineData<Time>[] = [];
      for (const [t, value] of [...epsByTime.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
        const candle = nearestCandle(t, bars.filter((c) => !c.is_forecast));
        if (!candle) continue;
        earningsPoints.push({ time: candle.time as Time, value });
      }
      if (earningsPoints.length > 0) {
        const earningsSeries = chart.addSeries(LineSeries, {
          color: "#16a34a",
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          lineType: LineType.Curved, // Smooth curve between quarterly points (no jagged steps)
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          priceScaleId: "earnings_eps",
          priceFormat: { type: "price", precision: 2, minMove: 0.01 },
        });
        chart.priceScale("earnings_eps").applyOptions({
          visible: false, // Don't crowd the right price axis with EPS numbers
          scaleMargins: { ...PRICE_PANE_MARGINS },
        });
        const dedupedEarnings = dedupeByTime(earningsPoints);
        earningsSeries.setData(dedupedEarnings);
        // Dot markers at each report date (strictly unique times)
        createSeriesMarkers(
          earningsSeries,
          dedupedEarnings.map((p) => ({
            time: p.time,
            position: "inBar" as const,
            color: "#16a34a",
            shape: "circle" as const,
            size: 0.6,
          })),
        );
      }
    }

    // 7. Series Markers: Anchor Dates & Quarterly Earnings Report Flags on Candlestick Series
    const markers: SeriesMarker<Time>[] = [];
    const screenDateFormatted = timeframe === "1W" ? getMondayIso(screenAsOfDate) : screenAsOfDate;
    const inspectedDateFormatted = timeframe === "1W" ? getMondayIso(inspectedDate) : inspectedDate;

    // Anchor: Screen Date (Gold)
    const validCandles = bars.filter((c) => !c.is_forecast && c.close !== null && c.close !== undefined);
    const screenCandle = validCandles.find((c) => c.time === screenDateFormatted) ||
      validCandles.filter((c) => c.time <= screenDateFormatted).pop();
    if (screenCandle) {
      markers.push({
        time: screenCandle.time as Time,
        position: "aboveBar",
        color: "#f59e0b",
        shape: "arrowDown",
        text: `📍 Screen (${screenAsOfDate})`,
        size: 1.3,
      });
    }

    // Anchor: Inspected Point (Emerald)
    const inspectedCandle = validCandles.find((c) => c.time === inspectedDateFormatted) ||
      validCandles.filter((c) => c.time <= inspectedDateFormatted).pop();
    if (inspectedCandle && inspectedCandle.time !== screenCandle?.time) {
      markers.push({
        time: inspectedCandle.time as Time,
        position: "aboveBar",
        color: "#10b981",
        shape: "arrowDown",
        text: `🔍 Inspected (${inspectedDate})`,
        size: 1.6,
      });
    }

    // Earnings flags: dedicated strip just above the volume pane (volume: 0.84 to 1.0; flags: 0.78 to 0.82)
    if (showEarningsFlags) {
      const usedTimes = new Set<string>();
      const flagPoints: LineData<Time>[] = [];
      const flagMarkers: SeriesMarker<Time>[] = [];

      // Combine earningsEvents and quarterlyGrowth into unified list
      const candidateEvents: { date: string; epsGrowth: number | null; surprisePct: number | null }[] = [];
      for (const ev of earningsEvents) {
        if (ev.date) {
          candidateEvents.push({
            date: ev.date,
            epsGrowth: ev.eps_growth_yoy ?? null,
            surprisePct: ev.surprise_pct ?? null,
          });
        }
      }
      for (const q of quarterlyGrowth) {
        if (q.report_date) {
          candidateEvents.push({
            date: q.report_date,
            epsGrowth: q.eps_growth_yoy ?? null,
            surprisePct: q.eps_surprise_pct ?? q.surprise_pct ?? null,
          });
        }
      }

      // If no events from either source, fall back to candle-flagged reports
      if (candidateEvents.length === 0) {
        for (const c of validCandles) {
          if (c.is_earnings_report) {
            candidateEvents.push({
              date: c.time,
              epsGrowth: c.earnings_growth_yoy ?? null,
              surprisePct: null,
            });
          }
        }
      }

      // When zoom is wide (ALL, 6Y, 5Y, or when bars count is high), drop text labels completely so they never overlap.
      // In closer views (2Y, 1Y, 6M, 3M), show compact percentage labels.
      const isWideZoom =
        activeRange === "ALL" ||
        activeRange === "6Y" ||
        activeRange === "5Y" ||
        (timeframe === "1W" ? bars.length > 70 : bars.length > 250);

      for (let idx = 0; idx < candidateEvents.length; idx++) {
        const ev = candidateEvents[idx];
        const mapped = chartTimeForDate(ev.date, timeframe);
        const candle = nearestCandle(mapped, validCandles);
        if (!candle || usedTimes.has(candle.time)) continue;
        usedTimes.add(candle.time);

        const growth = ev.epsGrowth;
        const surprise = ev.surprisePct;
        const pct = growth ?? surprise;

        const isPositive = pct != null && pct > 0;
        const isBig = pct != null && pct >= 10;
        const isNeg = pct != null && pct < 0;

        const markerColor = isBig ? "#10b981" : isNeg ? "#ef4444" : isPositive ? "#22c55e" : "#0284c7";
        const markerShape: SeriesMarker<Time>["shape"] = isPositive ? "arrowUp" : isNeg ? "arrowDown" : "circle";

        // Compact label: drop redundant "EPS " prefix to save horizontal space (e.g. "+429%", "-25%")
        // When zoomed out (6Y / ALL), only show text for major moves (|pct| >= 25%) or the latest 6 quarters to avoid collision
        // In wide zoom, text numbers go away completely, leaving clean non-overlapping arrows!
        let label = "";
        if (!isWideZoom && pct != null) {
          label = `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
        }

        flagPoints.push({ time: candle.time as Time, value: 1 });
        flagMarkers.push({
          time: candle.time as Time,
          position: "inBar" as const,
          color: markerColor,
          shape: markerShape,
          text: label,
          size: 0.6,
        });
      }

      if (flagPoints.length > 0) {
        // Phantom series pinned in the band right above volume
        const flagsSeries = chart.addSeries(LineSeries, {
          color: "rgba(0,0,0,0)",
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
          priceScaleId: "earnings_flags_axis",
          priceFormat: { type: "price", precision: 2, minMove: 0.01 },
        });
        chart.priceScale("earnings_flags_axis").applyOptions({
          visible: false,
          scaleMargins: { top: 0.73, bottom: 0.19 }, // centered at 0.77, right in the dedicated strip above volume (0.82)
        });
        flagsSeries.setData(dedupeByTime(flagPoints));
        flagMarkers.sort((a, b) => String(a.time).localeCompare(String(b.time)));
        createSeriesMarkers(flagsSeries, flagMarkers);
      }
    }

    // Apply anchor / inspected markers to candleSeries
    if (markers.length > 0) {
      const validTimeSet = new Set(candleData.map((d) => String(d.time)));
      const filteredMarkers = markers.filter((m) => validTimeSet.has(String(m.time)));
      filteredMarkers.sort((a, b) => String(a.time).localeCompare(String(b.time)));
      if (filteredMarkers.length > 0) {
        createSeriesMarkers(candleSeries, filteredMarkers);
      }
    }

    // 8. Crosshair Hover Listener
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || !param.point) {
        setHoveredCandle(null);
        return;
      }
      const match = bars.find((c) => c.time === param.time);
      if (match) {
        setHoveredCandle(match);
      } else {
        setHoveredCandle(null);
      }
    });

    // 9. Interactive Click Listener to Scrub Timeline
    chart.subscribeClick((param) => {
      if (param && param.time) {
        const clickedDate = String(param.time);
        onSelectDate(clickedDate);
      }
    });

    // 10. Load more only after the user pans past the left edge (from < 0).
    // from <= 10 fired on ALL/6Y fit, which requested unbounded 10k-day history
    // and blocked Django's single-threaded runserver so the page looked hung.
    // 10. Track visible logical range so user's zoom & pan position are preserved across data updates
    chart.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
      if (!logicalRange) return;
      lastLogicalRangeRef.current = logicalRange;
      if (logicalRange.from < 0 && hasMoreHistory && !isLoadingMoreHistory) {
        onLoadMoreHistory?.();
      }
    });

    // Apply active range
    applyRangeToChart(chart, activeRange, bars);
    // If the user already had an active zoom/position (or panned/zoomed before this re-render),
    // preserve that exact visible logical range so the chart NEVER snaps or jumps when data renders.
    if (lastLogicalRangeRef.current) {
      try {
        chart.timeScale().setVisibleLogicalRange(lastLogicalRangeRef.current);
      } catch {
        applyRangeToChart(chart, activeRange, bars);
      }
    } else {
      applyRangeToChart(chart, activeRange, bars);
    }

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0].contentRect) return;
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartApiRef.current = null;
    };
  }, [
    processedCandles,
    screenAsOfDate,
    inspectedDate,
    revealFuture,
    showRsLine,
    showEpsLine,
    showFairValueRibbon,
    showValuationCorridor,
    showExpectationTracks,
    showMultipleRibbon,
    showEarningsFlags,
    showEarningsLine,
    showSpxOverlay,
    showForecast,
    show10Ema,
    show21Ema,
    show50Sma,
    show200Sma,
    timeframe,
    isLogScale,
    historicalMedianPe,
    onSelectDate,
    activeRange,
    earningsEvents,
    quarterlyGrowth,
  ]);

  // Handle Range Preset Click with on-demand historical loading
  const handleRangePreset = async (r: ChartRangePreset) => {
    patchActiveBag({ range: r });
    lastLogicalRangeRef.current = null; // Clear preserved zoom so requested preset takes effect
    if ((r === "ALL" || r === "5Y") && hasMoreHistory && !isLoadingMoreHistory) {
      if (onLoadMoreHistory) {
        await onLoadMoreHistory();
      }
    }
    if (chartApiRef.current) {
      applyRangeToChart(chartApiRef.current, r, processedCandles);
    }
  };// Step helper
  const handleStepBars = (step: number) => {
    const newIdx = Math.max(0, Math.min(processedCandles.length - 1, inspectedIndex + step));
    if (newIdx !== inspectedIndex && processedCandles[newIdx]) {
      onSelectDate(processedCandles[newIdx].time);
    }
  };

  const isAtScreenDate = inspectedDate === screenAsOfDate;

  // Filter quarterly earnings ribbon items (ordered chronologically, past to future)
  const ribbonQuarters = useMemo(() => {
    if (quarterlyGrowth.length === 0) return [];
    return [...quarterlyGrowth].sort((a, b) => {
      const ae = a.is_estimate ? 1 : 0;
      const be = b.is_estimate ? 1 : 0;
      if (ae !== be) return ae - be;
      return (a.report_date || "").localeCompare(b.report_date || "");
    });
  }, [quarterlyGrowth]);

  return (
    <div className={cn("flex flex-col h-full w-full rounded-lg border border-line bg-surface overflow-hidden", className)}>
      {/* Chart Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-1.5 bg-surface-raised text-[11px]">
        {/* Active Stats */}
        <div className="flex items-center gap-3">
          {activeCandle && (
            <div className="flex items-center gap-2 font-mono text-[10.5px]">
              <span className={cn("font-bold px-1.5 py-0.5 rounded border", isAtScreenDate ? "bg-amber-500/15 border-amber-500/40 text-amber-500" : "bg-emerald-500/15 border-emerald-500/40 text-emerald-500")}>
                {isAtScreenDate ? `📍 ${activeCandle.time}` : `🔍 ${activeCandle.time}`}
              </span>
              <span className="text-ink">
                <strong className="text-ink-muted">O: </strong>${typeof activeCandle.open === "number" ? activeCandle.open.toFixed(2) : "—"}
              </span>
              <span className="text-ink">
                <strong className="text-ink-muted">H: </strong>${typeof activeCandle.high === "number" ? activeCandle.high.toFixed(2) : "—"}
              </span>
              <span className="text-ink">
                <strong className="text-ink-muted">L: </strong>${typeof activeCandle.low === "number" ? activeCandle.low.toFixed(2) : "—"}
              </span>
              <span className={cn("font-bold", typeof activeCandle.close === "number" && typeof activeCandle.open === "number" && activeCandle.close >= activeCandle.open ? "text-emerald-500" : "text-rose-500")}>
                <strong className="text-ink-muted font-normal">C: </strong>${typeof activeCandle.close === "number" ? activeCandle.close.toFixed(2) : "—"}
              </span>
              <span className="text-ink-muted hidden xl:inline">
                Vol: {typeof activeCandle.volume === "number" ? `${(activeCandle.volume / 1e6).toFixed(2)}M` : "—"}
              </span>
              {typeof activeCandle.rs_rating === "number" && (
                <span className="text-sky-400 font-bold hidden sm:inline" title="MarketSurge RS Rating / Ratio">
                  RS: {activeCandle.rs_rating.toFixed(0)}
                  {typeof activeCandle.rs_line === "number" && <span className="text-ink-muted font-normal text-[9.5px] ml-1">({activeCandle.rs_line.toFixed(1)})</span>}
                </span>
              )}
              {typeof activeCandle.eps_trailing_12m === "number" && (
                <span className="text-emerald-400 font-bold hidden lg:inline" title="Trailing 12-Month EPS">
                  EPS (TTM): ${activeCandle.eps_trailing_12m.toFixed(2)}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Controls Strip: Timeframe & Indicators & Blind Mode */}
        <div className="flex items-center gap-2">
          {/* Timeframe Switcher */}
          <div className="inline-flex rounded border border-line bg-surface p-0.5 font-mono text-[10px]">
            <button
              type="button"
              onClick={() => setTimeframe("1D")}
              className={cn(
                "rounded px-2 py-0.5 font-bold transition-colors",
                timeframe === "1D" ? "bg-accent text-accent-ink shadow-xs" : "text-ink-muted hover:text-ink"
              )}
            >
              1D
            </button>
            <button
              type="button"
              onClick={() => setTimeframe("1W")}
              className={cn(
                "rounded px-2 py-0.5 font-bold transition-colors",
                timeframe === "1W" ? "bg-accent text-accent-ink shadow-xs" : "text-ink-muted hover:text-ink"
              )}
            >
              1W
            </button>
          </div>

          {/* Logarithmic / Linear Scale Toggle */}
          <button
            type="button"
            onClick={() => setIsLogScale((p) => !p)}
            className={cn(
              "rounded px-2 py-0.5 border font-mono text-[10px] font-bold transition-all",
              isLogScale
                ? "border-purple-500/50 bg-purple-500/15 text-purple-400 shadow-xs"
                : "border-line bg-surface text-ink-muted hover:text-ink"
            )}
            title={isLogScale ? "Switch to Linear Scale (LIN)" : "Switch to Logarithmic Scale (LOG)"}
          >
            {isLogScale ? "LOG" : "LIN"}
          </button>

          {/* Range Jump Selector & Lazy Loading Indicator */}
          <div className="flex items-center gap-2">
            {isLoadingMoreHistory && (
              <span className="text-[10px] text-accent animate-pulse font-mono flex items-center gap-1">
                <span>⏳</span> Loading historical depth…
              </span>
            )}
            <div className="hidden sm:inline-flex items-center rounded border border-line bg-surface p-0.5 font-mono text-[9.5px]">
              {(["3M", "6M", "1Y", "2Y", "6Y", "ALL"] as ChartRangePreset[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => handleRangePreset(r)}
                  className={cn(
                    "rounded px-1.5 py-0.5 font-semibold transition-colors",
                    activeRange === r ? "bg-surface-sunk text-accent font-bold" : "text-ink-muted hover:text-ink"
                  )}
                  title={r === "6Y" ? "4 Years History + 2 Years Forecast (FAST Graphs Perspective)" : undefined}
                >
                  {r === "6Y" ? "6Y (4+2)" : r}
                </button>
              ))}
              <button
                type="button"
                onClick={handleResetView}
                className="ml-1 rounded border-l border-line pl-1.5 pr-1 py-0.5 font-bold text-accent hover:bg-accent/15 transition-colors"
                title="Reset view to sensible 2Y default (or right-click chart)"
              >
                🔄 Reset
              </button>
            </div>

            {/* Chart Height Slider */}
            <div className="hidden md:flex items-center gap-1.5 rounded border border-line bg-surface px-2 py-0.5 font-mono text-[9px] text-ink-muted">
              <span title="Adjust chart vertical canvas height">Height:</span>
              <input
                type="range"
                min={340}
                max={750}
                step={20}
                value={chartHeight}
                onChange={(e) => handleChartHeightChange(Number(e.target.value))}
                className="h-1.5 w-16 cursor-ew-resize accent-accent"
                title={`Chart canvas height: ${chartHeight}px`}
              />
              <span className="w-8 text-right font-bold text-ink">{chartHeight}px</span>
            </div>
          </div>

          <div className="relative">
            <button
              ref={indicatorButtonRef}
              type="button"
              onClick={() => setIndicatorMenuOpen((open) => !open)}
              className={cn(
                "inline-flex items-center gap-2 rounded border px-2 py-1 text-[10px] font-mono font-bold transition-all",
                indicatorMenuOpen
                  ? "border-accent/60 bg-accent/15 text-accent"
                  : "border-line bg-surface text-ink-muted hover:border-accent hover:text-ink"
              )}
              title="Indicator settings"
            >
              <span>Indicators</span>
              <span className={cn(
                "inline-flex min-w-[1.25rem] items-center justify-center rounded-full border px-1 text-[9px] font-bold",
                indicatorMenuOpen ? "border-accent/60 bg-accent/20 text-accent" : "border-line bg-surface-sunk text-ink-muted"
              )}>{activeIndicatorCount}</span>
            </button>

            {indicatorMenuOpen && (
              <div
                ref={indicatorMenuRef}
                className="absolute right-0 z-50 mt-2 w-[min(360px,calc(100vw-1rem))] overflow-hidden rounded-xl border border-line bg-surface shadow-2xl shadow-slate-950/25"
              >
                <div className="border-b border-line bg-surface-raised px-2.5 py-2">
                  <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-ink">
                    {timeframe === "1W" ? "Weekly studies" : "Daily studies"}
                  </div>
                  <input
                    value={indicatorSearch}
                    onChange={(event) => setIndicatorSearch(event.target.value)}
                    placeholder="Search indicators..."
                    className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[11px] font-mono text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
                  />
                </div>

                <div className="max-h-[320px] overflow-y-auto p-2">
                  <div className="space-y-1">
                    {filteredIndicators.length === 0 ? (
                      <div className="px-2 py-3 text-[11px] text-ink-muted">No indicators match this search.</div>
                    ) : (
                      filteredIndicators.map((option) => {
                        const weeklyOnlyDisabled = Boolean(option.weeklyOnly && timeframe !== "1W");
                        const enabled = weeklyOnlyDisabled ? false : indicatorConfig[option.key];
                        const label = timeframe === "1W" ? (option.weeklyLabel ?? option.label) : option.label;
                        return (
                          <button
                            key={option.key}
                            type="button"
                            disabled={weeklyOnlyDisabled}
                            onClick={() => {
                              if (weeklyOnlyDisabled) return;
                              setIndicator(option.key, !enabled);
                              setIndicatorMenuOpen(true);
                            }}
                            className={cn(
                              "flex w-full items-center justify-between gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors",
                              weeklyOnlyDisabled
                                ? "cursor-not-allowed border-transparent bg-surface-sunk text-ink-muted opacity-70"
                                : enabled
                                ? "border-accent/40 bg-accent/10 text-ink"
                                : "border-transparent bg-surface hover:border-line hover:bg-surface-raised text-ink-muted"
                            )}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] font-bold text-ink">{label}</span>
                                <span className="rounded border border-line bg-surface-sunk px-1 py-0.5 text-[8.5px] uppercase tracking-wide text-ink-faint">
                                  {option.category}
                                </span>
                              </div>
                              <div className="mt-0.5 truncate text-[10px] text-ink-muted">
                                {weeklyOnlyDisabled ? "Weekly only" : option.description}
                              </div>
                            </div>
                            <span
                              className={cn(
                                "inline-flex h-4 w-4 items-center justify-center rounded border text-[9px] font-bold transition-all",
                                weeklyOnlyDisabled
                                  ? "border-line bg-surface-sunk text-ink-faint"
                                  : enabled
                                  ? "border-accent bg-accent text-white"
                                  : "border-line bg-surface text-ink-faint"
                              )}
                            >
                              {enabled ? "✓" : ""}
                            </span>
                          </button>
                        );
                      })
                    )}
                    <div className="flex w-full items-center justify-between gap-2 rounded-lg border border-dashed border-line px-2.5 py-2 text-left opacity-60">
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-bold text-ink-muted">Minervini Trend Template (later)</div>
                        <div className="mt-0.5 text-[10px] text-ink-muted">Not toggleable in this release</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Forecast Accuracy Button */}
          {onOpenForecastModal && (
            <button
              type="button"
              onClick={onOpenForecastModal}
              className="inline-flex items-center gap-1 rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-bold text-accent hover:bg-accent/20 transition-all"
              title="Open TradingView-style forecast accuracy analysis"
            >
              <span>📊 Accuracy</span>
            </button>
          )}

          {/* Reveal Future / Blind Mode Toggle */}
          {onToggleRevealFuture && (
            <button
              type="button"
              onClick={() => onToggleRevealFuture(!revealFuture)}
              className={cn(
                "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-bold transition-all",
                revealFuture
                  ? "border-accent/60 bg-accent/15 text-accent"
                  : "border-line bg-surface text-ink-muted hover:border-accent hover:text-ink"
              )}
              title={
                revealFuture
                  ? "Click to hide future candles (Blind flashcard study mode)"
                  : "Click to reveal forward-walk outcome"
              }
            >
              <span>{revealFuture ? "👁 Outcome Revealed" : "🙈 Blind Test Mode"}</span>
            </button>
          )}
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div
        className="relative w-full"
        style={{ height: `${chartHeight}px`, minHeight: "340px" }}
        ref={chartContainerRef}
        onMouseLeave={() => setHoveredCandle(null)}
        onContextMenu={(e) => {
          e.preventDefault();
          handleResetView();
        }}
        onDoubleClick={handleResetView}
        title="Double-click or right-click to reset view to 2Y default"
      />

      {/* Bottom quarterly table: last 8 reported + 2 estimates */}
      {ribbonQuarters.length > 0 && (
        <div className="overflow-x-auto border-t border-line bg-surface px-2 py-1 font-mono text-[10px]">
          <table className="w-full min-w-[560px] text-left">
            <thead className="text-[8.5px] uppercase text-ink-muted">
              <tr>
                <th className="py-0.5 pr-2 font-bold">
                  <div className="flex items-center gap-1.5">
                    <span>Quarter</span>
                    {onOpenForecastModal && (
                      <button
                        type="button"
                        onClick={onOpenForecastModal}
                        className="rounded border border-accent/40 bg-accent/10 px-1 py-0.2 text-[8px] font-bold text-accent hover:bg-accent/20 transition-colors"
                        title="View TradingView Forecasts & Accuracy Chart"
                      >
                        📊 Accuracy
                      </button>
                    )}
                  </div>
                </th>
                {ribbonQuarters.map((q, idx) => (
                  <th
                    key={`${q.report_date}-${idx}`}
                    className={cn(
                      "cursor-pointer px-1.5 py-0.5 text-right font-bold",
                      q.is_estimate ? "text-sky-400" : "text-ink",
                    )}
                    onClick={() => q.report_date && onSelectDate(q.report_date)}
                  >
                    {q.report_date ? q.report_date.slice(2, 7) : "—"}
                    {q.is_estimate ? " est" : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* EPS Actual / Reported */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted font-bold">EPS Act</td>
                {ribbonQuarters.map((q, idx) => {
                  const act = q.eps_actual ?? (!q.is_estimate ? q.eps : null);
                  return (
                    <td key={`eps-act-${idx}`} className="px-1.5 text-right font-bold text-ink">
                      {act != null ? act.toFixed(2) : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* EPS Estimate */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted">EPS Est</td>
                {ribbonQuarters.map((q, idx) => {
                  const est = q.eps_estimate ?? (q.is_estimate ? q.eps : null);
                  return (
                    <td key={`eps-est-${idx}`} className="px-1.5 text-right text-ink-muted">
                      {est != null ? est.toFixed(2) : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* EPS Surprise */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted">Surprise</td>
                {ribbonQuarters.map((q, idx) => {
                  if (q.is_estimate) {
                    return (
                      <td key={`eps-surp-${idx}`} className="px-1.5 text-right text-[9px] text-ink-faint">
                        —
                      </td>
                    );
                  }
                  const bm = q.eps_beat_miss;
                  const pct = q.eps_surprise_pct;
                  return (
                    <td
                      key={`eps-surp-${idx}`}
                      className={cn(
                        "px-1.5 text-right font-bold text-[9px]",
                        bm === "beat" || (pct != null && pct > 0)
                          ? "text-emerald-500"
                          : bm === "miss" || (pct != null && pct < 0)
                          ? "text-rose-500"
                          : "text-ink-muted",
                      )}
                    >
                      {bm === "beat"
                        ? `Beat${pct != null ? ` (+${pct.toFixed(0)}%)` : ""}`
                        : bm === "miss"
                        ? `Miss${pct != null ? ` (${pct.toFixed(0)}%)` : ""}`
                        : pct != null
                        ? `${pct > 0 ? "+" : ""}${pct.toFixed(0)}%`
                        : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* EPS YoY Growth */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted">%Chg (YoY)</td>
                {ribbonQuarters.map((q, idx) => {
                  const g = q.eps_growth_yoy;
                  return (
                    <td
                      key={`epschg-${idx}`}
                      className={cn(
                        "px-1.5 text-right font-bold",
                        g != null && g > 0 ? "text-emerald-500" : g != null && g < 0 ? "text-rose-500" : "text-ink",
                      )}
                    >
                      {g != null ? `${g > 0 ? "+" : ""}${g.toFixed(0)}%` : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* Sales Actual */}
              <tr className="border-t border-line/50">
                <td className="py-0.5 pr-2 text-ink-muted font-bold">Sales Act</td>
                {ribbonQuarters.map((q, idx) => {
                  const act = q.revenue_actual ?? (!q.is_estimate ? q.revenue_m : null);
                  return (
                    <td key={`sales-act-${idx}`} className="px-1.5 text-right font-bold text-ink">
                      {act != null ? act.toFixed(0) : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* Sales Estimate */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted">Sales Est</td>
                {ribbonQuarters.map((q, idx) => {
                  const est = q.revenue_estimate ?? (q.is_estimate ? q.revenue_m : null);
                  return (
                    <td key={`sales-est-${idx}`} className="px-1.5 text-right text-ink-muted">
                      {est != null ? est.toFixed(0) : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* Sales Surprise */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted">Surprise</td>
                {ribbonQuarters.map((q, idx) => {
                  if (q.is_estimate) {
                    return (
                      <td key={`sales-surp-${idx}`} className="px-1.5 text-right text-[9px] text-ink-faint">
                        —
                      </td>
                    );
                  }
                  const bm = q.revenue_beat_miss;
                  const pct = q.revenue_surprise_pct;
                  return (
                    <td
                      key={`sales-surp-${idx}`}
                      className={cn(
                        "px-1.5 text-right font-bold text-[9px]",
                        bm === "beat" || (pct != null && pct > 0)
                          ? "text-emerald-500"
                          : bm === "miss" || (pct != null && pct < 0)
                          ? "text-rose-500"
                          : "text-ink-muted",
                      )}
                    >
                      {bm === "beat"
                        ? `Beat${pct != null ? ` (+${pct.toFixed(0)}%)` : ""}`
                        : bm === "miss"
                        ? `Miss${pct != null ? ` (${pct.toFixed(0)}%)` : ""}`
                        : pct != null
                        ? `${pct > 0 ? "+" : ""}${pct.toFixed(0)}%`
                        : "—"}
                    </td>
                  );
                })}
              </tr>
              {/* Sales YoY Growth */}
              <tr>
                <td className="py-0.5 pr-2 text-ink-muted">%Chg (YoY)</td>
                {ribbonQuarters.map((q, idx) => {
                  const g = q.revenue_growth_yoy;
                  return (
                    <td
                      key={`saleschg-${idx}`}
                      className={cn(
                        "px-1.5 text-right font-bold",
                        g != null && g > 0 ? "text-emerald-500" : g != null && g < 0 ? "text-rose-500" : "text-ink",
                      )}
                    >
                      {g != null ? `${g > 0 ? "+" : ""}${g.toFixed(0)}%` : "—"}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Interactive Time Travel Scrubber Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-surface-raised px-3 py-1.5 text-[11px]">
        {/* Navigation Step Buttons */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => handleStepBars(-20)}
            className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-accent hover:text-ink transition-colors"
            title="Step back 20 bars (~1 month)"
          >
            ◀◀ -20
          </button>
          <button
            type="button"
            onClick={() => handleStepBars(-5)}
            className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-accent hover:text-ink transition-colors"
            title="Step back 5 bars (~1 week)"
          >
            ◀ -5
          </button>
          <button
            type="button"
            onClick={() => handleStepBars(-1)}
            className="rounded border border-line bg-surface px-2 py-0.5 font-mono text-[10px] font-bold text-ink hover:border-accent hover:text-accent transition-colors"
            title="Step back 1 bar (-1D / -1W)"
          >
            ◀ -1 Bar
          </button>

          {/* Auto Replay Toggle */}
          <button
            type="button"
            onClick={() => setIsPlayingReplay(!isPlayingReplay)}
            className={cn(
              "rounded border px-2 py-0.5 font-mono text-[10px] font-bold transition-all",
              isPlayingReplay
                ? "border-emerald-500 bg-emerald-500/20 text-emerald-500 animate-pulse"
                : "border-line bg-surface text-ink hover:border-accent"
            )}
            title={isPlayingReplay ? "Pause Replay" : "Play Bar-by-Bar Replay (1 bar / 600ms)"}
          >
            {isPlayingReplay ? "⏸ Pause" : "▶ Replay"}
          </button>

          <button
            type="button"
            onClick={() => handleStepBars(1)}
            className="rounded border border-line bg-surface px-2 py-0.5 font-mono text-[10px] font-bold text-ink hover:border-accent hover:text-accent transition-colors"
            title="Step forward 1 bar (+1D / +1W)"
          >
            +1 Bar ▶
          </button>
          <button
            type="button"
            onClick={() => handleStepBars(5)}
            className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-accent hover:text-ink transition-colors"
            title="Step forward 5 bars (~1 week)"
          >
            +5 ▶
          </button>
          <button
            type="button"
            onClick={() => handleStepBars(20)}
            className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-accent hover:text-ink transition-colors"
            title="Step forward 20 bars (~1 month)"
          >
            +20 ▶▶
          </button>
        </div>

        {/* Timeline Slider Track */}
        <div className="flex flex-1 items-center gap-2 max-w-[280px] sm:max-w-[400px]">
          <input
            type="range"
            min={0}
            max={Math.max(0, processedCandles.length - 1)}
            value={inspectedIndex}
            onChange={(e) => {
              const idx = Number(e.target.value);
              if (processedCandles[idx]) {
                onSelectDate(processedCandles[idx].time);
              }
            }}
            className="w-full h-1.5 bg-surface-sunk rounded-lg appearance-none cursor-pointer accent-emerald-500"
            title="Scrub timeline across stock history"
          />
          <span className="font-mono text-[10px] text-ink-muted whitespace-nowrap">
            {inspectedIndex + 1}/{processedCandles.length}
          </span>
        </div>

        {/* Quick Reset & Latest Jumps */}
        <div className="flex items-center gap-1.5">
          {!isAtScreenDate && (
            <button
              type="button"
              onClick={() => onSelectDate(screenAsOfDate)}
              className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-500 hover:bg-amber-500/20 transition-colors"
              title={`Jump back to original screen date (${screenAsOfDate})`}
            >
              📍 Reset to Screen Date
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              if (processedCandles.length > 0) {
                onSelectDate(processedCandles[processedCandles.length - 1].time);
              }
            }}
            className="rounded border border-line bg-surface px-2 py-0.5 font-mono text-[10px] font-bold text-ink hover:border-accent hover:text-accent transition-colors"
            title="Jump to latest trading bar"
          >
            ⚡ Latest
          </button>
        </div>
      </div>
    </div>
  );
}
