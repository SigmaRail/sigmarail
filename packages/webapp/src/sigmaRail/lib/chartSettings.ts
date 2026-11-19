export const CHART_SETTINGS_STORAGE_KEY = "sigmarail-studio.chart-settings.v2";
export const LEGACY_CHART_INDICATORS_KEY = "sigmarail-studio.chart-indicators.v1";
const ACCOUNT_CHART_SETTINGS_PREFIX = "sigmarail-studio.user.";

export type ChartTimeframe = "1D" | "1W";
export type ChartRangePreset = "3M" | "6M" | "1Y" | "2Y" | "5Y" | "6Y" | "ALL";

export type ChartIndicatorKey =
  | "rsLine"
  | "earningsLine"
  | "earningsFlags"
  | "epsLine"
  | "fairValueRibbon"
  | "valuationCorridor"
  | "expectationTracks"
  | "multipleRibbon"
  | "forecast"
  | "ema10"
  | "ema21"
  | "sma50"
  | "sma200"
  | "spxOverlay";

export type ChartIndicatorConfig = Record<ChartIndicatorKey, boolean>;

export type ChartTfBag = {
  indicators: ChartIndicatorConfig;
  range: ChartRangePreset;
};

export type ChartPaneLayout = {
  price: number;
  rs: number;
  volume: number;
};

export type ChartSettingsV2 = {
  lastTimeframe: ChartTimeframe;
  chartHeight: number;
  isLogScale: boolean;
  /** Optional when loading chart preferences saved before pane sizing existed. */
  paneLayout?: ChartPaneLayout;
  "1D": ChartTfBag;
  "1W": ChartTfBag;
};

export const DEFAULT_CHART_HEIGHT = 420;
export const DEFAULT_CHART_PANE_LAYOUT: ChartPaneLayout = {
  price: 0.72,
  rs: 0.14,
  volume: 0.14,
};

const INDICATOR_KEYS: ChartIndicatorKey[] = [
  "rsLine",
  "earningsLine",
  "earningsFlags",
  "epsLine",
  "fairValueRibbon",
  "valuationCorridor",
  "expectationTracks",
  "multipleRibbon",
  "forecast",
  "ema10",
  "ema21",
  "sma50",
  "sma200",
  "spxOverlay",
];

const RANGE_PRESETS: ChartRangePreset[] = ["3M", "6M", "1Y", "2Y", "5Y", "6Y", "ALL"];

export const DEFAULT_INDICATORS_1D: ChartIndicatorConfig = {
  rsLine: false,
  earningsLine: false,
  earningsFlags: false,
  epsLine: false,
  fairValueRibbon: false,
  valuationCorridor: false,
  expectationTracks: false,
  multipleRibbon: false,
  forecast: false,
  ema10: false,
  ema21: true,
  sma50: true,
  sma200: false,
  spxOverlay: false,
};

export const DEFAULT_INDICATORS_1W: ChartIndicatorConfig = {
  ...DEFAULT_INDICATORS_1D,
};

export const DEFAULTS: ChartSettingsV2 = {
  lastTimeframe: "1D",
  chartHeight: DEFAULT_CHART_HEIGHT,
  isLogScale: false,
  paneLayout: { ...DEFAULT_CHART_PANE_LAYOUT },
  "1D": { indicators: { ...DEFAULT_INDICATORS_1D }, range: "1Y" },
  "1W": { indicators: { ...DEFAULT_INDICATORS_1W }, range: "2Y" },
};

function cloneDefaults(): ChartSettingsV2 {
  return {
    lastTimeframe: DEFAULTS.lastTimeframe,
    chartHeight: DEFAULTS.chartHeight,
    isLogScale: DEFAULTS.isLogScale,
    paneLayout: { ...DEFAULT_CHART_PANE_LAYOUT },
    "1D": {
      indicators: { ...DEFAULTS["1D"].indicators },
      range: DEFAULTS["1D"].range,
    },
    "1W": {
      indicators: { ...DEFAULTS["1W"].indicators },
      range: DEFAULTS["1W"].range,
    },
  };
}

function resolveStorage(storage?: Storage | null): Storage | null {
  if (storage) return storage;
  try {
    if (typeof window !== "undefined") return window.localStorage;
  } catch {
    return null;
  }
  return null;
}

function isTimeframe(value: unknown): value is ChartTimeframe {
  return value === "1D" || value === "1W";
}

function isRangePreset(value: unknown): value is ChartRangePreset {
  return typeof value === "string" && (RANGE_PRESETS as string[]).includes(value);
}

function mergeIndicators(
  defaults: ChartIndicatorConfig,
  parsed: Partial<ChartIndicatorConfig> | undefined,
): ChartIndicatorConfig {
  const next = { ...defaults };
  if (!parsed || typeof parsed !== "object") return next;
  for (const key of INDICATOR_KEYS) {
    const value = parsed[key];
    if (typeof value === "boolean") next[key] = value;
  }
  return next;
}

function normalizeBag(
  parsed: Partial<ChartTfBag> | undefined,
  defaults: ChartTfBag,
): ChartTfBag {
  return {
    indicators: mergeIndicators(defaults.indicators, parsed?.indicators),
    range: isRangePreset(parsed?.range) ? parsed.range : defaults.range,
  };
}

