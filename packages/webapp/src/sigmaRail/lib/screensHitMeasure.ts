import type { PipelineDocument, Stage } from "../components/strategy/StrategyDocument";

/** Left-fold Σ col aliases as a formula Operand dict (SQL-ready). */
export function sumColsExpr(aliases: string[]): Record<string, unknown> {
  if (aliases.length === 0) return { type: "lit", value: 0 };
  let expr: Record<string, unknown> = { type: "col", name: aliases[0]! };
  for (let i = 1; i < aliases.length; i++) {
    expr = {
      type: "formula",
      op: "+",
      args: [expr, { type: "col", name: aliases[i]! }],
    };
  }
  return expr;
}

/** Weighted Σ w·alias as formula Operand (matches compiler _weighted_hit_expr). */
export function weightedSumColsExpr(
  terms: { alias: string; weight: number }[],
): Record<string, unknown> {
  if (terms.length === 0) return { type: "lit", value: 0 };
  const term = (alias: string, weight: number): Record<string, unknown> => {
    const col = { type: "col", name: alias };
    if (Math.abs(weight - 1) < 1e-12) return col;
    return {
      type: "formula",
      op: "*",
      args: [{ type: "lit", value: weight }, col],
    };
  };
  let expr = term(terms[0]!.alias, terms[0]!.weight);
  for (let i = 1; i < terms.length; i++) {
    expr = {
      type: "formula",
      op: "+",
      args: [expr, term(terms[i]!.alias, terms[i]!.weight)],
    };
  }
  return expr;
}

export function countAsSignalTerms(
  stages: Stage[],
): { alias: string; weight: number }[] {
  const out: { alias: string; weight: number }[] = [];
  let i = 0;
  for (const s of stages) {
    if (s.mode !== "score" || !s.as_gate || s.computed_expr) {
      continue;
    }
    if (s.count_as_signal === false) {
      i += 1;
      continue;
    }
    // Match compiler: gates with no filters are not emitted as computed bools.
    if (!s.filters || s.filters.length === 0) {
      i += 1;
      continue;
    }
    const id = (s.id || "").trim() || `gate_${i}`;
    out.push({ alias: id, weight: s.signal_weight ?? 1 });
    i += 1;
  }
  return out;
}

export function countAsSignalAliases(stages: Stage[]): string[] {
  return countAsSignalTerms(stages).map((t) => t.alias);
}

function lastGateIndex(stages: Stage[]): number {
  let last = -1;
  for (let i = 0; i < stages.length; i++) {
    const s = stages[i]!;
    if (s.mode === "score" && Boolean(s.as_gate) && !s.computed_expr) {
      last = i;
    }
  }
  return last;
}

export type EnsureScreensHitOptions = {
  /** When true, overwrite screens_hit / screens_hit_w expr from current gates. */
  syncExpr?: boolean;
};

/**
 * Ensure a real ``screens_hit`` Stage.computed_expr exists (SQL expr).
 * Seeds from count_as_signal gates. With syncExpr, refreshes the formula.
 */
export function ensureScreensHitMeasures(
  doc: PipelineDocument,
  opts: EnsureScreensHitOptions = {},
): PipelineDocument {
  const syncExpr = Boolean(opts.syncExpr);
  const stages = [...(doc.stages ?? [])];
  const terms = countAsSignalTerms(stages);
  if (terms.length === 0) {
    return {
      ...doc,
      stages: stages.filter(
        (s) =>
          !s.computed_expr ||
          !["screens_hit", "screens_hit_w"].includes((s.id || "").trim()),
      ),
      gate_combine: doc.gate_combine ?? "count",
    };
  }

  const hitAliases = terms.map((t) => t.alias);
  const hitExpr = sumColsExpr(hitAliases);
  const anyWeighted = terms.some((t) => Math.abs(t.weight - 1) > 1e-12);
  const hitWExpr = anyWeighted ? weightedSumColsExpr(terms) : null;

  const upsert = (id: string, name: string, expr: Record<string, unknown>) => {
    const idx = stages.findIndex(
      (s) => Boolean(s.computed_expr) && (s.id || "").trim() === id,
    );
    if (idx >= 0) {
      if (syncExpr || !stages[idx]!.computed_expr) {
        stages[idx] = { ...stages[idx]!, computed_expr: expr, name, id };
      }
      return;
    }
    const stage: Stage = {
      mode: "score",
      name,
      id,
      as_gate: true,
      count_as_signal: false,
      computed_expr: expr,
      filters: [],
      factors: [],
    };
    const insertAt = lastGateIndex(stages) + 1;
    if (insertAt <= 0 || insertAt >= stages.length) {
      stages.push(stage);
    } else {
      stages.splice(insertAt, 0, stage);
    }
  };

  upsert("screens_hit", "Screens hit", hitExpr);
  if (hitWExpr) {
    upsert("screens_hit_w", "Screens hit (weighted)", hitWExpr);
  } else {
    const wIdx = stages.findIndex(
      (s) => Boolean(s.computed_expr) && (s.id || "").trim() === "screens_hit_w",
    );
    if (wIdx >= 0) stages.splice(wIdx, 1);
  }

  return {
    ...doc,
    gate_combine: "count",
    stages,
  };
}
