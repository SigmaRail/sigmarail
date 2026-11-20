/** Bind Strategy View PCM / Risk / Execution knobs to the pipeline document. */

import type { ExitTranche, PipelineDocument, PyramidPhase, Stage } from "../components/strategy/StrategyDocument";
import type { RuleSpec } from "./rulesAst";
import { normalizeOperandAst, parseRules } from "./rulesAst";

export const ALPHA_ADD_MODES = ["score", "signal", "pyramid"] as const;

export type FillSession = "moo" | "moc";

export const DAILY_MARKET_EXECUTION = { type: "market_order" as const };

export const CHAMPION_EXIT_TRANCHES: ExitTranche[] = [
  { trigger_r: 2.5, sell_pct: 0.2 },
  { trigger_r: 4.5, sell_pct: 0.33 },
  { trigger_r: 8.0, sell_pct: 0.33 },
];

export const DEFAULT_PYRAMID_PHASES: PyramidPhase[] = [
  { name: "test", size_pct: 0.5 },
  { name: "add", size_pct: 0.25 },
  { name: "full", size_pct: 0.25 },
];

export function ensurePyramidStage(stages: Stage[]): { stages: Stage[]; index: number } {
  const idx = stages.findIndex((s) => s.mode === "pyramid");
  if (idx >= 0) return { stages, index: idx };
  const next: Stage = {
    mode: "pyramid",
    name: "Scale-in (pyramid)",
    add_trigger_pct: 0.08,
    phases: [...DEFAULT_PYRAMID_PHASES],
  };
  return { stages: [...stages, next], index: stages.length };
}

export type PyramidKnobs = {
  addTriggerPct: number;
  phases: PyramidPhase[];
};

export function pyramidFromDoc(doc: PipelineDocument): PyramidKnobs {
  const pyr = (doc.stages ?? []).find((s) => s.mode === "pyramid");
  return {
    addTriggerPct: pyr?.add_trigger_pct ?? 0.08,
    phases: pyr?.phases?.length ? pyr.phases : [...DEFAULT_PYRAMID_PHASES],
  };
}

export function patchPyramid(doc: PipelineDocument, patch: Partial<PyramidKnobs>): PipelineDocument {
  const cur = pyramidFromDoc(doc);
  const next = { ...cur, ...patch };
  const ens = ensurePyramidStage(doc.stages ?? []);
  const stages = ens.stages.map((s, i) =>
    i === ens.index
      ? {
          ...s,
          mode: "pyramid" as const,
          add_trigger_pct: next.addTriggerPct,
          phases: next.phases,
        }
      : s,
  );
  return { ...doc, stages };
}

export function scoreRankingEditorsHidden(gateCombine?: string | null): boolean {
  return gateCombine === "count";
}

export function fillSessionFromDoc(doc: PipelineDocument): FillSession {
  return doc.execution?.fill_session === "moc" ? "moc" : "moo";
}

function withDailyMarket(
  doc: PipelineDocument,
  fillSession?: FillSession,
): PipelineDocument["execution"] {
  return {
    ...(doc.execution ?? {}),
    ...DAILY_MARKET_EXECUTION,
    fill_session: fillSession ?? fillSessionFromDoc(doc),
  };
}

export function patchFillSession(doc: PipelineDocument, fillSession: FillSession): PipelineDocument {
  return {
    ...doc,
    execution: withDailyMarket(doc, fillSession),
  };
}

export type PcmKnobs = {
  riskPerTrade: number;
  maxWeight: number;
  maxPositions: number;
  honorInsightConfidence: boolean;
  allowAddsOnInvested: boolean;
  defaultStopLossPct: number;
  rebalance?: string;
  minRegimeFraction: number;
  // Compat-dead round-trip fields — accepted on old stored specs, never read by
  // the runtime (dead in the legacy procedural PCM too; see SLOT_PIPELINE_GUIDE §4).
  // No Studio controls write meaningful behavior through these.
  regimeNeutralFraction: number;
  regimeBullFraction: number;
  scaledMaxPositionsFloor: number;
  enableSurrogates?: boolean;
  surrogateSizingMode?: "dollar_risk_parity" | "full_notional";
  preferCapitalEfficientSurrogates?: boolean; // compat-dead — see above
  minSurrogateAdv?: number;
};