export function normalizeChartPaneLayout(value: unknown): ChartPaneLayout {
  if (!value || typeof value !== "object") return { ...DEFAULT_CHART_PANE_LAYOUT };
  const parsed = value as Partial<ChartPaneLayout>;
  const price = Number.isFinite(parsed.price) ? Math.max(0.1, parsed.price!) : DEFAULT_CHART_PANE_LAYOUT.price;
  const rs = Number.isFinite(parsed.rs) ? Math.max(0.08, parsed.rs!) : DEFAULT_CHART_PANE_LAYOUT.rs;
  const volume = Number.isFinite(parsed.volume) ? Math.max(0.1, parsed.volume!) : DEFAULT_CHART_PANE_LAYOUT.volume;
  const total = price + rs + volume;
  return { price: price / total, rs: rs / total, volume: volume / total };
}

function normalizeV2(parsed: unknown): ChartSettingsV2 {
  const base = cloneDefaults();
  if (!parsed || typeof parsed !== "object") return base;
  const rec = parsed as Record<string, unknown>;
  return {
    lastTimeframe: isTimeframe(rec.lastTimeframe) ? rec.lastTimeframe : base.lastTimeframe,
    chartHeight:
      typeof rec.chartHeight === "number" && Number.isFinite(rec.chartHeight)
        ? Math.max(320, Math.min(850, Math.round(rec.chartHeight)))
        : base.chartHeight,
    isLogScale: typeof rec.isLogScale === "boolean" ? rec.isLogScale : base.isLogScale,
    paneLayout: normalizeChartPaneLayout(rec.paneLayout),
    "1D": normalizeBag(rec["1D"] as Partial<ChartTfBag> | undefined, base["1D"]),
    "1W": normalizeBag(rec["1W"] as Partial<ChartTfBag> | undefined, base["1W"]),
  };
}

export function getTfBag(settings: ChartSettingsV2, tf: ChartTimeframe): ChartTfBag {
  return settings[tf];
}

export function setTfBag(
  settings: ChartSettingsV2,
  tf: ChartTimeframe,
  bag: ChartTfBag,
): ChartSettingsV2 {
  return {
    ...settings,
    [tf]: {
      indicators: { ...bag.indicators },
      range: bag.range,
    },
  };
}

export function loadChartSettings(storage?: Storage | null): ChartSettingsV2 {
  const store = resolveStorage(storage);
  if (!store) return cloneDefaults();

  try {
    const v2raw = store.getItem(CHART_SETTINGS_STORAGE_KEY);
    if (v2raw) return normalizeV2(JSON.parse(v2raw));

    const v1raw = store.getItem(LEGACY_CHART_INDICATORS_KEY);
    if (v1raw) {
      const v1 = JSON.parse(v1raw) as Partial<ChartIndicatorConfig>;
      const migrated: ChartSettingsV2 = {
        lastTimeframe: "1W",
        chartHeight: DEFAULT_CHART_HEIGHT,
        isLogScale: false,
        paneLayout: { ...DEFAULT_CHART_PANE_LAYOUT },
        "1D": {
          indicators: mergeIndicators(DEFAULT_INDICATORS_1D, v1),
          range: "6M",
        },
        "1W": {
          indicators: mergeIndicators(DEFAULT_INDICATORS_1W, v1),
          range: "2Y",
        },
      };
      store.setItem(CHART_SETTINGS_STORAGE_KEY, JSON.stringify(migrated));
      return migrated;
    }
  } catch {
    return cloneDefaults();
  }

  return cloneDefaults();
}

export function saveChartSettings(
  settings: ChartSettingsV2,
  storage?: Storage | null,
): void {
  const store = resolveStorage(storage);
  if (!store) return;
  try {
    store.setItem(CHART_SETTINGS_STORAGE_KEY, JSON.stringify(normalizeV2(settings)));
  } catch {
    // Ignore quota / privacy-mode failures.
  }
}

function removeLegacyChartSettings(store: Storage): void {
  try {
    store.removeItem(CHART_SETTINGS_STORAGE_KEY);
    store.removeItem(LEGACY_CHART_INDICATORS_KEY);
  } catch {
    // Storage may be disabled in privacy-restricted browsing contexts.
  }
}

export function accountChartSettingsKey(userId: string): string {
  return `${ACCOUNT_CHART_SETTINGS_PREFIX}${encodeURIComponent(userId)}.chart-settings.v2`;
}

export function loadAccountChartSettings(userId: string, storage?: Storage | null): ChartSettingsV2 {
  const store = resolveStorage(storage);
  if (!store) return cloneDefaults();

  try {
    const scoped = store.getItem(accountChartSettingsKey(userId));
    if (scoped) return normalizeV2(JSON.parse(scoped));

    // Import the prior single-user browser setting once, then remove its global key
    // so it cannot leak into another signed-in account on this browser.
    const legacy = loadChartSettings(store);
    saveAccountChartSettings(userId, legacy, store);
    return legacy;
  } catch {
    return cloneDefaults();
  }
}

export function saveAccountChartSettings(
  userId: string,
  settings: ChartSettingsV2,
  storage?: Storage | null,
): void {
  const store = resolveStorage(storage);
  if (!store) return;
  try {
    store.setItem(accountChartSettingsKey(userId), JSON.stringify(normalizeV2(settings)));
    removeLegacyChartSettings(store);
  } catch {
    // Ignore quota / privacy-mode failures; the profile remains the durable store.
  }
}
