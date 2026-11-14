import type { BacktestReport, BacktestReportMetrics } from "../types";

export type RecommendationSeverity = "action" | "watch" | "info";

export type FrameworkSlot =
  | "Alpha"
  | "PortfolioConstruction"
  | "RiskManagement"
  | "Execution"
  | "General";

export interface StrategyRecommendation {
  id: string;
  severity: RecommendationSeverity;
  slot: FrameworkSlot;
  title: string;
  body: string;
  action: string;
}

export type RecommendationSource = Pick<
  BacktestReport,
  "metrics" | "warnings" | "highlights"
>;

/**
 * Deterministic, metric-driven recommendation engine for a completed backtest
 * run. Produces explicit, slot-scoped adjustments to guide the composer loop
 * (backtest → analyze → recommend → adjust → rerun). Thresholds are deliberately
 * simple and documented inline so they are auditable rather than black-box.
 */
export function buildBacktestRecommendations(
  source: RecommendationSource,
): StrategyRecommendation[] {
  const m: BacktestReportMetrics = source.metrics ?? {};
  const recommendations: StrategyRecommendation[] = [];

  const sharpe = m.sharpe_ratio ?? null;
  const maxDrawdown = m.max_drawdown ?? null;
  const winRate = m.win_rate ?? null;
  const profitFactor = m.profit_factor ?? null;
  const totalOrders = m.total_orders ?? null;
  const totalReturn = m.total_return ?? null;

  const hasAnyMetric = [sharpe, maxDrawdown, winRate, profitFactor, totalOrders, totalReturn].some(
    (v) => v != null,
  );
  if (!hasAnyMetric) return [];

  // Sample-size gate first: every tuning decision downstream is unreliable
  // without a minimum number of round-trip trades.
  if (totalOrders != null && totalOrders < 10) {
    recommendations.push({
      id: "insufficient-sample",
      severity: "watch",
      slot: "General",
      title: "Insufficient sample size",
      body: "Fewer than 10 orders were recorded, so most performance statistics are statistically fragile. Prefer widening the window or relaxing entry triggers before tuning downstream parameters.",
      action: "Extend the backtest start/end window or relax the Universe/Alpha filters to generate more round-trip trades.",
    });
  }

  if (totalReturn != null && totalReturn < 0) {
    recommendations.push({
      id: "negative-return",
      severity: "action",
      slot: "Alpha",
      title: "Negative total return",
      body: "The strategy lost money over the evaluation window. Confirm the universe is producing candidates and that entry triggers are not systematically late.",
      action: "Switch the Alpha model type or tighten entry triggers before adjusting sizing and stops.",
    });
  }

  if (sharpe != null && sharpe < 1.0) {
    recommendations.push({
      id: "low-sharpe",
      severity: "action",
      slot: "RiskManagement",
      title: "Weak risk-adjusted return",
      body: "Sharpe is below 1.0, indicating returns are not compensating for the volatility taken.",
      action: "Tighten stops (reduce trailing-stop / hard-stop distance) or reduce per-trade risk to damp volatility relative to return.",
    });
  }

  if (maxDrawdown != null && maxDrawdown > 0.25) {
    recommendations.push({
      id: "deep-drawdown",
      severity: "action",
      slot: "RiskManagement",
      title: "Deep maximum drawdown",
      body: "Drawdown exceeds 25%, a structural capital-preservation breach under the SEPA/VCP framework. Per-position stops cannot cap portfolio drawdown when correlated momentum names fall together.",
      action: "Gate new entries on a confirmed market-condition filter (SPY above a rising 200d plus breadth allocation_tier ≥ 67 held over a multi-day window), lower min_regime_fraction toward 0 for weak-breadth periods, and de-risk on the fast daily regime flag only with multi-day confirmation to avoid single-day whipsaw.",
    });
  }

  // High turnover + deep drawdown is the signature of "catching falling knives":
  // the screener keeps re-entering fresh breakouts while breadth deteriorates.
  if (totalOrders != null && totalOrders > 200 && maxDrawdown != null && maxDrawdown > 0.2) {
    recommendations.push({
      id: "high-turnover-deep-drawdown",
      severity: "action",
      slot: "Alpha",
      title: "Rotation is catching falling knives",
      body: "Hundreds of orders with a deep drawdown means the model keeps re-entering new breakouts through a weak market. The screener is a candidate generator, not a market-condition filter — entries must be suppressed when breadth deteriorates. Do not gate on the fast daily regime flag alone: a single-day flip flattens winners and re-buys the first bounce.",
      action: "Block new longs on a slow, confirmation-gated market filter (SPY above a rising 200d and allocation_tier ≥ 67 confirmed over a multi-day window); use the fast clamp_risk_off flag only as a 2-day-confirmed circuit breaker for de-risking, never a single-day all-clear.",
    });
  }

  if (winRate != null && winRate < 0.4) {
    recommendations.push({
      id: "low-win-rate",
      severity: "watch",
      slot: "Alpha",
      title: "Low win rate",
      body: "Fewer than 40% of trades are profitable. High-frequency loss-taking often points to late entries or a too-wide stop before breakeven.",
      action: "Tighten entry triggers or move the breakeven ratchet closer to entry so losing trades are smaller.",
    });
  }

  // The stored `profit_factor` field is populated from LEAN's "Profit-Loss Ratio"
  // (avg win / avg loss), not gross profit / gross loss (see VeraTradingLab
  // strategy_runs model). A value below 1.0 alongside a strongly positive return
  // is arithmetically impossible for a true profit factor, so treat it as a data
  // artifact and say so instead of emitting a false "poor profit factor" warning.
  const profitFactorInconsistent =
    profitFactor != null &&
    profitFactor < 1 &&
    totalReturn != null &&
    totalReturn >= 0.1;
  if (profitFactorInconsistent) {
    recommendations.push({
      id: "profit-factor-data-inconsistency",
      severity: "info",
      slot: "General",
      title: "Profit factor field is unreliable for this run",
      body: "A profit factor below 1.0 cannot coexist with a strongly positive return. The stored profit_factor is LEAN's Profit-Loss Ratio (avg win / avg loss), not gross profit / gross loss — skip this metric when tuning until the source is corrected.",
      action: "Ignore the profit-factor rule for this run; treat Profit-Loss Ratio separately from Profit Factor.",
    });
  } else if (profitFactor != null && profitFactor < 1.2) {
    recommendations.push({
      id: "poor-profit-factor",
      severity: "watch",
      slot: "RiskManagement",
      title: "Poor profit factor",
      body: "Gross profits are not materially exceeding gross losses, leaving little buffer for slippage and fees.",
      action: "Raise the tranche profit target or use a trailing runner to let winners run farther than losers.",
    });
  }

  if (totalOrders != null && totalOrders > 8 && sharpe != null && sharpe >= 1.5 && maxDrawdown != null && maxDrawdown <= 0.2) {
    recommendations.push({
      id: "promotion-candidate",
      severity: "info",
      slot: "Execution",
      title: "Promotion candidate",
      body: "Sharpe, drawdown, and sample size are within paper-deployment bounds. Confirm out-of-sample stability before promoting.",
      action: "Run an OOS forward test, then promote to paper via the Deploy phase.",
    });
  }

  if (recommendations.length === 0) {
    recommendations.push({
      id: "within-thresholds",
      severity: "info",
      slot: "General",
      title: "Within thresholds",
      body: "No metric crossed an action threshold. Review monthly returns and attribution for edge, then consider a broad optimization sweep.",
      action: "Launch an optimization or walk-forward sweep to search nearby parameter space.",
    });
  }

  const order: Record<RecommendationSeverity, number> = { action: 0, watch: 1, info: 2 };
  return recommendations.sort((a, b) => order[a.severity] - order[b.severity]);
}