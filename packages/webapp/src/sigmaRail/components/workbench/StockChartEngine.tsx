import { useEffect, useRef, useState, useMemo } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  PriceScaleMode,
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
import { fetchChartPreferences, saveChartPreferences } from "../../api/preferences";
import {
  DEFAULTS as DEFAULT_CHART_SETTINGS,
  getTfBag,
  loadAccountChartSettings,
  normalizeChartPaneLayout,
  saveAccountChartSettings,
  setTfBag,
  type ChartIndicatorKey,
  type ChartRangePreset,
  type ChartSettingsV2,
  type ChartTimeframe,
} from "../../lib/chartSettings";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import { Slider } from "@sb/webapp-core/components/ui/slider";
import { useTheme } from "@sb/webapp-core/hooks/useTheme";
import { Themes } from "@sb/webapp-core/providers/themeProvider";

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

/** Price, relative strength and volume use separate panes and scales. */
const PRICE_PANE_MARGINS = { top: 0.05, bottom: 0.04 } as const;

const INDICATOR_OPTIONS: IndicatorOption[] = [
  { key: "rsLine", label: "RS Line", category: "Trend", description: "Relative strength vs SPY in its own pane" },
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

function persistSettings(next: ChartSettingsV2, userId: string | null): ChartSettingsV2 {
  if (userId) saveAccountChartSettings(userId, next);
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

const CHART_HEIGHT_STORAGE_KEY = "sigmarail.chart.canvas-height.v1";
const LEGACY_CHART_HEIGHT_STORAGE_KEY = "vera_chart_canvas_height";
function loadSavedChartHeight(): number {
  try {
    let val = localStorage.getItem(CHART_HEIGHT_STORAGE_KEY);
    if (val === null) {
      val = localStorage.getItem(LEGACY_CHART_HEIGHT_STORAGE_KEY);
      if (val !== null) {
        localStorage.setItem(CHART_HEIGHT_STORAGE_KEY, val);
        localStorage.removeItem(LEGACY_CHART_HEIGHT_STORAGE_KEY);
      }
    }
    if (val) {
      const num = parseInt(val, 10);
      if (num >= 320 && num <= 850) return num;
    }
  } catch {}
  return 480; // Sensible default provides ample room for candles, flags, and volume
}

function withLegacyChartSettings(settings: ChartSettingsV2): ChartSettingsV2 {
  const saved = settings as Partial<ChartSettingsV2>;
  return {
    ...DEFAULT_CHART_SETTINGS,
    ...settings,
    paneLayout: normalizeChartPaneLayout(saved.paneLayout),
    chartHeight:
      typeof saved.chartHeight === "number" && Number.isFinite(saved.chartHeight)
        ? Math.max(320, Math.min(850, Math.round(saved.chartHeight)))
        : loadSavedChartHeight(),
    isLogScale: typeof saved.isLogScale === "boolean" ? saved.isLogScale : false,
  };
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
  className,
}: StockChartEngineProps) {
  const { theme } = useTheme();
  const isDarkTheme = theme === Themes.DARK;
  const chartColors = useMemo(() => {
    return isDarkTheme
      ? {
          background: "#0a0a0a",
          text: "#a3a3a3",
          border: "#262626",
          grid: "rgba(148, 163, 184, 0.12)",
        }
      : {
          background: "#ffffff",
          text: "#737373",
          border: "#e5e5e5",
          grid: "rgba(100, 116, 139, 0.14)",
        };
  }, [isDarkTheme]);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const lastLogicalRangeRef = useRef<LogicalRange | null>(null);
  const prevTickerRef = useRef<string | undefined>(ticker);
  const profileUserIdRef = useRef<string | null>(null);

  const [settings, setSettings] = useState<ChartSettingsV2>(DEFAULT_CHART_SETTINGS);
  const paneLayoutRef = useRef(settings.paneLayout);
  paneLayoutRef.current = settings.paneLayout;
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const timeframe = settings.lastTimeframe;
  const prevTimeframeRef = useRef<ChartTimeframe>(timeframe);
  const bag = getTfBag(settings, timeframe);
  const indicatorConfig = bag.indicators;
  const activeRange = bag.range;

  useEffect(() => {
    let active = true;
    void fetchChartPreferences()
      .then(({ userId, settings: serverSettings, configured }) => {
        if (!active) return;
        profileUserIdRef.current = userId;
        if (!userId) {
          setSettings(DEFAULT_CHART_SETTINGS);
        } else if (configured && serverSettings) {
          setSettings(persistSettings(withLegacyChartSettings(serverSettings), userId));
        } else {
          // First-run migration: import this user's scoped browser preferences into the profile.
          const accountSettings = withLegacyChartSettings(loadAccountChartSettings(userId));
          setSettings(persistSettings(accountSettings, userId));
          void saveChartPreferences(accountSettings).catch(() => {});
        }
      })
      .catch(() => {
        // Wait for the signed-in profile before loading any account-scoped values.
        if (active) setSettings(DEFAULT_CHART_SETTINGS);
      })
      .finally(() => {
        if (active) setSettingsLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!settingsLoaded) return;
    if (!profileUserIdRef.current) return;
    const timer = window.setTimeout(() => {
      void saveChartPreferences(settings).catch(() => {
        // Local storage remains the offline fallback.
      });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [settings, settingsLoaded]);

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

  const isLogScale = settings.isLogScale;
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
        profileUserIdRef.current,
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
        profileUserIdRef.current,
      );
    });
  };

  const setTimeframe = (tf: ChartTimeframe) => {
    setSettings((prev) => persistSettings({ ...prev, lastTimeframe: tf }, profileUserIdRef.current));
  };

  const showRsLine = indicatorConfig.rsLine;
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
    if (key === "earningsLine") return false;
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

  const chartHeight = settings.chartHeight;
  const [isCompactViewport, setIsCompactViewport] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches,
  );
  const [viewportHeight, setViewportHeight] = useState(() =>
    typeof window !== "undefined" ? window.innerHeight : 900,
  );
  // Keep all panes inside the visible chart workspace even when a larger saved
  // height is preferred by the user.
  const availableChartHeight = Math.max(
    isCompactViewport ? 280 : 340,
    viewportHeight - (isCompactViewport ? 220 : 160),
  );
  const renderedChartHeight = Math.min(
    chartHeight,
    availableChartHeight,
    isCompactViewport ? 420 : Number.MAX_SAFE_INTEGER,
  );

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const syncViewport = () => {
      setIsCompactViewport(media.matches);
      setViewportHeight(window.innerHeight);
    };
    syncViewport();
    media.addEventListener("change", syncViewport);
    window.addEventListener("resize", syncViewport);
    return () => {
      media.removeEventListener("change", syncViewport);
      window.removeEventListener("resize", syncViewport);
    };
  }, []);

  const handleChartHeightChange = (newHeight: number) => {
    setSettings((previous) =>
      persistSettings({ ...previous, chartHeight: newHeight }, profileUserIdRef.current),
    );
  };

  const handleScaleChange = (logScale: boolean) => {
    setSettings((previous) =>
      persistSettings({ ...previous, isLogScale: logScale }, profileUserIdRef.current),
    );
  };

  const handleResetChartDefaults = () => {
    lastLogicalRangeRef.current = null;
    setSettings(persistSettings({ ...DEFAULT_CHART_SETTINGS }, profileUserIdRef.current));
  };


  const [hoveredCandle, setHoveredCandle] = useState<ChartCandlePoint | null>(null);

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
    const defaultRange: ChartRangePreset = timeframe === "1D" ? "1Y" : "2Y";
    if (chartApiRef.current) {
      applyRangeToChart(chartApiRef.current, defaultRange, processedCandles);
      chartApiRef.current.priceScale("right").applyOptions({ autoScale: true });
      patchActiveBag({ range: defaultRange });
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

  // Apply Range Preset to TimeScale
  // Apply range presets to observed bars. Forecast dates must not move the
  // latest actual session away from the right edge on initial load.
  const applyRangeToChart = (chart: IChartApi, range: ChartRangePreset, candlesList: ChartCandlePoint[]) => {
    if (candlesList.length === 0) return;
    const visibleBars = candlesList.filter((c) => !c.is_forecast && c.close !== null && c.close !== undefined);
    if (visibleBars.length === 0) return;

    const totalBars = visibleBars.length;
    const lastBarIdx = totalBars - 1;
    const PADDING_BARS = 5;

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

    const lastCandle = visibleBars[lastBarIdx];
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

    const foundFromIdx = visibleBars.findIndex((c) => c.time >= targetFromDate);
    const fromIdx = foundFromIdx < 0 ? 0 : foundFromIdx;

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
    const height = Math.max(container.clientHeight || renderedChartHeight, 260);

    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: chartColors.background },
        textColor: chartColors.text,
        fontSize: 10,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      },
      grid: {
        vertLines: { color: chartColors.grid },
        horzLines: { color: chartColors.grid },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: "rgba(59, 130, 246, 0.55)", width: 1, style: 1 },
        horzLine: { color: "rgba(59, 130, 246, 0.4)", width: 1, style: 1 },
      },
      timeScale: {
        borderColor: chartColors.border,
        timeVisible: false,
        secondsVisible: false,
        rightOffset: 0,
        barSpacing: 8,
      },
      rightPriceScale: {
        borderColor: chartColors.border,
        autoScale: true,
        textColor: chartColors.text,
        mode: isLogScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
        scaleMargins: { ...PRICE_PANE_MARGINS },
      },
    });

    chartApiRef.current = chart;

    // Price, RS and volume share the time axis but keep independent scales.
    // Saved proportions are profile-wide, so they follow each ticker.
    const paneLayout = normalizeChartPaneLayout(paneLayoutRef.current);
    const visiblePriceRatio = showRsLine
      ? paneLayout.price
      : paneLayout.price / (paneLayout.price + paneLayout.volume);
    const visibleRsRatio = showRsLine ? paneLayout.rs : 0;
    const visibleVolumeRatio = showRsLine
      ? paneLayout.volume
      : paneLayout.volume / (paneLayout.price + paneLayout.volume);
    chart.panes()[0]?.setStretchFactor(visiblePriceRatio);
    const rsPaneIndex = showRsLine ? 1 : -1;
    if (showRsLine) {
      chart.addPane();
      chart.panes()[rsPaneIndex]?.setStretchFactor(visibleRsRatio);
    }
    const volumePaneIndex = showRsLine ? 2 : 1;
    chart.addPane();
    chart.panes()[volumePaneIndex]?.setStretchFactor(visibleVolumeRatio);

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
    }, volumePaneIndex);

    chart.priceScale("volume_pane", volumePaneIndex).applyOptions({
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

    // 5. Relative strength has its own pane and scale below price.
    if (showRsLine) {
      const rsLineSeries = chart.addSeries(LineSeries, {
        color: "#0284c7",
        lineWidth: 2,
        title: "RS",
        priceScaleId: "right",
        priceLineVisible: false,
      }, rsPaneIndex);

      const rsEmaSeries = chart.addSeries(LineSeries, {
        color: "rgba(56, 189, 248, 0.6)", // Cyan 21 EMA
        lineWidth: 1,
        title: "RS21",
        priceScaleId: "right",
        priceLineVisible: false,
      }, rsPaneIndex);

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

    // Lightweight Charts exposes its pane separators for direct resizing.
    // Persist the resulting proportions to the profile so the layout follows
    // the user when they inspect another symbol.
    let paneLayoutTimer: number | null = null;
    const paneObserver = new ResizeObserver(() => {
      const panes = chart.panes();
      const heights = panes.map((pane) => pane.getHeight());
      if (heights.length !== (showRsLine ? 3 : 2) || heights.some((value) => value <= 0)) return;
      if (paneLayoutTimer !== null) window.clearTimeout(paneLayoutTimer);
      paneLayoutTimer = window.setTimeout(() => {
        const total = heights.reduce((sum, value) => sum + value, 0);
        if (total <= 0) return;
        const nextVisible = {
          price: heights[0] / total,
          rs: showRsLine ? heights[1] / total : 0,
          volume: heights[showRsLine ? 2 : 1] / total,
        };
        setSettings((previous) => {
          const previousLayout = normalizeChartPaneLayout(previous.paneLayout);
          const nextLayout = showRsLine
            ? normalizeChartPaneLayout(nextVisible)
            : normalizeChartPaneLayout({
                price: nextVisible.price * (1 - previousLayout.rs),
                rs: previousLayout.rs,
                volume: nextVisible.volume * (1 - previousLayout.rs),
              });
          if (
            Math.abs(previousLayout.price - nextLayout.price) < 0.015 &&
            Math.abs(previousLayout.rs - nextLayout.rs) < 0.015 &&
            Math.abs(previousLayout.volume - nextLayout.volume) < 0.015
          ) return previous;
          return persistSettings({ ...previous, paneLayout: nextLayout }, profileUserIdRef.current);
        });
      }, 350);
    });
    chart.panes().forEach((pane) => {
      const element = pane.getHTMLElement();
      if (element) paneObserver.observe(element);
    });

    return () => {
      resizeObserver.disconnect();
      paneObserver.disconnect();
      if (paneLayoutTimer !== null) window.clearTimeout(paneLayoutTimer);
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
    showSpxOverlay,
    showForecast,
    show10Ema,
    show21Ema,
    show50Sma,
    show200Sma,
    timeframe,
    isLogScale,
    chartColors,
    historicalMedianPe,
    onSelectDate,
    activeRange,
    earningsEvents,
    quarterlyGrowth,
    settingsLoaded,
  ]);

  // Handle range preset selection with on-demand historical loading
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
  };

  const isAtScreenDate = inspectedDate === screenAsOfDate;
  const activeCandleIsForecast = activeCandle?.is_forecast === true;


  return (
    <div data-testid="stock-chart-engine" className={cn("flex flex-col h-full w-full rounded-lg border border-line bg-surface overflow-hidden", className)}>
      {/* Chart Top Toolbar */}
      <div data-testid="stock-chart-toolbar" className="flex min-w-0 flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/30 px-2 py-2 text-[11px] sm:px-3">
        {/* Active Stats */}
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {activeCandle && (
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] sm:gap-x-2.5 sm:text-[10.5px]">
              <span className={cn("whitespace-nowrap rounded border px-1.5 py-0.5 font-semibold", activeCandleIsForecast ? "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300" : isAtScreenDate ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300" : "border-border bg-background text-muted-foreground")}>
                {activeCandleIsForecast ? "Forecast" : isAtScreenDate ? "Screen date" : "Inspected"} · {activeCandle.time}
              </span>
              {activeCandleIsForecast ? (
                <span className="whitespace-nowrap text-muted-foreground">No traded OHLC or volume</span>
              ) : (
                <>
                  <span className="whitespace-nowrap text-foreground">
                    <strong className="text-ink-muted">O: </strong>${typeof activeCandle.open === "number" ? activeCandle.open.toFixed(2) : "—"}
                  </span>
                  <span className="whitespace-nowrap text-foreground">
                    <strong className="text-ink-muted">H: </strong>${typeof activeCandle.high === "number" ? activeCandle.high.toFixed(2) : "—"}
                  </span>
                  <span className="whitespace-nowrap text-foreground">
                    <strong className="text-ink-muted">L: </strong>${typeof activeCandle.low === "number" ? activeCandle.low.toFixed(2) : "—"}
                  </span>
                  <span className={cn("whitespace-nowrap font-semibold", typeof activeCandle.close === "number" && typeof activeCandle.open === "number" && activeCandle.close >= activeCandle.open ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400")}>
                    <strong className="text-ink-muted font-normal">C: </strong>${typeof activeCandle.close === "number" ? activeCandle.close.toFixed(2) : "—"}
                  </span>
                  <span className="text-ink-muted hidden xl:inline">
                    Vol: {typeof activeCandle.volume === "number" ? `${(activeCandle.volume / 1e6).toFixed(2)}M` : "—"}
                  </span>
                </>
              )}
              {typeof activeCandle.rs_rating === "number" && (
                <span className="text-sky-400 font-bold hidden sm:inline" title="Relative strength rating / ratio">
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
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          {/* Timeframe Switcher */}
          <div className="inline-flex items-center rounded-md border border-border bg-muted/40 p-0.5">
            <Button
              type="button"
              size="sm"
              variant={timeframe === "1D" ? "secondary" : "ghost"}
              onClick={() => setTimeframe("1D")}
              className="h-7 px-2.5 text-xs"
              aria-pressed={timeframe === "1D"}
            >
              1D
            </Button>
            <Button
              type="button"
              size="sm"
              variant={timeframe === "1W" ? "secondary" : "ghost"}
              onClick={() => setTimeframe("1W")}
              className="h-7 px-2.5 text-xs"
              aria-pressed={timeframe === "1W"}
            >
              1W
            </Button>
          </div>

          {/* Logarithmic / Linear Scale Toggle */}
          <Button
            type="button"
              onClick={() => handleScaleChange(!isLogScale)}
            size="sm"
            variant={isLogScale ? "secondary" : "outline"}
            className="h-7 px-2.5 text-xs"
            aria-pressed={isLogScale}
            title={isLogScale ? "Switch to Linear Scale (LIN)" : "Switch to Logarithmic Scale (LOG)"}
          >
            {isLogScale ? "LOG" : "LIN"}
          </Button>

          {/* Range Jump Selector & Lazy Loading Indicator */}
          <div className="flex items-center gap-2">
            {isLoadingMoreHistory && (
              <span className="text-[10px] text-accent animate-pulse font-mono flex items-center gap-1">
                <span>⏳</span> Loading historical depth…
              </span>
            )}
            <Select value={activeRange} onValueChange={(value) => handleRangePreset(value as ChartRangePreset)}>
              <SelectTrigger aria-label="Chart range" className="h-7 w-[5.5rem] px-2 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["3M", "6M", "1Y", "2Y", "6Y", "ALL"] as ChartRangePreset[]).map((range) => (
                  <SelectItem key={range} value={range}>
                    {range === "6Y" ? "6Y · 4+2" : range}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              onClick={handleResetView}
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              title="Reset chart view"
            >
              Reset
            </Button>

            {/* Chart Height Slider */}
            <div className="hidden md:flex items-center gap-1.5 rounded border border-line bg-surface px-2 py-0.5 font-mono text-[9px] text-ink-muted">
              <span title="Adjust chart vertical canvas height">Height:</span>
              <Slider
                min={340}
                max={750}
                step={20}
                value={[chartHeight]}
                onValueChange={([height]) => height !== undefined && handleChartHeightChange(height)}
                className="w-20"
                aria-label="Chart height"
              />
              <span className="w-8 text-right font-bold text-ink">{chartHeight}px</span>
            </div>
          </div>

          <div className="relative">
            <Button
              ref={indicatorButtonRef}
              type="button"
              onClick={() => setIndicatorMenuOpen((open) => !open)}
              variant={indicatorMenuOpen ? "secondary" : "outline"}
              size="sm"
              className="h-7 gap-1.5 px-2 text-xs"
              aria-expanded={indicatorMenuOpen}
              title="Indicator settings"
            >
              <span>Indicators</span>
              <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-muted px-1 text-[10px] font-semibold text-muted-foreground">{activeIndicatorCount}</span>
            </Button>

            {indicatorMenuOpen && (
              <div
                ref={indicatorMenuRef}
                className="absolute right-0 z-50 mt-2 w-[min(360px,calc(100vw-1rem))] overflow-hidden rounded-xl border border-line bg-surface shadow-2xl shadow-slate-950/25"
              >
                <div className="border-b border-line bg-surface-raised px-2.5 py-2">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-ink">
                      {timeframe === "1W" ? "Weekly studies" : "Daily studies"}
                    </div>
                    <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={handleResetChartDefaults}>
                      Reset defaults
                    </Button>
                  </div>
                  <Input
                    value={indicatorSearch}
                    onChange={(event) => setIndicatorSearch(event.target.value)}
                    placeholder="Search indicators..."
                    className="h-8 w-full px-2.5 py-1.5 text-xs"
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
                          <Button
                            key={option.key}
                            type="button"
                            variant={enabled ? "secondary" : "ghost"}
                            size="sm"
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
                            aria-pressed={enabled}
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
                          </Button>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Reveal Future / Blind Mode Toggle */}
          {onToggleRevealFuture && (
            <Button
              type="button"
              onClick={() => onToggleRevealFuture(!revealFuture)}
              variant={revealFuture ? "secondary" : "outline"}
              size="sm"
              className="h-7 px-2 text-xs"
              aria-pressed={revealFuture}
              aria-label={revealFuture ? "Hide future chart data" : "Show future chart data"}
              title={revealFuture ? "Hide forecast data" : "Show forecast data"}
            >
              {revealFuture ? "Forecast on" : "Forecast"}
            </Button>
          )}
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div
        className="relative w-full"
        style={{ height: `${renderedChartHeight}px`, minHeight: isCompactViewport ? "280px" : "340px" }}
        ref={chartContainerRef}
        onMouseLeave={() => setHoveredCandle(null)}
        onContextMenu={(e) => {
          e.preventDefault();
          handleResetView();
        }}
        onDoubleClick={handleResetView}
        title={`Double-click or right-click to reset view to ${timeframe === "1D" ? "1Y" : "2Y"}`}
      />

    </div>
  );
}
