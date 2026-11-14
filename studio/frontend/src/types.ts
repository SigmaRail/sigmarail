export type StudioMode = "screen" | "research" | "deploy" | "monitor";
export type WorkbenchTab = "screens" | "charts" | "watchlists" | "compose" | "runs" | "optimize" | "deploy" | "monitor" | "market";
export type BacktestSubTab = "compose" | "runs" | "optimize" | "paper";

export type ScreenSource = "preset" | "ir";

export type ViewMode = "list" | "grid";

export type OrderDirection = "asc" | "desc";

export type ScreenPreset = {
  id: string;
  label: string;
  /** True when preset maps to universe_query_v1 (Research / compose). */
  backtestable?: boolean;
};

export type LineageCaveat = {
  code: string;
  severity: "info" | "warning" | "caution" | "low";
  title: string;
  description: string;
  lookback_bars?: number;
};

export type MathPresentation = {
  latex: string;
  variables: Record<string, string>;
};

export type ScreenField = {
  name: string;
  prefixed_name?: string;
  prefix?: string;
  label: string;
  category: string;
  category_label?: string;
  type?: string;
  table?: string;
  sql_expr?: string;
  description?: string;
  /** Slot FieldPicker: computed stage aliases vs L7 vs position locals. */
  origin?: "computed" | "l7" | "position";
  caveats?: LineageCaveat[];
  math?: MathPresentation;
};

export type FieldLineageResponse = {
  field: string;
  table: string;
  found: boolean;
  caveats: LineageCaveat[];
  math?: MathPresentation;
  graph?: {
    root: { table: string; column: string };
    nodes: any[];
    edges: Array<{ from: string; to: string }>;
    truncated: boolean;
  };
};

export type CohortDistribution = {
  min: number;
  p10: number;
  p25: number;
  median: number;
  p75: number;
  p90: number;
  max: number;
};

export type FieldEvaluationResult = {
  ticker: string;
  field: string;
  date: string;
  value: number | string | null;
  universe_size?: number;
  rank?: number;
  components?: Record<string, any>;
  steps?: string[];
  distribution?: CohortDistribution | null;
  cohort_percentile?: number | null;
  substituted_latex?: string | null;
};

export type CatalogTemplateKind = "screener" | "strategy";
export type CatalogTemplateStatus = "active" | "deprecated" | "draft";

/** vera_query_core.alpha_evaluation.evaluate_factor_performance response (VeraProjects#70). */
export type AlphaPerformanceQuantile = {
  bucket: number;
  n_obs: number;
  mean_fwd_ret: number;
  mean_ew_ret: number;
  mean_active_spread: number;
  hit_rate: number;
  n_days: number;
};

export type AlphaPerformanceResult = {
  factor: string;
  factor_table: string;
  horizon: "5d" | "21d";
  quantiles_requested: number;
  start_date: string;
  end_date: string;
  quantiles: AlphaPerformanceQuantile[];
  ic_stats: {
    mean_ic: number | null;
    std_ic: number | null;
    icir: number | null;
    n_days: number;
  };
  regime_attribution: Record<string, { active_spread: number; n_days: number }>;
  monotonicity_score: number | null;
  summary: {
    n_days: number;
    top_bucket: number | null;
    top_mean_fwd_ret: number | null;
    top_mean_active_spread: number | null;
    ew_mean_fwd_ret: number | null;
    top_minus_bottom_spread: number | null;
    top_minus_bottom_active_spread: number | null;
  };
  verdict: "pass" | "fail" | "insufficient_data";
  verdict_reasons: string[];
};

export type ScreenTemplateSummary = {
  id: string;
  label: string;
  kind?: CatalogTemplateKind;
  tags?: string[];
  description?: string;
  why?: string;
  how?: string;
  status?: CatalogTemplateStatus;
  screener_template_id?: string;
};

export type ScreenTemplateDetail = {
  id: string;
  label: string;
  screen_ir?: string;
  description?: string;
  why?: string;
  how?: string;
  status?: CatalogTemplateStatus;
  spec: UniverseQueryV1;
};

export type IrOperand =
  | { type: "col"; name: string; offset?: number }
  | { type: "lit"; value: string | number | boolean }
  | {
      type: "formula";
      op: string;
      args: IrOperand[];
    };

export type ComparisonOp = "gt" | "gte" | "lt" | "lte" | "eq" | "neq";

export type IrComparisonNode = {
  type: ComparisonOp;
  left: IrOperand;
  right: IrOperand;
};

export type IrGroupNode = {
  type: "all" | "any";
  items: IrWhereNode[];
  name?: string;
};

export type IrWhereNode = IrComparisonNode | IrGroupNode | Record<string, unknown>;

/** A single ORDER BY term: either an allowlisted `field` (must be in select)
 *  or an `expr` operand tree (ColRef/LitVal/FormulaExpr over allowlisted cols). */
