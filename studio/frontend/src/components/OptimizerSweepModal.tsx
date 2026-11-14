import { useMemo, useState } from "react";
import type { BacktestSpecSummary, LaunchOptimizerRequest, OptimizerConstraint } from "../types";

const SWEEPABLE_PARAMETERS = [
  { id: "stop_loss_pct", label: "Stop Loss % (Alpha)", defaultMin: 0.04, defaultMax: 0.12, defaultStep: 0.02, defaultMinStep: 0.005 },
  { id: "target_atr_risk", label: "Target ATR Risk (PCM)", defaultMin: 0.002, defaultMax: 0.006, defaultStep: 0.001, defaultMinStep: 0.0005 },
  { id: "trailing_stop_pct", label: "Trailing Stop % (Risk)", defaultMin: 0.03, defaultMax: 0.09, defaultStep: 0.02, defaultMinStep: 0.005 },
  { id: "max_positions", label: "Max Positions (Capacity)", defaultMin: 5, defaultMax: 20, defaultStep: 5, defaultMinStep: 1 },
  { id: "max_sector_exposure", label: "Sector Cap % (Risk)", defaultMin: 0.15, defaultMax: 0.35, defaultStep: 0.05, defaultMinStep: 0.01 },
  { id: "period", label: "RSI Period (Alpha)", defaultMin: 8, defaultMax: 24, defaultStep: 4, defaultMinStep: 2 },
];

