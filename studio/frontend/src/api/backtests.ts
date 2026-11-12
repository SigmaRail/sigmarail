import type {
  AttributionResponse,
  BacktestJob,
  BacktestJobListItem,
  BacktestJobLog,
  BacktestReport,
  BacktestRunSummary,
  BacktestSpecSummary,
  ClosedTradesResponse,
  ComposeBacktestRequest,
  ComposeBacktestResponse,
  EquityCurveResponse,
  ExecutionHealth,
  ExecutionProjectsResponse,
  FetchBacktestSpecsOptions,
  FrameworkCatalog,
  LaunchOptimizerRequest,
  LeanProject,
  MonthlyReturnsResponse,
  MultiRunCompareResponse,
  OptimizerSessionHeatmapResponse,
  OptimizerSessionSummary,
  RunArtifactsResponse,
  SavedBacktestSpec,
  SaveFrameworkTemplateRequest,
  StrategyFrameworkTemplate,
  StrategySpecDetail,
  StrategyTemplateSummary,
  SubmitBacktestRequest,
  SubmitBacktestResponse,
  TickerCandlesResponse,
  TradeAnalyticsResponse,
} from "../types";

async function parseJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error(`Invalid JSON from ${res.url}`);
  }
}

function unwrapData(payload: unknown): unknown {
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    if ("data" in obj && obj.data !== undefined) return obj.data;
    if ("result" in obj && obj.result !== undefined) return obj.result;
  }
  return payload;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

export type FetchBacktestRunsOptions = {
  limit?: number;
  strategyId?: string;
  irId?: string;
  irContentHash?: string;
  status?: string;
  runType?: string;
  minSharpe?: number;
  minReturn?: number;
  maxDd?: number;
  search?: string;
  includeJobs?: boolean;
};

export async function fetchBacktestRuns(
  optionsOrLimit: number | FetchBacktestRunsOptions = 50,
  strategyId?: string,
): Promise<BacktestRunSummary[]> {
  const opts: FetchBacktestRunsOptions =
    typeof optionsOrLimit === "number"
      ? { limit: optionsOrLimit, strategyId }
      : optionsOrLimit;

  const params = new URLSearchParams({ limit: String(opts.limit ?? 50) });
  if (opts.strategyId?.trim()) params.set("strategy_id", opts.strategyId.trim());
  if (opts.irId?.trim()) params.set("ir_id", opts.irId.trim());
  if (opts.irContentHash?.trim()) params.set("ir_content_hash", opts.irContentHash.trim());
  if (opts.status?.trim() && opts.status !== "all") params.set("status", opts.status.trim());
  if (opts.runType?.trim() && opts.runType !== "all") params.set("run_type", opts.runType.trim());
  if (opts.minSharpe != null) params.set("min_sharpe", String(opts.minSharpe));
  if (opts.minReturn != null) params.set("min_return", String(opts.minReturn));
  if (opts.maxDd != null) params.set("max_dd", String(opts.maxDd));
  if (opts.search?.trim()) params.set("search", opts.search.trim());
  if (opts.includeJobs != null) params.set("include_jobs", opts.includeJobs ? "true" : "false");

  const data = await request<{ runs: BacktestRunSummary[] }>(
    `/api/backtests/runs?${params.toString()}`,
  );
  return Array.isArray(data?.runs) ? data.runs : [];
}

export async function fetchBacktestReport(runId: string): Promise<BacktestReport> {
  return request<BacktestReport>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/report`,
  );
}

export async function fetchRunEquityCurve(runId: string): Promise<EquityCurveResponse> {
  return request<EquityCurveResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/equity`,
  );
}

export async function fetchRunOrders(
  runId: string,
  limit = 200,
  options?: { symbol?: string; orderId?: string },
): Promise<{
  run_id: string;
  source?: string | null;
  orders: unknown[];
  count: number;
  truncated?: boolean;
  total?: number;
}> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (options?.symbol?.trim()) params.set("symbol", options.symbol.trim());
  if (options?.orderId?.trim()) params.set("order_id", options.orderId.trim());
  return request(
    `/api/backtests/runs/${encodeURIComponent(runId)}/orders?${params.toString()}`,
  );
}

export async function fetchRunClosedTrades(
  runId: string,
  limit = 500,
  options?: { symbol?: string; tradeId?: string },
): Promise<ClosedTradesResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (options?.symbol?.trim()) params.set("symbol", options.symbol.trim());
  if (options?.tradeId?.trim()) params.set("trade_id", options.tradeId.trim());
  return request<ClosedTradesResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/closed-trades?${params.toString()}`,
  );
}

export async function fetchRunMonthlyReturns(runId: string): Promise<MonthlyReturnsResponse> {
  return request<MonthlyReturnsResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/monthly-returns`,
  );
}

