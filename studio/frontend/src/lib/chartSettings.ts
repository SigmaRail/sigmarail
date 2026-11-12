export const CHART_SETTINGS_STORAGE_KEY = "sigmarail-studio.chart-settings.v2";
export const LEGACY_CHART_INDICATORS_KEY = "sigmarail-studio.chart-indicators.v1";

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

export type ChartSettingsV2 = {
  lastTimeframe: ChartTimeframe;
  "1D": ChartTfBag;
  "1W": ChartTfBag;
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
  rsLine: true,
  earningsLine: false,
  earningsFlags: true,
  epsLine: false,
  fairValueRibbon: false,
  valuationCorridor: false,
  expectationTracks: false,
  multipleRibbon: false,
  forecast: false,
  ema10: true,
  ema21: true,
  sma50: true,
  sma200: true,
  spxOverlay: true,
};

export const DEFAULT_INDICATORS_1W: ChartIndicatorConfig = {
  ...DEFAULT_INDICATORS_1D,
  earningsLine: true,
};

export const DEFAULTS: ChartSettingsV2 = {
  lastTimeframe: "1W",
  "1D": { indicators: { ...DEFAULT_INDICATORS_1D }, range: "6M" },
  "1W": { indicators: { ...DEFAULT_INDICATORS_1W }, range: "2Y" },
};

function cloneDefaults(): ChartSettingsV2 {
  return {
    lastTimeframe: DEFAULTS.lastTimeframe,
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

function normalizeV2(parsed: unknown): ChartSettingsV2 {
  const base = cloneDefaults();
  if (!parsed || typeof parsed !== "object") return base;
  const rec = parsed as Record<string, unknown>;
  return {
    lastTimeframe: isTimeframe(rec.lastTimeframe) ? rec.lastTimeframe : base.lastTimeframe,
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