export function pcmFromDoc(doc: PipelineDocument): PcmKnobs {
  return {
    riskPerTrade: doc.sizing?.risk_per_trade_pct ?? 0.005,
    maxWeight: doc.sizing?.max_weight ?? 0.25,
    maxPositions: doc.sizing?.max_positions ?? doc.risk?.max_positions ?? 10,
    honorInsightConfidence: doc.sizing?.honor_insight_confidence ?? true,
    allowAddsOnInvested: doc.sizing?.allow_adds_on_invested ?? true,
    defaultStopLossPct: doc.sizing?.default_stop_loss_pct ?? 0.08,
    rebalance: doc.sizing?.rebalance ?? "weekly",
    minRegimeFraction: doc.sizing?.min_regime_fraction ?? 0.15,
    regimeNeutralFraction: doc.sizing?.regime_neutral_fraction ?? 0.5,
    regimeBullFraction: doc.sizing?.regime_bull_fraction ?? 1.0,
    scaledMaxPositionsFloor: doc.sizing?.scaled_max_positions_floor ?? 2,
    enableSurrogates: doc.sizing?.enable_surrogates ?? false,
    surrogateSizingMode: doc.sizing?.surrogate_sizing_mode ?? "dollar_risk_parity",
    preferCapitalEfficientSurrogates: doc.sizing?.prefer_capital_efficient_surrogates ?? true,
    minSurrogateAdv: doc.sizing?.min_surrogate_adv ?? 5_000_000,
  };
}

export function patchPcm(doc: PipelineDocument, patch: Partial<PcmKnobs>): PipelineDocument {
  const cur = pcmFromDoc(doc);
  const next = { ...cur, ...patch };
  return {
    ...doc,
    sizing: {
      ...(doc.sizing ?? {}),
      policy: "risk_budgeted",
      risk_per_trade_pct: next.riskPerTrade,
      max_weight: next.maxWeight,
      max_positions: next.maxPositions,
      honor_insight_confidence: next.honorInsightConfidence,
      allow_adds_on_invested: next.allowAddsOnInvested,
      default_stop_loss_pct: next.defaultStopLossPct,
      rebalance: next.rebalance,
      min_regime_fraction: next.minRegimeFraction,
      regime_neutral_fraction: next.regimeNeutralFraction,
      regime_bull_fraction: next.regimeBullFraction,
      scaled_max_positions_floor: next.scaledMaxPositionsFloor,
      enable_surrogates: next.enableSurrogates,
      surrogate_sizing_mode: next.surrogateSizingMode,
      prefer_capital_efficient_surrogates: next.preferCapitalEfficientSurrogates,
      min_surrogate_adv: next.minSurrogateAdv,
    },
    risk: {
      ...(doc.risk ?? {}),
      max_positions: next.maxPositions,
    },
    execution: withDailyMarket(doc),
  };
}

export type ProgressiveKnobs = {
  tranches: ExitTranche[];
  trailingStopPct: number;
  maxHoldDays: number;
  regimeOn: boolean;
  regimeUses: string[];
  atrStopMultiplier: number;
  maxStopLossPct: number;
  useAtrStops: boolean;
  breakevenTimeStopDays: number;
  maxSingleWeight: number;
  breakevenRTrigger: number;
};

function exitStage(doc: PipelineDocument): Stage | undefined {
  return (doc.stages ?? []).find((s) => s.mode === "exit");
}

