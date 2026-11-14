/** Stamp dates / cash / benchmark onto a compiled VeraLab spec. */

export type EvaluationStamp = {
  start_date: string;
  end_date: string;
  initial_cash: number;
  benchmark: string;
};

export function stampEvaluation(
  spec: Record<string, unknown>,
  evalCfg: EvaluationStamp,
): Record<string, unknown> {
  const cash = Math.round(Number(evalCfg.initial_cash) || 100000);
  const bench = String(evalCfg.benchmark || "SPY").trim().toUpperCase() || "SPY";
  const start = String(evalCfg.start_date || "").trim();
  const end = String(evalCfg.end_date || "").trim();
  const veraBase =
    spec.VeraBase && typeof spec.VeraBase === "object"
      ? { ...(spec.VeraBase as Record<string, unknown>) }
      : {};
  const algo =
    spec.AlgorithmParameters && typeof spec.AlgorithmParameters === "object"
      ? { ...(spec.AlgorithmParameters as Record<string, unknown>) }
      : {};
  return {
    ...spec,
    AlgorithmParameters: {
      ...algo,
      "initial-cash": String(cash),
      benchmark: bench,
      ...(start ? { "start-date": start } : {}),
      ...(end ? { "end-date": end } : {}),
    },
    VeraBase: {
      ...veraBase,
      Evaluation: {
        start_date: start,
        end_date: end,
        initial_cash: cash,
        benchmark: bench,
      },
    },
  };
}

export function readEvaluation(spec: Record<string, unknown> | null | undefined): Partial<EvaluationStamp> {
  if (!spec) return {};
  const vb =
    spec.VeraBase && typeof spec.VeraBase === "object"
      ? (spec.VeraBase as Record<string, unknown>)
      : {};
  const ev =
    vb.Evaluation && typeof vb.Evaluation === "object"
      ? (vb.Evaluation as Record<string, unknown>)
      : {};
  const algo =
    spec.AlgorithmParameters && typeof spec.AlgorithmParameters === "object"
      ? (spec.AlgorithmParameters as Record<string, unknown>)
      : {};
  const start = String(ev.start_date || algo["start-date"] || "").trim();
  const end = String(ev.end_date || algo["end-date"] || "").trim();
  const cashRaw = ev.initial_cash ?? algo["initial-cash"];
  const cash = cashRaw != null && String(cashRaw).trim() ? Number(cashRaw) : undefined;
  const bench = String(ev.benchmark || algo.benchmark || "").trim().toUpperCase();
  return {
    ...(start ? { start_date: start } : {}),
    ...(end ? { end_date: end } : {}),
    ...(cash != null && Number.isFinite(cash) ? { initial_cash: cash } : {}),
    ...(bench ? { benchmark: bench } : {}),
  };
}

export function evaluationExtraEnv(spec: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!spec || typeof spec.AlgorithmParameters !== "object" || spec.AlgorithmParameters == null) {
    return {};
  }
  const algo = spec.AlgorithmParameters as Record<string, unknown>;
  const out: Record<string, string> = {};
  for (const key of ["initial-cash", "benchmark"] as const) {
    const raw = algo[key];
    if (raw != null && String(raw).trim()) out[key] = String(raw).trim();
  }
  return out;
}
