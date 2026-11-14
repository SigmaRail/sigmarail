import type { IrOperand } from "../../types";
import type { RuleSpec } from "../../lib/rulesAst";

/** Staged pipeline strategy document types (mirror of vera_query_core.strategy.pipeline). */

export type StageMode =
  | "filter"
  | "score"
  | "signal"
  | "confirm"
  | "watch"
  | "pyramid"
  | "hedge"
  | "exit";

export type ModelRef = {
  type: string;
  parameters?: Record<string, unknown>;
};

export type FilterCondition = {
  op: "gt" | "gte" | "lt" | "lte" | "eq" | "neq";
  left: string | IrOperand;
  right: number | string | boolean | IrOperand;
  right_kind?: "lit" | "col" | "formula";
  expr?: string | null;
  /** Stable chip id for agent patch ops. */
  id?: string | null;
  /** UI/agent provenance; stripped before SQL WHERE. */
  annotation?: {
    source?: "agent" | "user";
    action?: "added" | "modified" | "removed";
    rationale?: string;
    probe_ref?: Record<string, unknown> | null;
    at?: string;
  } | null;
};

export type FilterGroup = {
  logic: "and" | "or";
  name?: string;
  conditions: FilterNode[];
};

/**
 * A negated filter subtree — the document's own `not`.
 *
 * The compiled where-AST has always allowed `not`, but the document could only hold `neq`
 * (`not(eq(...))`); any other negation was rebuilt as a *positive* AND of its child, so
 * "not above the 50-day" loaded back as "above the 50-day".
 */
export type FilterNot = {
  item: FilterNode;
};

export type FilterNode = FilterCondition | FilterGroup | FilterNot;
export type FilterTree = FilterNode;

export function isFilterGroup(node: FilterNode): node is FilterGroup {
  return "logic" in node && Array.isArray(node.conditions);
}

export function isFilterNot(node: FilterNode): node is FilterNot {
  return !isFilterGroup(node) && "item" in node;
}

export type FactorWeight = {
  name: string;
  weight: number;
};

export type SelectionRule = {
  method: "top_n" | "top_n_per_sector" | "threshold";
  n?: number;
  sectors?: number;
  per_sector?: number;
  min_score?: number;
};

export type EntryTriggerType =
  | "pivot_breakout"
  | "pullback_to_sma"
  | "vcp_complete"
  | "rsi_cross"
  | "macd"
  | "ema_cross"
  | "breakout";

export type EntryTrigger = {
  type: EntryTriggerType;
  lookback_days?: number;
  volume_multiplier?: number;
  consolidation_days?: number;
  volume_surge_multiplier?: number;
  leader_rs_threshold?: number;
  sma_period?: number;
  max_deviation_pct?: number;
  contraction_count?: number;
  period?: number;
  fast_period?: number;
  slow_period?: number;
  signal_period?: number;
  oversold?: number;
  overbought?: number;
};

export type StopLossRule = {
  type: "atr" | "fixed_pct";
  multiplier?: number;
  pct?: number;
  initial_risk_pct?: number;
};

export type PyramidPhase = {
  name: string;
  size_pct: number;
  risk_pct?: number;
  trigger?: Record<string, unknown>;
};

export type ExitTranche = {
  trigger_r: number;
  sell_pct: number;
  stop_ratchet?: string;
};

export type HedgeInstrument = {
  ticker: string;
  max_allocation: number;
};

export type HedgeConfig = {
  instruments: HedgeInstrument[];
  trigger?: "regime_risk_off";
  unwind?: Record<string, unknown> | null;
};

export type RiskRuleType =
  | "progressive"
  | "trailing"
  | "max_drawdown"
  | "sector_exposure";

export type RiskRule = {
  type: RiskRuleType;
  take_profit_r?: number;
  trailing_stop_pct?: number;
  max_holding_days?: number;
  maximum_drawdown_percent?: number;
  maximum_sector_exposure?: number;
};

export type RiskConfig = {
  circuit_breaker?: Record<string, unknown> | null;
  /** Deprecated home — kept for reading pre-migration docs; new writes go to PipelineDocument.regime_gate. */
  regime_gate?: Record<string, unknown> | null;
  max_positions?: number | null;
  max_sector_exposure?: number | null;
  rules?: RiskRule[];
  model?: ModelRef | null;
  time_stop_skip_if?: Record<string, unknown> | null;
};

/** Bool/number SlotExpr over computed + L7 (+ pos.* for Risk). */
export type SlotExpr = {
  kind: "bool" | "number";
  where?: Record<string, unknown> | null;
  expr?: Record<string, unknown> | null;
};