export async function fetchRunTradeAnalytics(runId: string): Promise<TradeAnalyticsResponse> {
  return request<TradeAnalyticsResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/trade-analytics`,
  );
}

export async function fetchMultiRunCompare(runIds: string[]): Promise<MultiRunCompareResponse> {
  const ids = runIds.map((r) => encodeURIComponent(r)).join(",");
  return request<MultiRunCompareResponse>(`/api/backtests/compare?run_ids=${ids}`);
}

export async function fetchRunChartSeries(
  runId: string,
  chart: string,
  series: string,
): Promise<{
  run_id: string;
  chart: string;
  series: string;
  points: { t: number; value: number }[];
  count: number;
  error?: string | null;
}> {
  const params = new URLSearchParams({ chart, series });
  return request(
    `/api/backtests/runs/${encodeURIComponent(runId)}/chart-series?${params.toString()}`,
  );
}

export async function fetchRunDaySnapshots(runId: string): Promise<{
  run_id: string;
  snapshots: Array<{
    date?: string;
    as_of?: string;
    equity?: number;
    holdings?: unknown[];
    candidates?: Array<{ ticker?: string }>;
  }>;
  count: number;
  error?: string | null;
}> {
  return request(
    `/api/backtests/runs/${encodeURIComponent(runId)}/day-snapshots`,
  );
}

export async function fetchRunArtifacts(runId: string): Promise<RunArtifactsResponse> {
  return request<RunArtifactsResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/artifacts`,
  );
}

export async function fetchRunArtifactPreview(
  runId: string,
  artifactType: string,
): Promise<{
  run_id: string;
  artifact_type: string;
  preview: string | null;
  truncated: boolean;
  error?: string | null;
}> {
  return request(
    `/api/backtests/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactType)}`,
  );
}

export async function fetchFrameworkCatalog(): Promise<FrameworkCatalog> {
  const data = await request<{
    catalog?: Record<string, unknown>;
    framework_catalog?: Record<string, unknown>;
    templates?: StrategyTemplateSummary[];
    strategy_templates?: StrategyTemplateSummary[];
  }>("/api/backtests/framework-catalog");
  return {
    catalog: data?.catalog ?? data?.framework_catalog,
    templates: Array.isArray(data?.strategy_templates)
      ? data.strategy_templates
      : Array.isArray(data?.templates)
        ? data.templates
        : [],
  };
}

