import type {
  AlphaPerformanceResult,
  PreviewResponse,
  SavedScreen,
  ScreenField,
  ScreenPreset,
  ScreenTemplateDetail,
  ScreenTemplateSummary,
  StockIntrospectionData,
  TurnoverResponse,
  UniverseQueryV1,
  UniverseRangeSummary,
} from "../types";
import { toTvSymbol } from "../lib/tvSymbol";

export interface MarketContextPoint {
  date: string;
  weekly_allocation_fraction: number;
  weekly_allocation_tier: number;
  composite_score_normalized: number;
  market_regime_signal: number;
  is_bear_market_active: number;
  allocation_note: string;
  breadth_200d: number;
  breadth_50d: number;
  spy_close: number;
  spy_sma200d: number;
  spy_sma50d: number;
  spy_above200d: number;
  spy_above50d: number;
  spy_below200d: number;
  spy_below200d_3d: number;
  ma50_gt_ma200: number;
  ma50_slope_pos: number;
  ma200_slope_pos: number;
  ma_stack_score: number;
  risk_on_fast_flags: number;
  risk_off_fast_flags: number;
  clamp_risk_off: number;
  breadth_thrust: number;
  ftd: number;
  distribution_count_25d: number;
  breadth55_days15: number;
  is_bear_market_enhanced: number;
  bear_severity: string;
  bear_market_score: number;
  pct_near_52w_high: number;
  pct_near_52w_low: number;
  pct_above_sma20d: number;
  pct_above_sma50d: number;
  pct_above_sma200d: number;
  pct_above_sma20d_sma5: number;
  pct_above_sma50d_sma5: number;
  pct_above_sma200d_sma5: number;
  price_vs_sma30w_pct: number | null;
  price_vs_sma40w_pct: number | null;
  sma30w_vs_sma40w_pct: number | null;
  sma40w_slope_pct: number | null;
  trend_score: number;
  pct_sp500_above_sma40w: number | null;
  pct_stocks_above_sma200: number;
  market_sma200_trend_strength: number;
  vix_close: number | null;
  vix_sma20d: number | null;
  vix_sma50d: number | null;
  vix_sma200d: number | null;
  vix_vs_sma20d_pct: number | null;
  vix_vs_sma50d_pct: number | null;
  vix_vs_sma200d_pct: number | null;
  vix_contango_proxy: number;
  vix_spike_flag: number;
  vix_above_sma200d: number;
  uvxy_vs_vix_basis: number | null;
  svxy_vs_vix_basis: number | null;
}

export async function fetchMarketContext(
  startDate: string,
  endDate: string,
  limit = 2000,
): Promise<MarketContextPoint[]> {
  const data = await request<MarketContextPoint[]>(
    `/api/screens/market-context?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&limit=${limit}`,
  );
  return Array.isArray(data) ? data : [];
}

async function parseJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    const snippet = text.replace(/\s+/g, " ").slice(0, 180);
    throw new Error(`Invalid JSON from ${res.url} (${res.status}): ${snippet}`);
  }
}

/** Unwrap DRF / VeraCharts-style envelopes when present. */
function unwrapData(payload: unknown): unknown {
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    if ("data" in obj && obj.data !== undefined) return obj.data;
    if ("result" in obj && obj.result !== undefined) return obj.result;
  }
  return payload;
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    ...init,
  });
  const raw = await parseJson(res);
  if (!res.ok) {
    const detail =
      raw && typeof raw === "object" && "detail" in raw
        ? String((raw as { detail: unknown }).detail)
        : res.statusText;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return unwrapData(raw) as T;
}

export async function fetchPresets(): Promise<ScreenPreset[]> {
  const data = await request<ScreenPreset[] | { presets: ScreenPreset[] }>(
    "/api/screens/presets",
  );
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data.presets)) {
    return data.presets;
  }
  return [];
}

export async function fetchPresetUniverse(
  presetId: string,
): Promise<{ preset_id: string; spec: UniverseQueryV1 }> {
  return request<{ preset_id: string; spec: UniverseQueryV1 }>(
    `/api/screens/presets/${encodeURIComponent(presetId)}/universe`,
  );
}

export async function fetchFieldValues(name: string, q = "", limit = 40): Promise<string[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("limit", String(limit));
  const data = await request<{ values?: string[] }>(
    `/api/screens/fields/${encodeURIComponent(name)}/values?${params.toString()}`,
  );
  return Array.isArray(data.values) ? data.values : [];
}

/** Pre-LEAN factor performance (VeraProjects#70/#75): quantiles, IC/ICIR, regime, verdict. */
export async function fetchAlphaPerformance(
  name: string,
  opts: {
    start: string;
    end: string;
    horizon?: "5d" | "21d";
    quantiles?: number;
    table?: string;
  },
): Promise<AlphaPerformanceResult> {
  const params = new URLSearchParams({ start: opts.start, end: opts.end });
  params.set("horizon", opts.horizon ?? "5d");
  params.set("quantiles", String(opts.quantiles ?? 10));
  if (opts.table) params.set("table", opts.table);
  return request<AlphaPerformanceResult>(
    `/api/screens/fields/${encodeURIComponent(name)}/alpha-performance?${params.toString()}`,
  );
}

export async function fetchFields(): Promise<ScreenField[]> {
  const data = await request<{ fields: ScreenField[]; count?: number }>(
    "/api/screens/fields",
  );
  if (data && typeof data === "object" && Array.isArray(data.fields)) {
    return data.fields;
  }
  return [];
}

export async function fetchTemplates(): Promise<ScreenTemplateSummary[]> {
  const data = await request<
    ScreenTemplateSummary[] | { templates: ScreenTemplateSummary[] }
  >("/api/screens/templates");
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data.templates)) {
    return data.templates;
  }
  return [];
}

