import { describe, expect, it } from "vitest";
import {
  CHART_SETTINGS_STORAGE_KEY,
  DEFAULTS,
  DEFAULT_INDICATORS_1D,
  DEFAULT_INDICATORS_1W,
  LEGACY_CHART_INDICATORS_KEY,
  getTfBag,
  loadChartSettings,
  saveChartSettings,
  setTfBag,
  type ChartIndicatorConfig,
} from "./chartSettings";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();

  get length() {
    return this.data.size;
  }

  clear() {
    this.data.clear();
  }

  getItem(key: string) {
    return this.data.has(key) ? this.data.get(key)! : null;
  }

  key(index: number) {
    return [...this.data.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.data.delete(key);
  }

  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}

describe("chartSettings v2", () => {
  it("returns defaults when storage is empty", () => {
    const store = new MemoryStorage();
    const loaded = loadChartSettings(store);
    expect(loaded.lastTimeframe).toBe("1W");
    expect(loaded["1D"].range).toBe("6M");
    expect(loaded["1W"].range).toBe("2Y");
    expect(loaded["1D"].indicators).toEqual(DEFAULT_INDICATORS_1D);
    expect(loaded["1W"].indicators).toEqual(DEFAULT_INDICATORS_1W);
    expect(loaded["1W"].indicators.earningsLine).toBe(true);
    expect(loaded["1D"].indicators.earningsLine).toBe(false);
    expect(loaded["1D"].indicators.fairValueRibbon).toBe(false);
    expect(loaded["1W"].indicators.spxOverlay).toBe(true);
  });

  it("migrates legacy v1 indicators onto both timeframes once", () => {
    const store = new MemoryStorage();
    const legacy: Partial<ChartIndicatorConfig> = {
      rsLine: false,
      epsLine: true,
      forecast: true,
      ema10: false,
    };
    store.setItem(LEGACY_CHART_INDICATORS_KEY, JSON.stringify(legacy));

    const loaded = loadChartSettings(store);
    expect(loaded["1D"].indicators.rsLine).toBe(false);
    expect(loaded["1W"].indicators.rsLine).toBe(false);
    expect(loaded["1D"].indicators.epsLine).toBe(true);
    expect(loaded["1W"].indicators.epsLine).toBe(true);
    expect(loaded["1D"].indicators.ema10).toBe(false);
    expect(loaded["1W"].indicators.forecast).toBe(true);
    expect(loaded["1D"].indicators.spxOverlay).toBe(true);
    expect(loaded["1W"].indicators.earningsLine).toBe(true);
    expect(loaded["1D"].indicators.earningsLine).toBe(false);
    expect(store.getItem(CHART_SETTINGS_STORAGE_KEY)).toBeTruthy();

    store.setItem(
      LEGACY_CHART_INDICATORS_KEY,
      JSON.stringify({ rsLine: true, ema10: true }),
    );
    const again = loadChartSettings(store);
    expect(again["1D"].indicators.rsLine).toBe(false);
    expect(again["1D"].indicators.ema10).toBe(false);
  });

  it("prefers v2 over leftover v1", () => {
    const store = new MemoryStorage();
    store.setItem(LEGACY_CHART_INDICATORS_KEY, JSON.stringify({ rsLine: false }));
    saveChartSettings(
      {
        lastTimeframe: "1D",
        "1D": { indicators: { ...DEFAULTS["1D"].indicators, sma200: false }, range: "1Y" },
        "1W": { indicators: { ...DEFAULTS["1W"].indicators }, range: "5Y" },
      },
      store,
    );
    const loaded = loadChartSettings(store);
    expect(loaded.lastTimeframe).toBe("1D");
    expect(loaded["1D"].range).toBe("1Y");
    expect(loaded["1W"].range).toBe("5Y");
    expect(loaded["1D"].indicators.sma200).toBe(false);
    expect(loaded["1D"].indicators.rsLine).toBe(true);
  });

  it("getTfBag / setTfBag write only the active timeframe", () => {
    const base = loadChartSettings(new MemoryStorage());
    const next = setTfBag(base, "1D", {
      indicators: { ...base["1D"].indicators, rsLine: false },
      range: "3M",
    });
    expect(getTfBag(next, "1D").range).toBe("3M");
    expect(getTfBag(next, "1D").indicators.rsLine).toBe(false);
    expect(getTfBag(next, "1W").range).toBe("2Y");
    expect(getTfBag(next, "1W").indicators.rsLine).toBe(true);
  });

  it("round-trips save then load", () => {
    const store = new MemoryStorage();
    const settings = setTfBag(DEFAULTS, "1W", {
      indicators: { ...DEFAULTS["1W"].indicators, spxOverlay: false },
      range: "ALL",
    });
    settings.lastTimeframe = "1W";
    saveChartSettings(settings, store);
    const loaded = loadChartSettings(store);
    expect(loaded.lastTimeframe).toBe("1W");
    expect(loaded["1W"].range).toBe("ALL");
    expect(loaded["1W"].indicators.spxOverlay).toBe(false);
    expect(loaded["1D"].range).toBe("6M");
  });
});