export type OrderByItemV1 =
  | { field: string; direction?: OrderDirection | string; expr?: never }
  | { expr: IrOperand; direction?: OrderDirection | string; field?: never };

export type UniverseQueryV1 = {
  version?: number;
  from: string;
  select: string[];
  where: IrWhereNode;
  order_by?: OrderByItemV1[];
  limit_per_day?: number;
  [key: string]: unknown;
};

export type SavedScreen = {
  id: number | string;
  name: string;
  spec: UniverseQueryV1;
  is_system?: boolean;
  category?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  source_template_id?: string;
  spec_content_hash?: string;
};

export type ScreenRow = {
  ticker: string;
  date?: string;
  close?: number | null;
  rs_rating?: number | null;
  technical_rating?: number | null;
  setup_quality_rating?: number | null;
  high_growth_momentum_rating?: number | null;
  avg_vol_50d?: number | null;
  overall_score?: number | null;
  minervini_score?: number | null;
  oneil_score?: number | null;
  classification?: string | null;
  industry_group_rank?: number | null;
  [key: string]: unknown;
};

export type PreviewResponse = {
  as_of: string;
  preset?: string;
  limit: number;
  table?: string | null;
  count: number;
  rows: ScreenRow[];
  screen_ir?: unknown;
  spec?: UniverseQueryV1;
  /** Compiled ClickHouse SQL for universe_query_v1 previews (when present). */
  sql?: string;
  params?: Record<string, unknown>;
  note?: string;
};

export type TurnoverResponse = {
  as_of: string;
  prior: string | null;
  added: string[];
  removed: string[];
  retained_count: number;
};

export type RankDelta = "new" | "dropped" | "up" | "down" | "same" | null;

export type RankedRow = ScreenRow & {
  rank: number;
  priorRank: number | null;
  delta: RankDelta;
  deltaRank: number | null;
};

export type BacktestRunSummary = {
  run_id: string;
  strategy_id?: string | null;
  run_timestamp?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  ir_id?: string | null;
  run_type?: string | null;
  trigger?: string | null;
  total_return?: number | null;
  annual_return?: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  max_drawdown?: number | null;
  win_rate?: number | null;
  profit_factor?: number | null;
  total_orders?: number | null;
  total_fees?: number | null;
  alpha?: number | null;
  beta?: number | null;
  volatility?: number | null;
  git_commit?: string | null;
  git_branch?: string | null;
  spec_title?: string | null;
  alpha_type?: string | null;
  universe_type?: string | null;
  risk_type?: string | null;
  portfolio_type?: string | null;
  execution_type?: string | null;
  symbols?: string[];
  ir_schema_version?: number | null;
  ir_content_hash?: string | null;
  /** The spec's hash at read time; differs from ir_content_hash = older revision. */
  spec_ir_content_hash?: string | null;
  /** True when this run came from an earlier revision than the spec's current one. */
  revision_stale?: boolean;
  status?: "done" | "running" | "failed" | "pending" | "cancelled" | string;
  error_message?: string | null;
  progress_pct?: number | null;
  algorithm_json?: string | null;
};

export type BacktestReportMetrics = {
  total_return?: number | null;
  annual_return?: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  max_drawdown?: number | null;
  win_rate?: number | null;
  profit_factor?: number | null;
  total_orders?: number | null;
  total_fees?: number | null;
  start_equity?: number | null;
  end_equity?: number | null;
};

/** Handoff from Screen mode → Backtest compose (inline, saved, or L7 preset). */
export type BacktestPrefill = {
  universeSource: "inline" | "saved" | "preset";
  inlineSpec?: UniverseQueryV1;
  savedScreenId?: number | string;
  /** L7 screen_stocks preset id when universeSource is preset. */
  presetId?: string;
  title?: string;
  /** True when Screen tab spec differs from last saved snapshot. */
  dirty?: boolean;
};

export type BacktestReport = {
  run_id: string;
  ir_id?: string | null;
  period?: { start?: string; end?: string };
  run_type?: string | null;
  trigger?: string | null;
  run_timestamp?: string | null;
  metrics?: BacktestReportMetrics;
  summary_statistics_keys?: string[];
  highlights?: string[];
  warnings?: string[];
  artifact_refs?: Array<{ artifact_type?: string; json_bytes?: number | null }>;
  provenance?: {
    git_commit?: string | null;
    git_branch?: string | null;
    image?: string | null;
    ir_schema_version?: string | null;
    ir_content_hash?: string | null;
  };
};

export type StrategyTemplateSummary = {
  id: string;
  label: string;
  description?: string;
};

export type FrameworkCatalog = {
  catalog?: Record<string, unknown>;
  templates: StrategyTemplateSummary[];
};

export type ComposeUniverseSource =
  | "saved_screen"
  | "inline"
  | "inline_spec"
  | "screen_preset";