export function OptimizerSweepModal({
  specs,
  isOpen,
  onClose,
  onLaunch,
  isLaunching,
  initialIrId,
  initialTitle,
  initialStartDate,
  initialEndDate,
}: {
  specs: BacktestSpecSummary[];
  isOpen: boolean;
  onClose: () => void;
  onLaunch: (req: LaunchOptimizerRequest) => void;
  isLaunching: boolean;
  initialIrId?: string;
  initialTitle?: string;
  initialStartDate?: string;
  initialEndDate?: string;
}) {
  const [baseIrId, setBaseIrId] = useState(initialIrId || specs[0]?.ir_id || "");
  const [title, setTitle] = useState(initialTitle ? `${initialTitle} Sweep` : "");
  const [startDate, setStartDate] = useState(initialStartDate || "2025-01-01");
  const [endDate, setEndDate] = useState(initialEndDate || "2026-01-01");
  const [strategyType, setStrategyType] = useState<"euler" | "grid">("euler");

  useMemo(() => {
    if (isOpen && initialIrId) {
      setBaseIrId(initialIrId);
      if (initialTitle) setTitle(`${initialTitle} Sweep`);
      if (initialStartDate) setStartDate(initialStartDate);
      if (initialEndDate) setEndDate(initialEndDate);
    }
  }, [isOpen, initialIrId, initialTitle, initialStartDate, initialEndDate]);
  const [objective, setObjective] = useState("sharpe_ratio");
  const [maxConcurrent, setMaxConcurrent] = useState(4);

  // Param X
  const [paramXName, setParamXName] = useState("stop_loss_pct");
  const [paramXMin, setParamXMin] = useState(0.04);
  const [paramXMax, setParamXMax] = useState(0.12);
  const [paramXStep, setParamXStep] = useState(0.02);

  // Param Y
  const [useParamY, setUseParamY] = useState(true);
  const [paramYName, setParamYName] = useState("target_atr_risk");
  const [paramYMin, setParamYMin] = useState(0.002);
  const [paramYMax, setParamYMax] = useState(0.006);
  const [paramYStep, setParamYStep] = useState(0.001);

  // Constraints
  const [constraints] = useState<OptimizerConstraint[]>([
    { target: "Drawdown", operator: "lessOrEqual", target_value: 0.20 },
    { target: "Total Trades", operator: "greaterOrEqual", target_value: 15 },
  ]);

  const xValues = useMemo(() => {
    const vals: number[] = [];
    let cur = paramXMin;
    while (cur <= paramXMax + 1e-6 && vals.length < 25) {
      vals.push(Number(cur.toFixed(4)));
      cur += paramXStep;
    }
    return vals;
  }, [paramXMin, paramXMax, paramXStep]);

  const yValues = useMemo(() => {
    if (!useParamY) return [];
    const vals: number[] = [];
    let cur = paramYMin;
    while (cur <= paramYMax + 1e-6 && vals.length < 25) {
      vals.push(Number(cur.toFixed(4)));
      cur += paramYStep;
    }
    return vals;
  }, [useParamY, paramYMin, paramYMax, paramYStep]);

  const totalRunsEstimate = useParamY ? xValues.length * yValues.length : xValues.length;

  if (!isOpen) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!baseIrId) return;

    onLaunch({
      base_ir_id: baseIrId,
      start_date: startDate,
      end_date: endDate,
      param_x_name: paramXName,
      param_x_values: xValues,
      param_y_name: useParamY ? paramYName : undefined,
      param_y_values: useParamY ? yValues : undefined,
      title: title.trim() || undefined,
      objective,
      strategy_type: strategyType,
      constraints,
      max_concurrent: maxConcurrent,
      lean_project: "VeraTradingLab",
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-ink">Launch Parameter Sweep</span>
            <span className="rounded bg-accent/15 px-2 py-0.5 text-[10px] font-bold uppercase text-accent">
              LEAN Native
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-lg font-bold text-ink-muted hover:text-ink transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
          {/* Base Spec & Title */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold text-ink-muted">Base Strategy Spec</label>
              <select
                value={baseIrId}
                onChange={(e) => setBaseIrId(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-xs text-ink"
                required
              >
                {specs.map((s) => (
                  <option key={s.ir_id} value={s.ir_id}>
                    {s.title || s.ir_id}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-ink-muted">Study Title (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Minervini Risk & Exit Optimization"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-xs text-ink"
              />
            </div>
          </div>

          {/* Strategy & Objective */}
          <div className="grid grid-cols-3 gap-3 rounded-lg border border-line bg-surface-sunk p-3">
            <div>
              <label className="block text-[11px] font-bold text-ink-muted">Search Strategy</label>
              <select
                value={strategyType}
                onChange={(e) => setStrategyType(e.target.value as "euler" | "grid")}
                className="mt-1 w-full rounded border border-line bg-surface px-2 py-1 text-xs text-ink"
              >
                <option value="euler">EulerSearch (Adaptive Fractal) ⚡</option>
                <option value="grid">GridSearch (Exhaustive Sweep)</option>
              </select>
              <span className="mt-1 block text-[10px] text-ink-faint">
                {strategyType === "euler"
                  ? "Adaptive coarse sweep with automatic focal zoom."
                  : "Brute-force evaluation of all coordinate pairs."}
              </span>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-ink-muted">Target Objective</label>
              <select
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-surface px-2 py-1 text-xs text-ink"
              >
                <option value="sharpe_ratio">Sharpe Ratio (Max)</option>
                <option value="sortino_ratio">Sortino Ratio (Max)</option>
                <option value="total_return">Total Return (Max)</option>
                <option value="min_drawdown">Minimize Max Drawdown</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-ink-muted">Concurrency</label>
              <select
                value={maxConcurrent}
                onChange={(e) => setMaxConcurrent(Number(e.target.value))}
                className="mt-1 w-full rounded border border-line bg-surface px-2 py-1 text-xs text-ink"
              >
                <option value={2}>2 Parallel Workers</option>
                <option value={4}>4 Parallel Workers (Recommended)</option>
                <option value={8}>8 Parallel Workers (High Core)</option>
              </select>
            </div>
          </div>

          {/* Date Range */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold text-ink-muted">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-xs text-ink"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-ink-muted">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-xs text-ink"
              />
            </div>
          </div>

          {/* Parameter X Sweep */}
          <div className="rounded-lg border border-line bg-surface p-3 space-y-2">
            <span className="text-[11px] font-bold text-ink">Primary Parameter (X-Axis)</span>
            <div className="grid grid-cols-4 gap-2">
              <div>
                <label className="block text-[10px] text-ink-muted">Parameter</label>
                <select
                  value={paramXName}
                  onChange={(e) => setParamXName(e.target.value)}
                  className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                >
                  {SWEEPABLE_PARAMETERS.map((p) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-ink-muted">Min</label>
                <input
                  type="number"
                  step="any"
                  value={paramXMin}
                  onChange={(e) => setParamXMin(Number(e.target.value))}
                  className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                />
              </div>
              <div>
                <label className="block text-[10px] text-ink-muted">Max</label>
                <input
                  type="number"
                  step="any"
                  value={paramXMax}
                  onChange={(e) => setParamXMax(Number(e.target.value))}
                  className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                />
              </div>
              <div>
                <label className="block text-[10px] text-ink-muted">Step</label>
                <input
                  type="number"
                  step="any"
                  value={paramXStep}
                  onChange={(e) => setParamXStep(Number(e.target.value))}
                  className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                />
              </div>
            </div>
          </div>

          {/* Parameter Y Sweep */}
          <div className="rounded-lg border border-line bg-surface p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-ink">Secondary Parameter (Y-Axis)</span>
              <label className="flex cursor-pointer items-center gap-1 text-[10.5px] text-ink-muted">
                <input
                  type="checkbox"
                  checked={useParamY}
                  onChange={(e) => setUseParamY(e.target.checked)}
                  className="rounded border-line"
                />
                Enable 2D Sweep
              </label>
            </div>

            {useParamY && (
              <div className="grid grid-cols-4 gap-2">
                <div>
                  <label className="block text-[10px] text-ink-muted">Parameter</label>
                  <select
                    value={paramYName}
                    onChange={(e) => setParamYName(e.target.value)}
                    className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                  >
                    {SWEEPABLE_PARAMETERS.map((p) => (
                      <option key={p.id} value={p.id}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-ink-muted">Min</label>
                  <input
                    type="number"
                    step="any"
                    value={paramYMin}
                    onChange={(e) => setParamYMin(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-ink-muted">Max</label>
                  <input
                    type="number"
                    step="any"
                    value={paramYMax}
                    onChange={(e) => setParamYMax(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-ink-muted">Step</label>
                  <input
                    type="number"
                    step="any"
                    value={paramYStep}
                    onChange={(e) => setParamYStep(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-xs text-ink"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Quant Constraints */}
          <div className="rounded-lg border border-line bg-surface-sunk p-3 space-y-1.5">
            <span className="block text-[11px] font-bold text-ink-muted">
              Quant Pruning Constraints (Discard Overfit Anomalies)
            </span>
            <div className="flex flex-wrap gap-2 text-[10.5px]">
              {constraints.map((c, i) => (
                <span key={i} className="rounded bg-surface px-2 py-0.5 border border-line text-ink">
                  {c.target} {c.operator === "lessOrEqual" ? "≤" : "≥"} {c.target_value}
                </span>
              ))}
            </div>
          </div>

          {/* Modal Footer & Launch Trigger */}
          <div className="flex items-center justify-between border-t border-line pt-3">
            <span className="text-[11px] font-mono text-ink-muted">
              Estimated variants: <span className="font-bold text-ink">{totalRunsEstimate} runs</span>
            </span>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLaunching || !baseIrId}
                className="rounded bg-accent px-4 py-1.5 text-xs font-bold text-accent-ink hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {isLaunching ? "Launching Study…" : "🚀 Launch Optimization"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
