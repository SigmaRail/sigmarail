import { describe, expect, it } from "vitest";
import {
  fmtNum,
  fmtPct,
  measureFactors,
  resolveFactorTable,
  yearsBack,
} from "./alphaPerformance";
import type { Stage } from "../components/strategy/StrategyDocument";
import type { ScreenField } from "../types";

function stage(partial: Partial<Stage>): Stage {
  return { name: "m", mode: "score", ...partial };
}

describe("measureFactors", () => {
  it("marks computed_expr col measures as evaluable", () => {
    const out = measureFactors([
      stage({ id: "rs", as_gate: true, computed_expr: { type: "col", name: "rs_rating" } }),
    ]);
    expect(out).toEqual([
      { alias: "rs", label: "m", column: "rs_rating" },
    ]);
  });

  it("marks non-col expression measures unsupported", () => {
    const out = measureFactors([
      stage({
        id: "sum",
        as_gate: true,
        computed_expr: { type: "add", left: { type: "col", name: "a" } },
      }),
    ]);
    expect(out[0]?.column).toBeNull();
    expect(out[0]?.reason).toMatch(/materialized/);
  });

  it("marks filter measures unsupported", () => {
    const out = measureFactors([
      stage({ id: "gate", as_gate: true, filters: [] }),
    ]);
    expect(out[0]?.column).toBeNull();
    expect(out[0]?.reason).toMatch(/filter/);
  });

  it("skips non-measure score stages and missing aliases", () => {
    const out = measureFactors([
      stage({ id: "rank", name: "Rank" }), // plain rank stage, not a measure
      stage({ as_gate: true, computed_expr: { type: "col", name: "x" } }), // no id
      { name: "Filter", mode: "filter", filters: [] },
    ]);
    expect(out).toHaveLength(0);
  });

  it("preserves stage order and label fallback to alias", () => {
    const out = measureFactors([
      stage({
        id: "a",
        name: "ATR pct",
        as_gate: true,
        computed_expr: { type: "col", name: "atr_14_pct" },
      }),
      stage({
        id: "b",
        name: "",
        as_gate: true,
        computed_expr: { type: "col", name: "perf_3m" },
      }),
    ]);
    expect(out.map((m) => m.alias)).toEqual(["a", "b"]);
    expect(out[0]?.label).toBe("ATR pct");
    expect(out[1]?.label).toBe("b");
  });
});

describe("resolveFactorTable", () => {
  const fields: ScreenField[] = [
    { name: "atr_14_pct", label: "ATR", category: "technicals", table: "screener_price_tech_daily" },
    { name: "factor_rolling_alpha_252d", label: "Alpha", category: "factors", table: "screener_factor_daily" },
  ];

  it("resolves the catalog table", () => {
    expect(resolveFactorTable("factor_rolling_alpha_252d", fields)).toBe("screener_factor_daily");
    expect(resolveFactorTable("atr_14_pct", fields)).toBe("screener_price_tech_daily");
  });

  it("falls back to screener_price_tech_daily when unknown", () => {
    expect(resolveFactorTable("does_not_exist", fields)).toBe("screener_price_tech_daily");
    expect(resolveFactorTable("atr_14_pct", [])).toBe("screener_price_tech_daily");
  });
});

describe("formatting", () => {
  it("fmtPct signs and scales", () => {
    expect(fmtPct(0.0050158)).toBe("+0.50%");
    expect(fmtPct(-0.0123)).toBe("-1.23%");
    expect(fmtPct(null)).toBe("—");
    expect(fmtPct(Number.NaN)).toBe("—");
  });

  it("fmtNum handles nulls", () => {
    expect(fmtNum(-0.003566, 3)).toBe("-0.004");
    expect(fmtNum(null)).toBe("—");
  });

  it("yearsBack subtracts whole years (UTC)", () => {
    expect(yearsBack("2025-06-30")).toBe("2024-06-30");
    // Feb 29 rolls to Mar 1 (matches AlphaMembershipProbe yearBackStart).
    expect(yearsBack("2024-02-29")).toBe("2023-03-01");
    expect(yearsBack("")).toBe("");
  });
});