export type ComposeUniverse = {
  source: ComposeUniverseSource;
  saved_screen_id?: number | string;
  inline_spec?: UniverseQueryV1;
  preset_id?: string;
};

export type EquityCurvePoint = {
  t: number;
  equity: number;
};

export type EquityCurveResponse = {
  run_id: string;
  source?: string | null;
  points: EquityCurvePoint[];
  count: number;
  error?: string | null;
};

export type RunArtifactsResponse = {
  run_id: string;
  artifacts: Array<{
    artifact_type?: string;
    json_bytes?: number | null;
    created_at?: string | null;
  }>;
  count: number;
};

export type ComposeLineage = {
  studio_screen_id?: number | string;
  studio_screen_name?: string;
};

export type ComposeBacktestRequest = {
  template_id?: string;
  framework?: Record<string, unknown>;
  universe?: ComposeUniverse;
  spec?: Record<string, unknown>;
  framework_overrides?: Record<string, unknown>;
  algorithm_parameters?: Record<string, unknown>;
  title?: string;
  lineage?: ComposeLineage;
};

export type UniverseRangeSummary = {
  start_date: string;
  end_date: string;
  dates: string[];
  member_counts: number[];
  summary: {
    trading_days: number;
    avg_members_per_day: number;
    min_members_per_day: number;
    max_members_per_day: number;
  };
  weekly_samples?: Array<{ date: string; sample_tickers: string[] }>;
};

export type ComposeValidation = {
  ok: boolean;
  message?: string;
  error?: string | null;
};

export type ComposeBacktestResponse = {
  spec: Record<string, unknown>;
  ir_id_suggested?: string | null;
  validation: ComposeValidation;
};

export type AssembledAlphaState = {
  use_screener: boolean;
  screener_max_positions: number;
  screener_stop_loss_pct: number;
  use_rsi: boolean;
  rsi_period: number;
  rsi_resolution: "Daily" | "Hour" | "Minute";
  use_macd: boolean;
  use_ema: boolean;
};

export type AssembledPcmState = {
  engine: string;
  max_weight: number;
  rebalance: string;
};

export type AssembledRiskState = {
  use_trailing_stop: boolean;
  trailing_stop_pct: number;
  use_sector_cap: boolean;
  max_sector_exposure: number;
  use_hard_stop: boolean;
  stop_loss_pct: number;
  use_take_profit: boolean;
  take_profit_pct: number;
};

export type AssembledExecutionState = {
  engine: string;
};

export type AssembledFrameworkSpec = {
  alpha: AssembledAlphaState;
  pcm: AssembledPcmState;
  risk: AssembledRiskState;
  execution: AssembledExecutionState;
};

export type StrategyFrameworkTemplate = {
  id: string | number;
  name: string;
  description: string;
  category?: string;
  is_system?: boolean;
  framework: AssembledFrameworkSpec;
  created_at?: string;
  updated_at?: string;
};

export type SaveFrameworkTemplateRequest = {
  name: string;
  description?: string;
  category?: string;
  framework: AssembledFrameworkSpec;
};

export type BacktestSpecSummary = {
  ir_id: string;
  title: string;
  spec_schema_version?: number;
  notes?: string;
  category?: string;
  is_system?: boolean;
  is_template?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  alpha_type?: string | null;
  universe_type?: string | null;
  risk_type?: string | null;
  portfolio_type?: string | null;
  execution_type?: string | null;
  symbols?: string[];
  screener_summary?: {
    has_screener: boolean;
    source?: string | null;
    rules_count?: number;
    order_by?: string | null;
    limit_per_day?: number | null;
  };
  algorithm_json?: string | null;
  has_pipeline?: boolean;
  ir_content_hash?: string | null;
  compiler_version?: string | null;
  schema_status?: "modern" | "legacy" | string;
  [key: string]: unknown;
};

export type StrategySpecDetail = BacktestSpecSummary & {
  spec: Record<string, unknown>;
};

export type FetchBacktestSpecsOptions = {
  search?: string;
  alpha_type?: string;
  universe_type?: string;
  schema_status?: string;
  is_template?: boolean;
  limit?: number;
};

export type SavedBacktestSpec = {
  ir_id: string;
  title: string;
  inserted?: boolean;
  is_template?: boolean;
  category?: string;
  spec?: Record<string, unknown>;
  notes?: string;
  ir_content_hash?: string | null;
  /** True when the save forked because the target spec already had backtest runs. */
  forked?: boolean;
  parent_ir_id?: string | null;
  parent_content_hash?: string | null;
  mutation_type?: string | null;
  changelog_notes?: string | null;
  runs_on_parent?: number;
};

export type SubmitBacktestRequest = {
  ir_id: string;
  start_date: string;
  end_date: string;
  immediate?: boolean;
  lean_project?: string;
  extra_env?: Record<string, string>;
};