export type PipelineBindings = {
  alpha_eligibility?: SlotExpr | null;
  alpha_setup?: SlotExpr | null;
  alpha_rank?: string[] | null;
  /** Optional ASC/DESC per alpha_rank field (default desc). */
  alpha_rank_directions?: Record<string, "asc" | "desc"> | null;
  alpha_confidence?: SlotExpr | null;
  /** Int8 measure: 1 Up / -1 Down / 0 Flat */
  alpha_direction?: SlotExpr | null;
  alpha_magnitude?: SlotExpr | null;
  alpha_weight?: SlotExpr | null;
  /** Insight.Period days (default 1). */
  alpha_insight_period_days?: number | null;
  pcm_scale?: SlotExpr | null;
  pcm_allow_entry?: SlotExpr | null;
  risk_skip_time_stop?: SlotExpr | null;
  risk_allow_pyramid_add?: SlotExpr | null;
};

export type PolicyRuleRole =
  | "alpha_eligibility"
  | "alpha_setup"
  | "alpha_confidence"
  | "pcm_allow_entry"
  | "pcm_scale"
  | "risk_skip_time_stop"
  | "risk_allow_pyramid_add";

/** One policy-rule chain link (Studio SSOT). */
export type PolicyRule = {
  id: string;
  label?: string | null;
  role: PolicyRuleRole;
  slot: SlotExpr;
};

/** when → set allowlisted PCM/Risk knobs (last-wins). */
export type PolicyOverride = {
  id: string;
  label?: string | null;
  when: SlotExpr;
  set: Record<string, number | boolean>;
};

export const POLICY_OVERRIDE_KEYS = [
  "risk_per_trade_pct",
  "max_position_weight",
  "trailing_stop_pct",
  "atr_stop_multiplier",
  "breakeven_time_stop_days",
  "max_holding_days",
] as const;

export type ExecutionType = "market_order" | "vwap" | "std_dev" | "immediate";

export type ExecutionConfig = {
  type?: ExecutionType;
  fill_session?: "moo" | "moc";
  model?: ModelRef | null;
};

export type UniverseSource = "screener" | "manual" | "composite";

export type UniverseConfig = {
  source?: UniverseSource;
  symbols?: string[];
  select?: string[];
  screen?: FilterNode[];
  limit_per_day?: number;
  model?: ModelRef | null;
};

export type SizingPolicy =
  | "atr_risk"
  | "risk_budgeted"
  | "risk_parity"
  | "confidence_weighted"
  | "equal_weight";

export type SizingConfig = {
  policy?: SizingPolicy;
  max_positions?: number | null;
  max_weight?: number | null;
  min_weight?: number | null;
  target_atr_risk?: number | null;
  risk_per_trade_pct?: number | null;
  rebalance?: string | null;
  use_regime_scaling?: boolean | null;
  min_regime_fraction?: number | null;
  regime_neutral_fraction?: number | null;
  regime_bull_fraction?: number | null;
  scaled_max_positions_floor?: number | null;
  honor_insight_confidence?: boolean | null;
  allow_adds_on_invested?: boolean | null;
  default_stop_loss_pct?: number | null;
  enable_surrogates?: boolean | null;
  surrogate_sizing_mode?: "dollar_risk_parity" | "full_notional" | null;
  prefer_capital_efficient_surrogates?: boolean | null;
  min_surrogate_adv?: number | null;
  /** Unified rules pass (Phase 2, C-FW-RULES): ordered rule table over insight candidates
   *  + insight-quiet holdings — compiles to Framework.PortfolioConstruction.Parameters.rules. */
  rules?: RuleSpec[];
  /** Base sizing Operand AST — target = size_expr × action.size_scale (enter/add). */
  size_expr?: Record<string, unknown> | null;
  /** Book-level ASTs (Phase 3, C-FW-RULES) — evaluated once per PCM pass:
   *  scale_expr → regime.scale, slots_expr → acct.scaled_max_positions,
   *  order_expr → unit ordering key. Compile to PCM Parameters of the same names. */
  scale_expr?: Record<string, unknown> | null;
  slots_expr?: Record<string, unknown> | null;
  order_expr?: Record<string, unknown> | null;
  model?: ModelRef | null;
};

export type StageDocumentation = {
  purpose?: string;
  inputs?: string[];
  expression?: string;
  variables?: Record<string, string>;
  confirmation?: string;
  effect?: string;
  notes?: string;
};

