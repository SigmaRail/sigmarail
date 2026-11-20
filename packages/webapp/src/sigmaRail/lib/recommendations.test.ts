import { describe, it, expect } from "vitest";
import { buildBacktestRecommendations } from "./recommendations";
import type { BacktestReport } from "../types";

function report(metrics: BacktestReport["metrics"]): BacktestReport {
  return {
    run_id: "run-test",
    metrics,
    highlights: [],
    warnings: [],
  };
}

describe("buildBacktestRecommendations", () => {
  it("returns no recommendations when all metrics are absent", () => {
    expect(buildBacktestRecommendations(report({}))).toEqual([]);
    expect(
      buildBacktestRecommendations(
        report({ total_return: null, sharpe_ratio: null, max_drawdown: null }),
      ),
    ).toEqual([]);
  });

  it("flags insufficient sample size and negative return", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: -0.05, total_orders: 3, sharpe_ratio: 0.2 }),
    );
    const ids = recs.map((r) => r.id);
    expect(ids).toContain("insufficient-sample");
    expect(ids).toContain("negative-return");
    expect(ids).toContain("low-sharpe");
  });

  it("routes deep drawdown and weak sharpe to RiskManagement", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 0.6, sharpe_ratio: 0.8, max_drawdown: 0.32, total_orders: 40 }),
    );
    const risk = recs.filter((r) => r.slot === "RiskManagement");
    expect(risk.map((r) => r.id)).toEqual(
      expect.arrayContaining(["low-sharpe", "deep-drawdown"]),
    );
  });

  it("flags high-turnover deep drawdown as falling-knife rotation", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 0.6, sharpe_ratio: 1.1, max_drawdown: 0.39, total_orders: 968 }),
    );
    const rotation = recs.find((r) => r.id === "high-turnover-deep-drawdown");
    expect(rotation).toBeDefined();
    expect(rotation?.slot).toBe("Alpha");
    expect(rotation?.action).toContain("confirmation");
    expect(rotation?.action).not.toContain("regime-source = market_regime_signals_daily");
  });

  it("does not flag high turnover when drawdown is shallow", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 0.6, max_drawdown: 0.12, total_orders: 968 }),
    );
    expect(recs.map((r) => r.id)).not.toContain("high-turnover-deep-drawdown");
  });

  it("flags profit_factor below 1 with strongly positive return as a data artifact, not poor profit factor", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 0.635, profit_factor: 0.5, total_orders: 968 }),
    );
    const ids = recs.map((r) => r.id);
    expect(ids).toContain("profit-factor-data-inconsistency");
    expect(ids).not.toContain("poor-profit-factor");
  });

  it("still flags poor profit factor when the value is consistent with a modest return", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 0.03, profit_factor: 1.1, total_orders: 30 }),
    );
    expect(recs.map((r) => r.id)).toContain("poor-profit-factor");
    expect(recs.map((r) => r.id)).not.toContain("profit-factor-data-inconsistency");
  });

  it("emits a promotion-candidate info for robust metrics", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 1.2, sharpe_ratio: 1.8, max_drawdown: 0.12, total_orders: 80 }),
    );
    expect(recs.map((r) => r.id)).toContain("promotion-candidate");
  });

  it("falls back to a single within-thresholds info when nothing crosses a rule", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: 0.3, sharpe_ratio: 1.1, max_drawdown: 0.15, win_rate: 0.55, profit_factor: 1.5, total_orders: 30 }),
    );
    expect(recs).toHaveLength(1);
    expect(recs[0].id).toBe("within-thresholds");
  });

  it("orders action before watch before info", () => {
    const recs = buildBacktestRecommendations(
      report({ total_return: -0.1, sharpe_ratio: 0.4, max_drawdown: 0.4, total_orders: 4, win_rate: 0.2 }),
    );
    const severities = recs.map((r) => r.severity);
    expect(severities).toEqual([...severities].sort((a, b) => {
      const order = { action: 0, watch: 1, info: 2 };
      return order[a] - order[b];
    }));
  });
});