export function progressiveFromDoc(doc: PipelineDocument): ProgressiveKnobs {
  const exit = exitStage(doc);
  const gate = doc.regime_gate ?? doc.risk?.regime_gate;
  const uses = Array.isArray(gate?.uses) ? (gate.uses as string[]) : [];
  return {
    tranches:
      exit?.tranches && exit.tranches.length > 0
        ? exit.tranches
        : CHAMPION_EXIT_TRANCHES,
    trailingStopPct: exit?.trailing_stop_pct ?? 0.15,
    maxHoldDays: exit?.max_hold_days ?? 63,
    regimeOn: Boolean(gate),
    regimeUses: uses,
    atrStopMultiplier: exit?.atr_stop_multiplier ?? 2.0,
    maxStopLossPct: exit?.max_stop_loss_pct ?? 0.05,
    useAtrStops: exit?.use_atr_stops ?? true,
    breakevenTimeStopDays: exit?.breakeven_time_stop_days ?? 10,
    maxSingleWeight: exit?.max_single_weight ?? 0.2,
    breakevenRTrigger: exit?.breakeven_r_trigger ?? 1.5,
  };
}

export function patchProgressive(
  doc: PipelineDocument,
  patch: Partial<ProgressiveKnobs>,
): PipelineDocument {
  const cur = progressiveFromDoc(doc);
  const next = { ...cur, ...patch };
  const stages = [...(doc.stages ?? [])];
  const idx = stages.findIndex((s) => s.mode === "exit");
  const exit: Stage = {
    ...(idx >= 0 ? stages[idx]! : { name: "Sell Into Strength", mode: "exit" }),
    mode: "exit",
    name: idx >= 0 ? stages[idx]!.name : "Sell Into Strength",
    tranches: next.tranches,
    trailing_stop_pct: next.trailingStopPct,
    max_hold_days: next.maxHoldDays,
    atr_stop_multiplier: next.atrStopMultiplier,
    max_stop_loss_pct: next.maxStopLossPct,
    use_atr_stops: next.useAtrStops,
    breakeven_time_stop_days: next.breakevenTimeStopDays,
    max_single_weight: next.maxSingleWeight,
    breakeven_r_trigger: next.breakevenRTrigger,
  };
  if (idx >= 0) stages[idx] = exit;
  else stages.push(exit);

  const defaultUses = ["scale_exposure", "skip_pyramid_adds", "block_new_longs"];
  const prevGateRaw = doc.regime_gate ?? doc.risk?.regime_gate;
  const prevGate =
    typeof prevGateRaw === "object" && prevGateRaw !== null ? prevGateRaw : {};
  const regime_gate = next.regimeOn
    ? {
        source: "regime_signals_canonical",
        threshold: 0.5,
        ...prevGate,
        uses: next.regimeUses.length > 0 ? next.regimeUses : defaultUses,
      }
    : null;

  // Regime policy is cross-slot — lives at doc level, compiles to
  // DataSources.regime; uses[] routes effects to PCM (scale_exposure,
  // skip_pyramid_adds) and Alpha (block_new_longs). Clear any legacy
  // risk.regime_gate copy so reads can't disagree on which path is current.
  const risk = doc.risk ? { ...doc.risk } : undefined;
  if (risk && risk.regime_gate !== undefined) {
    delete risk.regime_gate;
  }
  return {
    ...doc,
    stages,
    risk,
    regime_gate,
    execution: withDailyMarket(doc),
  };
}

/** Ordered rule AST (C-FW-RULES Phase 1) lives on the exit stage → Risk slot. */
export function exitRulesFromDoc(doc: PipelineDocument): RuleSpec[] {
  // parseRules also canonicalizes `col __position.<f>` → `pos` nodes so the
  // editor renders bindings as pos pills and the next save migrates the AST.
  return parseRules(exitStage(doc)?.rules);
}

export function patchExitRules(
  doc: PipelineDocument,
  rules: RuleSpec[],
): PipelineDocument {
  const stages = [...(doc.stages ?? [])];
  const idx = stages.findIndex((s) => s.mode === "exit");
  if (idx >= 0) {
    stages[idx] = { ...stages[idx]!, rules };
  } else {
    stages.push({ name: "Sell Into Strength", mode: "exit", rules });
  }
  return { ...doc, stages };
}

/** Unified PCM rules pass (C-FW-RULES Phase 2) lives on `doc.sizing.rules`. */
export function pcmRulesFromDoc(doc: PipelineDocument): RuleSpec[] {
  return parseRules(doc.sizing?.rules);
}