export type SubmitBacktestResponse = {
  job_id: string;
  status: string;
  lean_project?: string;
  run_id?: string | null;
  [key: string]: unknown;
};

export type ExecutionHealth = {
  docker: boolean;
  lean_cli: boolean;
  clickhouse: boolean;
  worker_recent: boolean;
  ready: boolean;
  messages?: string[];
  docker_detail?: string;
  lean_cli_detail?: string;
  clickhouse_detail?: string;
  worker_detail?: string;
};

export type LeanProject = {
  id: string;
  label: string;
  lean_cli_name?: string;
  spec_kinds?: string[];
  enabled?: boolean;
  [key: string]: unknown;
};

export type ExecutionProjectsResponse = {
  projects: LeanProject[];
  registry_path?: string;
  note?: string;
  error?: string;
};

export type BacktestJobListItem = {
  job_id: string;
  ir_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status: BacktestJobStatus;
  runner_id?: string | null;
  submitted_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  lean_output_path?: string | null;
  error_message?: string | null;
  extra_env?: string | null;
  progress_pct?: number | null;
  current_sim_date?: string | null;
  elapsed_seconds?: number | null;
  estimated_remaining_seconds?: number | null;
  last_heartbeat?: string | null;
  last_log_line?: string | null;
  [key: string]: unknown;
};

export type BacktestJobLog = {
  job_id: string;
  log_path?: string | null;
  lines: string[];
  text: string;
  line_count?: number;
  error?: string;
};

export type BacktestJobStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "cancelled"
  | string;

export type BacktestJob = {
  job_id: string;
  status: BacktestJobStatus;
  error_message?: string | null;
  lean_output_path?: string | null;
  ir_id?: string | null;
  run_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  progress_pct?: number | null;
  current_sim_date?: string | null;
  elapsed_seconds?: number | null;
  estimated_remaining_seconds?: number | null;
  last_heartbeat?: string | null;
  last_log_line?: string | null;
  [key: string]: unknown;
};

export type VeraScreenerFrameworkOverrides = {
  max_positions?: number;
  stop_loss_pct?: number;
  max_weight?: number;
  target_atr_risk?: number;
};

export type HybridRsiFrameworkOverrides = {
  period?: number;
  maximum_drawdown_percent?: number;
};

export type FrameworkSlotType =
  | "UniverseSelection"
  | "Alpha"
  | "PortfolioConstruction"
  | "RiskManagement"
  | "Execution";

export type FrameworkModelConfig = {
  type: string;
  parameters: Record<string, unknown>;
};

export type FullFrameworkConfig = {
  universeSelection: FrameworkModelConfig;
  alpha: FrameworkModelConfig;
  portfolioConstruction: FrameworkModelConfig;
  riskManagement: FrameworkModelConfig;
  execution: FrameworkModelConfig;
};

export type LiveDeploymentSummary = {
  deployment_id: string;
  ir_id?: string | null;
  lean_environment?: string | null;
  brokerage?: string | null;
  status?: string | null;
  started_at?: string | null;
  stopped_at?: string | null;
  approval_backtest_run_id?: string | null;
  parameters?: string | null;
  created_at?: string | null;
};

export type LiveDeploymentStatus = {
  deployment?: LiveDeploymentSummary;
  latest_snapshot?: Record<string, unknown> | null;
  spec_summary?: Record<string, unknown> | null;
  approval_backtest_report?: BacktestReport | null;
  highlights?: string[];
};

export type LiveAccountProfile = {
  id: string;
  provider: string;
  data_provider: string;
  environment: "paper" | "live";
  display_name: string;
  account_identifier: string;
  active: boolean;
  credentials_configured: boolean;
  connection_verification_available: boolean;
  updated_at: string;
};

export type LiveAccountVerification = {
  supported: boolean;
  verified: boolean;
  message: string;
  account_status?: string;
  feed_verified: boolean;
};

export type LiveBrokerageDescriptor = {
  id: string;
  label: string;
  cli_name: string;
  default_data_provider: string;
  environments: Record<string, string>;
  environment_option?: string;
  environment_config?: string;
  credentials: Array<{ key: string; label: string; secret: boolean; required: boolean; choices?: string[] }>;
};

export type LiveDataProviderDescriptor = {
  id: string;
  label: string;
  cli_name: string;
  credentials: Array<{ key: string; label: string; secret: boolean; required: boolean; choices?: string[] }>;
};

export type LiveBrokerageCatalog = {
  brokerages: LiveBrokerageDescriptor[];
  data_providers: LiveDataProviderDescriptor[];
};