export type Stage = {
  name: string;
  id?: string | null;
  mode: StageMode;
  depends_on?: string | null;
  filters?: FilterTree[];
  factors?: FactorWeight[];
  selection?: SelectionRule | null;
  entry_triggers?: EntryTrigger[];
  phases?: PyramidPhase[];
  tranches?: ExitTranche[];
  instruments?: HedgeInstrument[];
  max_candidates?: number | null;
  max_positions?: number | null;
  stop_loss?: StopLossRule | null;
  max_hold_days?: number | null;
  trailing_stop_pct?: number | null;
  stop_cooldown_days?: number | null;
  add_trigger_pct?: number | null;
  atr_stop_multiplier?: number | null;
  max_stop_loss_pct?: number | null;
  use_atr_stops?: boolean | null;
  breakeven_time_stop_days?: number | null;
  max_single_weight?: number | null;
  breakeven_r_trigger?: number | null;
  as_gate?: boolean;
  count_as_signal?: boolean;
  /** Optional weight when a weighted sum measure references this gate (default 1). */
  signal_weight?: number;
  /** Number Operand AST → Universe.computed[] kind=number (aggregate measures / L7). */
  computed_expr?: Record<string, unknown> | null;
  /** Optional measure filter → Universe.post_where (not ORDER BY). */
  measure_filter?: FilterCondition | null;
  optional_score_fields?: string[];
  optional_min?: Record<string, number>;
  omit_tt?: boolean;
  require_flag?: string;
  /** Ordered rule-driven control flow (Phase 1, C-FW-RULES): compiles to Framework.<Slot>.Parameters.rules. */
  rules?: RuleSpec[];
  /** Initial-stop Operand AST (C-VERA-EXPR-V2): compiles to Framework.RiskManagement.Parameters.init_stop. */
  init_stop?: Record<string, unknown> | null;
  documentation?: StageDocumentation;
};

export type PipelineDocumentation = {
  description?: string;
  purpose?: string;
  assumptions?: string[];
  variables?: Record<string, string>;
  risks?: string[];
  version?: string;
};

export type PipelineDocument = {
  strategy_name: string;
  stages: Stage[];
  gate_combine?: "union" | "count" | string;
  min_screens?: number | null;
  /** Alpha entry gate: skip names whose trailing ATR% exceeds this (0 = off). */
  max_entry_atr_pct?: number | null;
  universe?: UniverseConfig;
  sizing?: SizingConfig;
  alpha?: ModelRef | null;
  hedge?: HedgeConfig | null;
  risk?: RiskConfig;
  execution?: ExecutionConfig;
  documentation?: PipelineDocumentation;
  bindings?: PipelineBindings | null;
  policy_rules?: PolicyRule[];
  policy_overrides?: PolicyOverride[];
  /** Cross-slot regime policy (compiles to DataSources.regime + uses[] routed to PCM/Alpha — not Risk-owned). */
  regime_gate?: Record<string, unknown> | null;
};

export type FactorInfo = {
  column: string;
  table: string;
  direction: string;
  description: string;
};

export type StrategyPreset = {
  id: string;
  name: string;
  stages: string[];
  description?: string;
  tags?: string[];
  status?: "active" | "deprecated" | "draft";
  screener_template_id?: string;
};

function isEmptyStageDocumentation(doc?: StageDocumentation): boolean {
  if (!doc) return true;
  return (
    !doc.purpose &&
    !doc.expression &&
    !doc.confirmation &&
    !doc.effect &&
    !doc.notes &&
    !(doc.inputs && doc.inputs.length) &&
    !(doc.variables && Object.keys(doc.variables).length)
  );
}

function isEmptyPipelineDocumentation(doc?: PipelineDocumentation): boolean {
  if (!doc) return true;
  return (
    !doc.description &&
    !doc.purpose &&
    !doc.version &&
    !(doc.assumptions && doc.assumptions.length) &&
    !(doc.variables && Object.keys(doc.variables).length) &&
    !(doc.risks && doc.risks.length)
  );
}

/** Drop empty stage/pipeline documentation so saves stay compact. */
export function omitEmptyDocumentation(doc: PipelineDocument): PipelineDocument {
  const stages = doc.stages.map((stage) => {
    if (!isEmptyStageDocumentation(stage.documentation)) return stage;
    const { documentation: _omit, ...rest } = stage;
    return rest;
  });
  if (!isEmptyPipelineDocumentation(doc.documentation)) {
    return { ...doc, stages };
  }
  const { documentation: _omit, ...rest } = doc;
  return { ...rest, stages };
}

export type AllocationPolicy = {
  base?: "weights" | "risk_parity" | "hrp" | "black_litterman";
  weights?: Record<string, number>;
  regime?: {
    signal?: string;
    map?: Record<string, Record<string, number>>;
    global_exposure?: Record<string, number> | null;
  } | null;
  performance?: {
    metric?: string;
    lookback_days?: number;
    floor?: number;
    ceiling?: number;
    rebalance_days?: number;
  } | null;
  vol_target?: { target_vol?: number; band?: number } | null;
};

export type PortfolioDocument = {
  name: string;
  legs: PipelineDocument[];
  allocation?: AllocationPolicy;
};