export async function fetchTemplate(
  id: string,
): Promise<ScreenTemplateDetail> {
  return request<ScreenTemplateDetail>(
    `/api/screens/templates/${encodeURIComponent(id)}`,
  );
}

export async function fetchAsOfRange(limit = 10000): Promise<string[]> {
  const data = await request<unknown>(
    `/api/screens/as-of-range?limit=${limit}`,
  );
  if (Array.isArray(data)) return data.map(String);
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.dates)) return obj.dates.map(String);
    if (Array.isArray(obj.as_of_range)) return obj.as_of_range.map(String);
  }
  return [];
}

export async function previewScreen(body: {
  as_of: string;
  preset: string;
  limit?: number;
}): Promise<PreviewResponse> {
  return request<PreviewResponse>("/api/screens/preview", {
    method: "POST",
    body: JSON.stringify({
      as_of: body.as_of,
      preset: body.preset,
      limit: body.limit ?? 50,
    }),
  });
}

export async function previewIr(body: {
  as_of: string;
  spec: UniverseQueryV1;
  /** NTH-2: attach days_in_universe (pinned/end asof only). */
  include_tenure?: boolean;
  tenure_start?: string;
}): Promise<PreviewResponse> {
  return request<PreviewResponse>("/api/screens/preview-ir", {
    method: "POST",
    body: JSON.stringify({
      as_of: body.as_of,
      spec: body.spec,
      include_tenure: body.include_tenure,
      tenure_start: body.tenure_start,
    }),
  });
}

/** Compile universe_query_v1 to ClickHouse SQL without executing. */
export async function compileUniverseSql(body: {
  spec: UniverseQueryV1;
}): Promise<{ sql: string; params: Record<string, unknown> }> {
  return request<{ sql: string; params: Record<string, unknown> }>(
    "/api/screens/compile-sql",
    {
      method: "POST",
      body: JSON.stringify({ spec: body.spec }),
    },
  );
}

export async function fetchTurnover(body: {
  as_of: string;
  preset: string;
  limit?: number;
}): Promise<TurnoverResponse | null> {
  try {
    return await request<TurnoverResponse>("/api/screens/turnover", {
      method: "POST",
      body: JSON.stringify({
        as_of: body.as_of,
        preset: body.preset,
        limit: body.limit ?? 50,
      }),
    });
  } catch {
    return null;
  }
}

export async function fetchSavedScreens(): Promise<SavedScreen[]> {
  const data = await request<{ screens: SavedScreen[]; count?: number }>(
    "/api/screens/saved",
  );
  return Array.isArray(data?.screens) ? data.screens : [];
}

export async function createSavedScreen(body: {
  name: string;
  spec: UniverseQueryV1;
}): Promise<SavedScreen> {
  return request<SavedScreen>("/api/screens/saved", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateSavedScreen(
  id: number | string,
  body: { name?: string; spec?: UniverseQueryV1; source_template_id?: string },
): Promise<SavedScreen> {
  return request<SavedScreen>(`/api/screens/saved/${encodeURIComponent(String(id))}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteSavedScreen(id: number | string): Promise<void> {
  await request<unknown>(`/api/screens/saved/${encodeURIComponent(String(id))}`, {
    method: "DELETE",
  });
}

export async function fetchUniverseRangeSummary(body: {
  spec: UniverseQueryV1;
  start_date: string;
  end_date: string;
  include_weekly_samples?: boolean;
}): Promise<UniverseRangeSummary> {
  return request<UniverseRangeSummary>("/api/screens/universe-range-summary", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** C-SCREEN-PROBE-V1 — stage-prefix probe (layers / asof / range / diff). */
export async function fetchScreenProbe(body: {
  view: "layers" | "asof" | "range" | "diff";
  pipeline?: unknown;
  spec?: UniverseQueryV1;
  preset_id?: string;
  through?: { binding_id?: string; stage_index?: number };
  through_b?: { binding_id?: string; stage_index?: number };
  probe_mode?: "measures" | "members";
  as_of?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  include_sql?: boolean;
  /** Stage toggles for Alpha membership probe overlays / funnel. */
  enabled_bindings?: string[];
  /** When true with enabled_bindings, range also returns measure_series.funnel (AND pass count). */
  cumulative?: boolean;
  /** Optional L7 columns merged into asof select (NTH-1; max 8). */
  extra_select?: string[];
  /** Optional asof order_by (field must be in select). */
  order_by?: Array<{ field: string; direction?: "asc" | "desc" }>;
  /** NTH-2: attach days_in_universe for asof rows. */
  include_tenure?: boolean;
  tenure_start?: string;
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/screens/probe", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchStockIntrospection(
  ticker: string,
  as_of: string,
  historyDays = 300,
  forwardDays = 60,
  includeDossier?: boolean,
): Promise<StockIntrospectionData> {
  const params = new URLSearchParams({
    ticker,
    as_of,
    history_days: String(historyDays),
    forward_days: String(forwardDays),
  });
  if (includeDossier !== undefined) {
    params.set("include_dossier", includeDossier ? "1" : "0");
  }
  return request<StockIntrospectionData>(`/api/screens/stock-overview?${params.toString()}`);
}

export function tradingViewUrl(
  ticker: string,
  exchange?: string | null,
): string {
  const sym = toTvSymbol(ticker, exchange);
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;
}

export async function fetchLatestTradingDate(): Promise<string | null> {
  try {
    const data = await request<{ latest_date: string | null }>("/api/screens/latest-trading-date");
    return data?.latest_date ?? null;
  } catch {
    return null;
  }
}
