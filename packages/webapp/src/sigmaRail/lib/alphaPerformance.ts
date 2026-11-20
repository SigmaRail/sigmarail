import type { ScreenField } from "../types";
import type { Stage } from "../components/strategy/StrategyDocument";

/** A score-stage measure and whether it maps to a physical factor column. */
export type MeasureFactor = {
  /** Stage id shown in the picker. */
  alias: string;
  /** Stage display name. */
  label: string;
  /** Bare ClickHouse column when evaluable; null when unsupported. */
  column: string | null;
  /** Human-readable reason the measure cannot be evaluated. */
  reason?: string;
};

const DEFAULT_FACTOR_TABLE = "screener_price_tech_daily";

/**
 * Score stages that participate as measures (as_gate or computed_expr).
 * Only `computed_expr {type:"col"}` resolves to a physical column today —
 * expression and filter measures need a materialization path first.
 */
export function measureFactors(stages: Stage[]): MeasureFactor[] {
  const out: MeasureFactor[] = [];
  for (const s of stages ?? []) {
    if (s.mode !== "score") continue;
    const isMeasure = Boolean(s.as_gate) || Boolean(s.computed_expr);
    if (!isMeasure) continue;
    const alias = (s.id || "").trim();
    if (!alias) continue;
    const label = (s.name || alias).trim();
    const expr = s.computed_expr as { type?: string; name?: string } | null | undefined;
    if (expr) {
      const col = expr.type === "col" ? (expr.name || "").trim() : "";
      if (col) {
        out.push({ alias, label, column: col });
      } else {
        out.push({
          alias,
          label,
          column: null,
          reason: "expression measures must be materialized as a factor column",
        });
      }
    } else {
      out.push({
        alias,
        label,
        column: null,
        reason: "filter/boolean measures are not numeric factors",
      });
    }
  }
  return out;
}

/** Field-catalog lookup for the ClickHouse table holding `column`. */
export function resolveFactorTable(
  column: string,
  fields: ScreenField[],
): string {
  const f = fields.find((f) => f.name === column && f.table);
  return f?.table || DEFAULT_FACTOR_TABLE;
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const pct = v * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

/** End − N years, ISO date (UTC-safe). Empty input → empty output. */
export function yearsBack(endDate: string, years = 1): string {
  if (!endDate) return "";
  const d = new Date(`${endDate}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - years);
  return d.toISOString().slice(0, 10);
}