export type LocalRuntimeDeployment = {
  deployment_id?: string;
  ir_id?: string;
  approval_backtest_run_id?: string;
  project: string;
  mode: "paper" | "live" | "unknown";
  brokerage?: string;
  data_provider?: string;
  account_profile_id?: string;
  account_name?: string;
  account_identifier?: string;
  status: string;
  started_at?: string;
  stopped_at?: string;
  container_name?: string | null;
  container_status?: string;
  output_dir?: string;
  project_dir?: string;
  last_action?: string;
  metrics?: LeanLiveMetrics | null;
};

export type LeanLiveMetrics = {
  as_of: string;
  algorithm_id: string;
  runtime_statistics: Record<string, string>;
  summary_statistics: Record<string, string>;
  holdings: Array<{
    symbol: string;
    quantity?: number | string;
    average_price?: number | string;
    market_price?: number | string;
    market_value?: number | string;
    unrealized_pnl?: number | string;
  }>;
  recent_orders: Array<{
    id: string;
    symbol?: string;
    status?: string;
    type?: string;
    quantity?: number | string;
    price?: number | string;
    time?: string;
    updated_at?: string;
    filled_at?: string;
  }>;
};

export type LocalLiveRuntime = {
  enabled: boolean;
  mode: "paper" | "live" | "unknown";
  project: string;
  status: string;
  active_count: number;
  max_concurrent: number;
  deployments: LocalRuntimeDeployment[];
  deployment: LocalRuntimeDeployment | null;
};

export type LocalRuntimeActionResponse = { deployment: LocalRuntimeDeployment };

export type PromotionGateResult = {
  ok: boolean;
  run_id?: string;
  ir_id?: string;
  error?: string;
  code?: string;
  job_status?: string;
  run_summary?: {
    period_start?: string | null;
    period_end?: string | null;
    run_timestamp?: string | null;
    total_return?: number | null;
    annual_return?: number | null;
    sharpe_ratio?: number | null;
    max_drawdown?: number | null;
  };
  metrics?: BacktestReportMetrics;
  highlights?: string[];
  warnings?: string[];
};

export type RegisterPaperDeploymentResponse = {
  deployment_id: string;
  ir_id: string;
  lean_environment?: string;
  brokerage?: string;
  status?: string;
  started_at?: string;
  approval_backtest_run_id?: string;
  promotion_gate?: PromotionGateResult;
};

/** Editable filter row for the Applied Filters ALL-group UI. */
export type AppliedFilterRow = {
  id: string;
  op: ComparisonOp;
  left: IrOperand;
  right: IrOperand;
  /** True when node is not a simple comparison (display-only). */
  readOnly?: boolean;
  raw?: IrWhereNode;
  /** Agent/user provenance for chip "why" UI. */
  annotation?: {
    source?: "agent" | "user";
    action?: "added" | "modified" | "removed";
    rationale?: string;
    probe_ref?: Record<string, unknown> | null;
    at?: string;
  };
};

/**
 * A Deepvue-style filter group. The first group is always `all` (every row must
 * match); each subsequent group is `any` (at least one row must match). The
 * screen as a whole is `all(group1…) AND any(group2…) AND any(group3…)…`.
 */
export type AppliedFilterGroup = {
  id: string;
  name?: string;
  logic: "all" | "any";
  rows: AppliedFilterRow[];
  /** One nest of groups (Universe screen tree). Inner groups have no children. */
  children?: AppliedFilterGroup[];
};

export type MonthlyReturnsMatrix = Record<string, Record<string, number>>;

export type MonthlyReturnsResponse = {
  run_id: string;
  years: number[];
  matrix: MonthlyReturnsMatrix;
  total_months: number;
  win_months: number;
  win_rate_months: number;
  error?: string | null;
};

export type TradeStatistics = {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  expectancy: number;
  average_profit: number;
  average_loss: number;
  largest_profit: number;
  largest_loss: number;
  average_trade_duration: string;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  average_mae: number;
  average_mfe: number;
  largest_mae: number;
  largest_mfe: number;
};

export type TradeExcursionPoint = {
  id: string;
  symbol: string;
  profit_loss: number;
  return_pct: number;
  mae: number;
  mfe: number;
  mae_pct: number;
  mfe_pct: number;
  is_win: boolean;
  exit_time: string;
};

export type TradeAnalyticsResponse = {
  run_id: string;
  trade_statistics: TradeStatistics;
  excursions: TradeExcursionPoint[];
  count: number;
  error?: string | null;
};

export type ClosedTradeItem = {
  id: string;
  symbol: string;
  entry_time: string;
  exit_time?: string | null;
  entry_price: number;
  exit_price?: number | null;
  current_price?: number | null;
  direction: string;
  quantity: number;
  profit_loss: number;
  return_pct: number;
  total_fees?: number;
  mae?: number;
  mfe?: number;
  duration?: string;
  is_win: boolean;
  status?: "CLOSED" | "OPEN";
};

export type OpenTradeItem = ClosedTradeItem;