export function patchPcmRules(
  doc: PipelineDocument,
  rules: RuleSpec[],
): PipelineDocument {
  return { ...doc, sizing: { ...(doc.sizing ?? {}), rules } };
}

/** Base sizing Operand AST on `doc.sizing.size_expr` (PCM slot). */
export function pcmSizeExprFromDoc(
  doc: PipelineDocument,
): Record<string, unknown> | null {
  const v = doc.sizing?.size_expr;
  if (!v || typeof v !== "object") return null;
  return normalizeOperandAst(v) as Record<string, unknown>;
}

export function patchPcmSizeExpr(
  doc: PipelineDocument,
  sizeExpr: Record<string, unknown> | null,
): PipelineDocument {
  return { ...doc, sizing: { ...(doc.sizing ?? {}), size_expr: sizeExpr } };
}

/** Book-level PCM ASTs (Phase 3) — `doc.sizing.{scale,slots,order}_expr`. */
export type PcmBookExprKey = "scale_expr" | "slots_expr" | "order_expr";

export function pcmBookExprFromDoc(
  doc: PipelineDocument,
  key: PcmBookExprKey,
): Record<string, unknown> | null {
  const v = doc.sizing?.[key];
  if (!v || typeof v !== "object") return null;
  return normalizeOperandAst(v) as Record<string, unknown>;
}

export function patchPcmBookExpr(
  doc: PipelineDocument,
  key: PcmBookExprKey,
  expr: Record<string, unknown> | null,
): PipelineDocument {
  return { ...doc, sizing: { ...(doc.sizing ?? {}), [key]: expr } };
}

/** Position-init stop Operand AST (C-VERA-EXPR-V2) on the exit stage → Risk slot. */
export function initStopFromDoc(
  doc: PipelineDocument,
): Record<string, unknown> | null {
  const v = exitStage(doc)?.init_stop;
  if (!v || typeof v !== "object") return null;
  // Legacy `col __position.<f>` spellings render as `pos` pills and re-save
  // in the canonical form — identical evaluation.
  return normalizeOperandAst(v) as Record<string, unknown>;
}

export function patchInitStop(
  doc: PipelineDocument,
  initStop: Record<string, unknown> | null,
): PipelineDocument {
  const stages = [...(doc.stages ?? [])];
  const idx = stages.findIndex((s) => s.mode === "exit");
  if (idx >= 0) {
    stages[idx] = { ...stages[idx]!, init_stop: initStop };
  } else {
    stages.push({
      name: "Sell Into Strength",
      mode: "exit",
      init_stop: initStop,
    });
  }
  return { ...doc, stages };
}

export function pinDailyMarketExecution(doc: PipelineDocument): PipelineDocument {
  return {
    ...doc,
    execution: withDailyMarket(doc),
  };
}

/** Stop-out cooldown (days) lives on the Alpha signal stage; edited from the Risk card. */
export function stopCooldownFromDoc(doc: PipelineDocument): number {
  const signal = (doc.stages ?? []).find((s) => s.mode === "signal");
  return signal?.stop_cooldown_days ?? 10;
}

export function patchStopCooldown(doc: PipelineDocument, days: number): PipelineDocument {
  const stages = [...(doc.stages ?? [])];
  const idx = stages.findIndex((s) => s.mode === "signal");
  if (idx < 0) return doc;
  stages[idx] = { ...stages[idx]!, stop_cooldown_days: days };
  return { ...doc, stages };
}

/** Champion Alpha ranks boolean screens by screens_hit. Union is not authored here. */
export function pinChampionGateRanking(doc: PipelineDocument): PipelineDocument {
  const floor = doc.min_screens != null && doc.min_screens >= 1 ? doc.min_screens : 1;
  return {
    ...doc,
    gate_combine: "count",
    min_screens: floor,
  };
}

export function pinChampionPipeline(doc: PipelineDocument): PipelineDocument {
  return pinChampionGateRanking({
    ...doc,
    execution: { ...(doc.execution ?? {}), ...DAILY_MARKET_EXECUTION, fill_session: "moo" },
  });
}