export async function composeBacktest(
  body: ComposeBacktestRequest,
): Promise<ComposeBacktestResponse> {
  return request<ComposeBacktestResponse>("/api/backtests/compose", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchBacktestSpecs(
  options: FetchBacktestSpecsOptions | number = 50,
): Promise<BacktestSpecSummary[]> {
  const opts: FetchBacktestSpecsOptions =
    typeof options === "number" ? { limit: options } : options;

  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.search) params.set("search", opts.search);
  if (opts.alpha_type) params.set("alpha_type", opts.alpha_type);
  if (opts.universe_type) params.set("universe_type", opts.universe_type);
  if (opts.schema_status) params.set("schema_status", opts.schema_status);
  if (opts.is_template !== undefined) params.set("is_template", String(opts.is_template));

  const queryStr = params.toString() ? `?${params.toString()}` : "";
  const data = await request<{ specs: BacktestSpecSummary[] }>(
    `/api/backtests/specs${queryStr}`,
  );
  return Array.isArray(data?.specs) ? data.specs : [];
}

export async function fetchBacktestSpecDetail(
  irId: string,
): Promise<StrategySpecDetail> {
  return request<StrategySpecDetail>(
    `/api/backtests/specs/${encodeURIComponent(irId)}`,
  );
}

export async function saveBacktestSpec(body: {
  ir_id: string;
  title: string;
  spec: Record<string, unknown>;
  is_template?: boolean;
  category?: string;
  tags?: string[];
  notes?: string;
  /** Fork even when the target spec has no runs (explicit "save as new version"). */
  force_new_version?: boolean;
  /** Recorded as the fork's changelog; auto-generated server-side when omitted. */
  changelog_notes?: string;
  pipeline_document?: Record<string, unknown>;
  expected_hash?: string;
}): Promise<SavedBacktestSpec> {
  return request<SavedBacktestSpec>("/api/backtests/specs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchBacktestSpecHead(
  irId: string,
): Promise<{ ir_id: string; ir_content_hash?: string | null; updated_at?: string; title?: string }> {
  return request(`/api/backtests/specs/${encodeURIComponent(irId)}/head`);
}

export async function submitBacktest(
  body: SubmitBacktestRequest,
): Promise<SubmitBacktestResponse> {
  return request<SubmitBacktestResponse>("/api/backtests/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchBacktestJob(jobId: string): Promise<BacktestJob> {
  return request<BacktestJob>(
    `/api/backtests/jobs/${encodeURIComponent(jobId)}`,
  );
}

export async function fetchExecutionHealth(): Promise<ExecutionHealth> {
  return request<ExecutionHealth>("/api/execution/health");
}

export async function fetchExecutionProjects(): Promise<LeanProject[]> {
  const data = await request<ExecutionProjectsResponse>(
    "/api/execution/projects",
  );
  return Array.isArray(data?.projects) ? data.projects : [];
}

export async function fetchBacktestJobs(
  limit = 20,
  status?: string,
): Promise<BacktestJobListItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status?.trim()) {
    params.set("status", status.trim());
  }
  const data = await request<{ jobs: BacktestJobListItem[] }>(
    `/api/backtests/jobs?${params.toString()}`,
  );
  return Array.isArray(data?.jobs) ? data.jobs : [];
}

export async function fetchBacktestJobLog(
  jobId: string,
  tail = 200,
): Promise<BacktestJobLog> {
  return request<BacktestJobLog>(
    `/api/backtests/jobs/${encodeURIComponent(jobId)}/log?tail=${tail}`,
  );
}

export async function cancelBacktestJob(
  jobId: string,
): Promise<{ job_id: string; status: string; error?: string }> {
  return request<{ job_id: string; status: string; error?: string }>(
    `/api/backtests/jobs/${encodeURIComponent(jobId)}/cancel`,
    {
      method: "POST",
    },
  );
}

export async function fetchRunAttribution(
  runId: string,
): Promise<AttributionResponse> {
  return request<AttributionResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/attribution`,
  );
}

export async function fetchTickerCandles(
  ticker: string,
  startDate: string,
  endDate: string,
): Promise<TickerCandlesResponse> {
  const params = new URLSearchParams({
    ticker: ticker.trim().toUpperCase(),
    start_date: startDate.trim(),
    end_date: endDate.trim(),
  });
  return request<TickerCandlesResponse>(
    `/api/backtests/candles?${params.toString()}`,
  );
}

export async function launchOptimizerSession(
  req: LaunchOptimizerRequest,
): Promise<OptimizerSessionSummary & { jobs: Array<{ job_id: string; ir_id: string; parameters: Record<string, unknown> }> }> {
  return request("/api/backtests/optimize", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function fetchOptimizerSessions(
  limit = 20,
): Promise<{ sessions: OptimizerSessionSummary[]; count: number }> {
  return request<{ sessions: OptimizerSessionSummary[]; count: number }>(
    `/api/backtests/optimize/sessions?limit=${limit}`,
  );
}

export async function fetchOptimizerSessionHeatmap(
  sessionId: string,
): Promise<OptimizerSessionHeatmapResponse> {
  return request<OptimizerSessionHeatmapResponse>(
    `/api/backtests/optimize/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function fetchFrameworkTemplates(): Promise<{
  templates: StrategyFrameworkTemplate[];
  count: number;
}> {
  return request<{ templates: StrategyFrameworkTemplate[]; count: number }>(
    "/api/backtests/framework-templates",
  );
}

export async function saveFrameworkTemplate(
  req: SaveFrameworkTemplateRequest,
): Promise<StrategyFrameworkTemplate> {
  return request<StrategyFrameworkTemplate>("/api/backtests/framework-templates", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function updateFrameworkTemplate(
  id: string | number,
  req: Partial<SaveFrameworkTemplateRequest>,
): Promise<StrategyFrameworkTemplate> {
  return request<StrategyFrameworkTemplate>(
    `/api/backtests/framework-templates/${encodeURIComponent(String(id))}`,
    {
      method: "PUT",
      body: JSON.stringify(req),
    },
  );
}

export async function deleteFrameworkTemplate(
  id: string | number,
): Promise<{ deleted: boolean; id: string | number }> {
  return request<{ deleted: boolean; id: string | number }>(
    `/api/backtests/framework-templates/${encodeURIComponent(String(id))}`,
    {
      method: "DELETE",
    },
  );
}

export async function fetchRunDrawdowns(
  runId: string,
): Promise<import("../types").DrawdownAnalyticsResponse> {
  return request<import("../types").DrawdownAnalyticsResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/drawdowns`,
  );
}

export async function fetchRunBenchmarkComparison(
  runId: string,
  benchmark: string = "SPY",
): Promise<import("../types").BenchmarkComparisonResponse> {
  const p = new URLSearchParams({ benchmark });
  return request<import("../types").BenchmarkComparisonResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/benchmark-comparison?${p.toString()}`,
  );
}

export async function fetchRunAssetAllocation(
  runId: string,
): Promise<import("../types").AssetAllocationResponse> {
  return request<import("../types").AssetAllocationResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/asset-allocation`,
  );
}

export async function fetchRunPortfolioExposure(
  runId: string,
): Promise<import("../types").PortfolioExposureResponse> {
  return request<import("../types").PortfolioExposureResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/exposure`,
  );
}

export async function fetchRunRollingStats(
  runId: string,
): Promise<import("../types").RollingStatsResponse> {
  return request<import("../types").RollingStatsResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/rolling-stats`,
  );
}