export type ClosedTradesResponse = {
  run_id: string;
  source?: string | null;
  trades: ClosedTradeItem[];
  open_trades?: ClosedTradeItem[];
  count: number;
  open_count?: number;
  truncated: boolean;
  total: number;
  error?: string | null;
};

export type MultiRunCompareMetrics = {
  total_return?: number | null;
  annual_return?: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  max_drawdown?: number | null;
  win_rate?: number | null;
  profit_factor?: number | null;
  expectancy?: number | null;
  total_orders?: number | null;
  total_trades?: number | null;
  total_fees?: number | null;
  start_equity?: number | null;
  end_equity?: number | null;
  max_consecutive_wins?: number | null;
  max_consecutive_losses?: number | null;
};

export type MultiRunComparePoint = {
  t: number;
  equity: number;
  normalized: number;
};

export type MultiRunCompareRunItem = {
  run_id: string;
  ir_id?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  run_timestamp?: string | null;
  metrics: MultiRunCompareMetrics;
  points: MultiRunComparePoint[];
  point_count: number;
};

export type MultiRunCompareResponse = {
  runs: MultiRunCompareRunItem[];
  count: number;
  error?: string | null;
};

export type SectorAttribution = {
  sector: string;
  total_pnl: number;
  total_trades: number;
  win_trades: number;
  win_rate: number;
  profit_factor: number | null;
  avg_return_pct: number;
  symbols: string[];
};

export type IndustryAttribution = {
  industry: string;
  sector: string;
  total_pnl: number;
  total_trades: number;
  win_trades: number;
  win_rate: number;
  profit_factor: number | null;
};

export type RegimeAttribution = {
  regime: string;
  description: string;
  total_pnl: number;
  total_trades: number;
  win_trades: number;
  win_rate: number;
  profit_factor: number | null;
  avg_return_pct: number;
  expectancy: number | null;
};

export type AttributionResponse = {
  run_id: string;
  sectors: SectorAttribution[];
  industries: IndustryAttribution[];
  regimes: RegimeAttribution[];
  summary: {
    total_pnl: number;
    total_trades: number;
    top_sector: string;
    top_sector_pnl: number;
    best_regime: string;
  };
  error?: string | null;
};

export type CandleBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  closeadj?: number;
};

export type TickerCandlesResponse = {
  ticker: string;
  meta?: {
    name?: string;
    sector?: string;
    industry?: string;
    category?: string;
  };
  candles: CandleBar[];
  count: number;
  source?: string;
  error?: string | null;
};

export type OptimizerConstraint = {
  target: string;
  operator: "lessOrEqual" | "greaterOrEqual" | "equals";
  target_value: number;
};

export type OptimizerSessionSummary = {
  session_id: string;
  strategy_id: string;
  base_ir_id: string;
  title: string;
  objective: string;
  param_x_name: string;
  param_x_values: number[];
  param_y_name?: string | null;
  param_y_values: number[];
  total_combinations: number;
  status: string;
  strategy_type?: "euler" | "grid" | string;
  oos_days?: number;
  constraints?: OptimizerConstraint[];
  best_run_id?: string | null;
  best_score?: number | null;
  best_parameters?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type OptimizerRunPoint = {
  run_id: string;
  ir_id: string;
  total_return: number;
  annual_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  total_orders: number;
  score: number;
  parameters: Record<string, unknown>;
  euler_generation?: number;
  stability_score?: number;
  passes_constraints?: boolean;
  oos_sharpe_ratio?: number | null;
  oos_efficiency?: number | null;
};

export type OptimizerHeatmapData = {
  param_x_name: string;
  param_x_values: number[];
  param_y_name?: string | null;
  param_y_values: number[];
  sharpe_matrix: Array<Array<number | null>>;
  return_matrix: Array<Array<number | null>>;
  drawdown_matrix: Array<Array<number | null>>;
  run_id_matrix: Array<Array<string | null>>;
};

export type OptimizerSessionHeatmapResponse = {
  session: OptimizerSessionSummary;
  completed_runs: number;
  total_combinations: number;
  is_done: boolean;
  best_run?: OptimizerRunPoint | null;
  heatmap: OptimizerHeatmapData;
  pareto_frontier: OptimizerRunPoint[];
  all_points: OptimizerRunPoint[];
  error?: string | null;
};

export type LaunchOptimizerRequest = {
  base_ir_id: string;
  start_date: string;
  end_date: string;
  param_x_name: string;
  param_x_values: number[];
  param_y_name?: string;
  param_y_values?: number[];
  title?: string;
  objective?: string;
  strategy_type?: "euler" | "grid";
  oos_days?: number;
  constraints?: OptimizerConstraint[];
  max_concurrent?: number;
  lean_project?: string;
};

export type EvaluationStrategyType = "baseline" | "optimization_sweep";

export interface SweepParamRange {
  name: string;
  label?: string;
  target_slot?: "Alpha" | "Risk" | "Portfolio" | "Execution" | "Universe";
  min: number;
  max: number;
  step: number;
}

export interface OptimizationSweepConfig {
  strategy_type: "euler" | "grid";
  objective: "sharpe_ratio" | "sortino_ratio" | "total_return" | "calmar_ratio" | "min_drawdown";
  param_x: SweepParamRange;
  param_y?: SweepParamRange;
  use_param_y: boolean;
  constraints: OptimizerConstraint[];
  max_concurrent: number;
}

export function normalizeSearchStrategy(raw: string | undefined | null): "euler" | "grid" {
  return raw === "grid" ? "grid" : "euler";
}

export interface WalkForwardConfig {
  train_window_months: number;
  test_window_months: number;
  step_months: number;
  anchored: boolean;
}

export interface EvaluationConfig {
  strategy: EvaluationStrategyType;
  start_date: string;
  end_date: string;
  initial_cash: number;
  benchmark: string;
  sweep?: OptimizationSweepConfig;
}

export interface TrendTemplateItem {
  id: string;
  label: string;
  passed: boolean;
  desc: string;
}

export interface TrendTemplateChecklist {
  score: string;
  passed_count: number;
  all_passed: boolean;
  items: TrendTemplateItem[];
}

export interface ChartCandlePoint {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma10?: number | null;
  sma20?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  ema21?: number | null;
  rs_rating?: number | null;
  rs_line?: number | null;
  rs_line_ema21?: number | null;
  eps_trailing_12m?: number | null;
  eps_line_val?: number | null;
  fair_value_15pe?: number | null;
  normal_pe_val?: number | null;
  pe_10_0?: number | null;
  pe_12_5?: number | null;
  pe_15_0?: number | null;
  pe_17_5?: number | null;
  pe_20_0?: number | null;
  pe_25_0?: number | null;
  pe_normal?: number | null;
  ghost_fair_value_15pe?: number | null;
  ghost_normal_pe?: number | null;
  ghost_pe_10_0?: number | null;
  ghost_pe_12_5?: number | null;
  ghost_pe_15_0?: number | null;
  ghost_pe_17_5?: number | null;
  ghost_pe_20_0?: number | null;
  ghost_pe_25_0?: number | null;
  ghost_pe_normal?: number | null;
  fwd_track_1y?: number | null;
  fwd_track_2y?: number | null;
  fair_value_price?: number | null;
  fv_band_p30?: number | null;
  fv_band_p10?: number | null;
  fv_band_m10?: number | null;
  fv_band_m30?: number | null;
  is_earnings_report?: boolean;
  earnings_growth_yoy?: number | null;
  revenue_growth_yoy?: number | null;
  spy_close?: number | null;
  is_future: boolean;
  is_forecast?: boolean;
}

export interface ValuationForecastSummary {
  growth_rate_pct: number;
  fwd_eps_1y: number;
  fwd_eps_2y: number;
  target_price_15x: number;
  target_price_normal_pe: number;
  fwd_cagr_2y_normal_pe: number;
  fwd_cagr_2y_15x: number;
  fwd_peg_ratio: number;
  historical_median_pe: number;
  ttm_eps: number;
  fair_value_price?: number;
  valuation_spread_pct?: number;
  valuation_status?: string;
}

export interface ForwardOutcomeStats {
  forward_sessions_available: number;
  return_5d_pct: number | null;
  return_20d_pct: number | null;
  return_60d_pct: number | null;
  return_250d_pct: number | null;
  max_gain_pct: number | null;
  max_loss_pct: number | null;
}

export type BeatMissStatus = "beat" | "miss" | "in_line" | "unreported";

export interface QuarterlyGrowthPoint {
  report_date: string;
  revenue_m: number | null;
  eps: number | null;
  gross_margin_pct: number | null;
  net_margin_pct: number | null;
  revenue_growth_yoy: number | null;
  eps_growth_yoy: number | null;
  is_estimate?: boolean;
  surprise_pct?: number | null;
  eps_actual?: number | null;
  eps_estimate?: number | null;
  eps_surprise_dollar?: number | null;
  eps_surprise_pct?: number | null;
  eps_beat_miss?: BeatMissStatus | null;
  revenue_actual?: number | null;
  revenue_estimate?: number | null;
  revenue_surprise_m?: number | null;
  revenue_surprise_pct?: number | null;
  revenue_beat_miss?: BeatMissStatus | null;
}

export interface EarningsReportEvent {
  date: string;
  eps: number | null;
  eps_growth_yoy: number | null;
  revenue_m: number | null;
  revenue_growth_yoy: number | null;
  is_future: boolean;
  surprise_pct?: number | null;
}

export interface AnnualGrowthPoint {
  year: string;
  eps: number | null;
  eps_actual?: number | null;
  eps_estimate?: number | null;
  eps_beat_miss?: BeatMissStatus | null;
  eps_chg_pct: number | null;
  sales_m: number | null;
  sales_actual?: number | null;
  sales_estimate?: number | null;
  sales_beat_miss?: BeatMissStatus | null;
  revenue_actual?: number | null;
  revenue_estimate?: number | null;
  revenue_beat_miss?: BeatMissStatus | null;
  sales_chg_pct: number | null;
  is_estimate: boolean;
}

export interface ForecastCalibrationData {
  has_realized_history: boolean;
  forward_sessions_evaluated: number;
  origin_date: string;
  origin_price: number;
  projected_eps_1y: number;
  actual_eps_1y: number | null;
  eps_beat_1y_pct: number | null;
  projected_eps_2y: number;
  actual_eps_2y: number | null;
  eps_beat_2y_pct: number | null;
  projected_target_normal_pe: number;
  actual_peak_price: number | null;
  actual_latest_price: number | null;
  target_achieved_pct: number | null;
  expected_cagr_2y: number;
  realized_cagr: number | null;
  calibration_score_pct: number | null;
  max_gain_mfe_pct: number | null;
  max_loss_mae_pct: number | null;
}

export interface IndustryPeerComp {
  ticker: string;
  company_name: string;
  peer_group?: string;
  close: number;
  rs_rating: number | null;
  growth_rate_pct: number | null;
  historical_median_pe: number;
  target_price_15x: number | null;
  target_price_normal_pe: number | null;
  fwd_cagr_2y_normal_pe: number | null;
  valuation_spread_pct: number | null;
  valuation_status: string;
}

export interface StockIntrospectionData {
  ticker: string;
  as_of: string;
  company_name: string;
  sector: string;
  industry: string;
  exchange: string;
  historical_median_pe?: number;
  valuation_forecast?: ValuationForecastSummary;
  as_of_kpis: Record<string, any>;
  trend_template: TrendTemplateChecklist;
  forward_stats: ForwardOutcomeStats;
  forecast_calibration?: ForecastCalibrationData;
  quarterly_growth: QuarterlyGrowthPoint[];
  annual_growth?: AnnualGrowthPoint[];
  earnings_events?: EarningsReportEvent[];
  industry_peers?: IndustryPeerComp[];
  chart_series: ChartCandlePoint[];
}

export interface DrawdownPoint {
  t: number;
  date: string;
  equity: number;
  peak: number;
  drawdown_pct: number;
}

export interface DrawdownEpisode {
  peak_date: string;
  peak_equity: number;
  trough_date: string;
  trough_equity: number;
  depth_pct: number;
  recovery_date: string | null;
  duration_days: number;
  status: "Recovered" | "Active";
}

export interface DrawdownAnalyticsResponse {
  run_id: string;
  series: DrawdownPoint[];
  episodes: DrawdownEpisode[];
  max_drawdown: number;
  current_drawdown: number;
  count: number;
  error?: string | null;
}

export interface BenchmarkDataPoint {
  date: string;
  strategy_equity: number;
  strategy_normalized: number;
  benchmark_price: number;
  benchmark_normalized: number;
}

export interface ActiveRiskMetrics {
  strategy_total_return: number;
  benchmark_total_return: number;
  beta: number;
  alpha_annualized: number;
  correlation: number;
  up_market_capture: number;
  down_market_capture: number;
  tracking_error: number;
  information_ratio: number;
  var_95: number;
  cvar_95: number;
}

export interface BenchmarkComparisonResponse {
  run_id: string;
  benchmark: string;
  series: BenchmarkDataPoint[];
  metrics: ActiveRiskMetrics;
  count: number;
  error?: string | null;
}

export interface AssetAllocationItem {
  symbol: string;
  traded_volume: number;
  volume_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  realized_pnl: number;
  avg_duration_days: number;
}

export interface AssetAllocationResponse {
  run_id: string;
  total_volume: number;
  total_pnl: number;
  symbol_count: number;
  items: AssetAllocationItem[];
  error?: string | null;
}

export interface PortfolioExposurePoint {
  date: string;
  equity: number;
  long_value: number;
  cash_value: number;
  long_pct: number;
  cash_pct: number;
  holdings_count: number;
}

export interface PortfolioExposureResponse {
  run_id: string;
  series: PortfolioExposurePoint[];
  count: number;
  max_holdings: number;
  avg_long_pct: number;
  estimated_capacity_m: number;
  error?: string | null;
}

export interface RollingStatsSummaryMatrix {
  sharpe: Record<string, number | string>;
  win_rate: Record<string, string>;
  volatility: Record<string, string>;
  beta: Record<string, number | string>;
}

export interface RollingStatsPoint {
  date: string;
  [key: string]: string | number;
}

export interface RollingStatsResponse {
  run_id: string;
  summary_matrix: RollingStatsSummaryMatrix;
  rolling_series: RollingStatsPoint[];
  count: number;
  error?: string | null;
}
