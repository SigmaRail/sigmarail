import { useMemo } from "react";
import {
  normalizeSearchStrategy,
  type EvaluationConfig,
  type EvaluationStrategyType,
  type OptimizationSweepConfig,
  type SweepParamRange,
} from "../../types";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

export const DEFAULT_SWEEPABLE_PARAMS: SweepParamRange[] = [
  { name: "risk_per_trade_pct", label: "Risk Budget % (1R)", target_slot: "Portfolio", min: 0.005, max: 0.02, step: 0.0025 },
  { name: "take_profit_r", label: "Tranche 1 Profit (R)", target_slot: "Risk", min: 1.5, max: 3.5, step: 0.5 },
  { name: "max_positions", label: "Max Positions (Capacity)", target_slot: "Portfolio", min: 5, max: 20, step: 5 },
];

export const INITIAL_EVALUATION_CONFIG: EvaluationConfig = {
  strategy: "baseline",
  start_date: "2025-01-01",
  end_date: "2026-01-01",
  initial_cash: 100000,
  benchmark: "SPY",
  sweep: {
    strategy_type: "euler",
    objective: "sharpe_ratio",
    param_x: DEFAULT_SWEEPABLE_PARAMS[0]!,
    param_y: DEFAULT_SWEEPABLE_PARAMS[1]!,
    use_param_y: true,
    constraints: [
      { target: "Drawdown", operator: "lessOrEqual", target_value: 0.20 },
      { target: "Total Trades", operator: "greaterOrEqual", target_value: 15 },
    ],
    max_concurrent: 4,
  },
};

interface EvaluationSettingsPanelProps {
  config: EvaluationConfig;
  onChangeConfig: (updated: EvaluationConfig) => void;
  availableParams?: SweepParamRange[];
  compact?: boolean;
  baselineOnly?: boolean;
}

export function EvaluationSettingsPanel({
  config,
  onChangeConfig,
  availableParams = DEFAULT_SWEEPABLE_PARAMS,
  compact = false,
  baselineOnly = false,
}: EvaluationSettingsPanelProps) {
  const sweep = config.sweep ?? INITIAL_EVALUATION_CONFIG.sweep!;
  const isSweep = config.strategy === "optimization_sweep";

  const paramOptions = useMemo(() => {
    return availableParams.length > 0 ? availableParams : DEFAULT_SWEEPABLE_PARAMS;
  }, [availableParams]);

  // Calculate estimated variant count for sweep
  const { xCount, yCount, totalSweepRuns } = useMemo(() => {
    const xVals: number[] = [];
    let curX = sweep.param_x.min;
    while (curX <= sweep.param_x.max + 1e-6 && xVals.length < 30) {
      xVals.push(curX);
      curX += sweep.param_x.step;
    }
    const xC = Math.max(1, xVals.length);

    let yC = 1;
    if (sweep.use_param_y && sweep.param_y) {
      const yVals: number[] = [];
      let curY = sweep.param_y.min;
      while (curY <= sweep.param_y.max + 1e-6 && yVals.length < 30) {
        yVals.push(curY);
        curY += sweep.param_y.step;
      }
      yC = Math.max(1, yVals.length);
    }
    return {
      xCount: xC,
      yCount: yC,
      totalSweepRuns: sweep.use_param_y ? xC * yC : xC,
    };
  }, [sweep.param_x, sweep.param_y, sweep.use_param_y]);

  function setStrategy(strategy: EvaluationStrategyType) {
    onChangeConfig({
      ...config,
      strategy,
    });
  }

  function updateSweep(partial: Partial<OptimizationSweepConfig>) {
    onChangeConfig({
      ...config,
      sweep: {
        ...sweep,
        ...partial,
      },
    });
  }

  return (
    <Card className={compact ? "space-y-4 border-0 p-0 shadow-none" : "space-y-4 p-4 shadow-none"}>
      {/* Header & Protocol Segmented Control */}
      {!baselineOnly ? <div className={`flex flex-col justify-between gap-3 sm:flex-row sm:items-center ${compact ? "" : "border-b border-line pb-3"}`}>
        {!compact ? <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-ink flex items-center gap-1.5">
            <span>🔬</span>
            <span>Evaluation & Simulation Protocol</span>
          </h3>
          <p className="mt-0.5 text-[11px] text-ink-muted">Used only for backtests.</p>
        </div> : <span className="text-xs font-semibold text-ink">Run type</span>}

        {/* Segmented Buttons */}
        <div className="inline-flex rounded-lg border border-line bg-surface-sunk p-1">
          <Button
            type="button"
            onClick={() => setStrategy("baseline")}
            size="sm"
            variant={!isSweep ? "secondary" : "ghost"}
            aria-pressed={!isSweep}
          >
            <span>🎯</span>
            <span>Baseline</span>
          </Button>
          <Button
            type="button"
            onClick={() => setStrategy("optimization_sweep")}
            size="sm"
            variant={isSweep ? "secondary" : "ghost"}
            aria-pressed={isSweep}
          >
            <span>⚡</span>
            <span>Parameter Sweep</span>
          </Button>
        </div>
      </div> : null}

      {/* Date Range & Common Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
            Start Date
          </label>
          <Input
            type="date"
            className="h-9 px-2.5 py-1.5 text-xs font-mono"
            value={config.start_date}
            onChange={(e) => onChangeConfig({ ...config, start_date: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
            End Date
          </label>
          <Input
            type="date"
            className="h-9 px-2.5 py-1.5 text-xs font-mono"
            value={config.end_date}
            onChange={(e) => onChangeConfig({ ...config, end_date: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
            Initial Capital
          </label>
          <Select value={String(config.initial_cash)} onValueChange={(value) => onChangeConfig({ ...config, initial_cash: Number(value) })}>
            <SelectTrigger className="h-9 px-2.5 py-1.5 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="25000">$25,000 USD (PDT Cash)</SelectItem>
              <SelectItem value="50000">$50,000 USD (Standard Margin)</SelectItem>
              <SelectItem value="100000">$100,000 USD (Institutional Base)</SelectItem>
              <SelectItem value="500000">$500,000 USD (High Capacity)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
            Benchmark
          </label>
          <Select value={config.benchmark} onValueChange={(benchmark) => onChangeConfig({ ...config, benchmark })}>
            <SelectTrigger className="h-9 px-2.5 py-1.5 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="SPY">SPY (S&amp;P 500 ETF)</SelectItem>
              <SelectItem value="QQQ">QQQ (Nasdaq 100 ETF)</SelectItem>
              <SelectItem value="IWM">IWM (Russell 2000 ETF)</SelectItem>
              <SelectItem value="BIL">BIL (1-3M T-Bills Risk-Free)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Mode Specific Section: Parameter Sweep Matrix */}
      {config.strategy === "optimization_sweep" && (
        <div className="rounded-lg border border-line bg-surface-raised p-3.5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                <span>⚡</span>
                <span>Hyperparameter Search Space</span>
              </span>
              <p className="text-[10.5px] text-ink-muted">
                Define the parameter grid ranges to sweep across the 5-slot architecture.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-accent/15 px-3 py-1 text-xs font-bold text-accent border border-accent/30">
                {totalSweepRuns} Total Variants ({xCount} × {yCount})
              </span>
            </div>
          </div>

          {/* 2D Matrix Controls */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Param X */}
            <div className="rounded-lg border border-line bg-surface p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-ink">Primary Parameter (Axis X)</span>
                <span className="text-[10px] font-semibold text-accent uppercase">
                  {sweep.param_x.target_slot ?? "Model"}
                </span>
              </div>
              <Select value={sweep.param_x.name} onValueChange={(name) => {
                  const selected = paramOptions.find((p) => p.name === name);
                  if (selected) {
                    updateSweep({
                      param_x: { ...selected },
                    });
                  }
                }}>
                <SelectTrigger className="h-9 w-full text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>{paramOptions.map((p) => <SelectItem key={p.name} value={p.name}>{p.label ?? p.name}</SelectItem>)}</SelectContent>
              </Select>

              <div className="grid grid-cols-3 gap-2 pt-1">
                <div>
                  <label className="block text-[10px] uppercase font-bold text-ink-faint">Min</label>
                  <Input
                    type="number"
                    step="any"
                    className="h-8 px-2 py-1 text-xs font-mono"
                    value={sweep.param_x.min}
                    onChange={(e) =>
                      updateSweep({
                        param_x: { ...sweep.param_x, min: Number(e.target.value) },
                      })
                    }
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-ink-faint">Max</label>
                  <Input
                    type="number"
                    step="any"
                    className="h-8 px-2 py-1 text-xs font-mono"
                    value={sweep.param_x.max}
                    onChange={(e) =>
                      updateSweep({
                        param_x: { ...sweep.param_x, max: Number(e.target.value) },
                      })
                    }
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-ink-faint">Step</label>
                  <Input
                    type="number"
                    step="any"
                    className="h-8 px-2 py-1 text-xs font-mono"
                    value={sweep.param_x.step}
                    onChange={(e) =>
                      updateSweep({
                        param_x: { ...sweep.param_x, step: Number(e.target.value) },
                      })
                    }
                  />
                </div>
              </div>
            </div>

            {/* Param Y */}
            <div className="rounded-lg border border-line bg-surface p-3 space-y-2">
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-1.5 cursor-pointer text-xs font-bold text-ink">
                  <Checkbox
                    checked={sweep.use_param_y}
                    onCheckedChange={(checked) => updateSweep({ use_param_y: checked === true })}
                    aria-label="Enable secondary sweep parameter"
                  />
                  <span>Secondary Parameter (Axis Y)</span>
                </label>
                {sweep.use_param_y && sweep.param_y && (
                  <span className="text-[10px] font-semibold text-accent uppercase">
                    {sweep.param_y.target_slot ?? "Model"}
                  </span>
                )}
              </div>

              {sweep.use_param_y && sweep.param_y ? (
                <>
                  <Select value={sweep.param_y.name} onValueChange={(name) => {
                      const selected = paramOptions.find((p) => p.name === name);
                      if (selected) {
                        updateSweep({
                          param_y: { ...selected },
                        });
                      }
                    }}>
                    <SelectTrigger className="h-9 w-full text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>{paramOptions.map((p) => <SelectItem key={p.name} value={p.name}>{p.label ?? p.name}</SelectItem>)}</SelectContent>
                  </Select>

                  <div className="grid grid-cols-3 gap-2 pt-1">
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-ink-faint">Min</label>
                      <Input
                        type="number"
                        step="any"
                        className="h-8 px-2 py-1 text-xs font-mono"
                        value={sweep.param_y.min}
                        onChange={(e) =>
                          updateSweep({
                            param_y: { ...sweep.param_y!, min: Number(e.target.value) },
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-ink-faint">Max</label>
                      <Input
                        type="number"
                        step="any"
                        className="h-8 px-2 py-1 text-xs font-mono"
                        value={sweep.param_y.max}
                        onChange={(e) =>
                          updateSweep({
                            param_y: { ...sweep.param_y!, max: Number(e.target.value) },
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-ink-faint">Step</label>
                      <Input
                        type="number"
                        step="any"
                        className="h-8 px-2 py-1 text-xs font-mono"
                        value={sweep.param_y.step}
                        onChange={(e) =>
                          updateSweep({
                            param_y: { ...sweep.param_y!, step: Number(e.target.value) },
                          })
                        }
                      />
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex h-24 items-center justify-center text-xs text-ink-muted">
                  1D Sweep (Secondary Parameter disabled)
                </div>
              )}
            </div>
          </div>

          {/* Search Strategy & Objective */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-line/60">
            <div>
              <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
                Search Strategy
              </label>
              <Select value={normalizeSearchStrategy(sweep.strategy_type)} onValueChange={(strategy_type) => updateSweep({ strategy_type: normalizeSearchStrategy(strategy_type) })}>
                <SelectTrigger className="h-9 w-full text-xs"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="euler">Euler Step-Search</SelectItem><SelectItem value="grid">Grid Search (Cartesian Exhaustive)</SelectItem></SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
                Optimization Objective
              </label>
              <Select value={sweep.objective} onValueChange={(objective) => updateSweep({ objective: objective as OptimizationSweepConfig["objective"] })}>
                <SelectTrigger className="h-9 w-full text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="sharpe_ratio">Maximize Sharpe Ratio</SelectItem>
                  <SelectItem value="sortino_ratio">Maximize Sortino Ratio</SelectItem>
                  <SelectItem value="total_return">Maximize Total Return</SelectItem>
                  <SelectItem value="calmar_ratio">Maximize Calmar Ratio (Return / Max DD)</SelectItem>
                  <SelectItem value="min_drawdown">Minimize Drawdown</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1">
                Post-hoc heatmap filter
              </label>
              <div className="rounded border border-line bg-surface px-2.5 py-1.5 text-[11px] font-mono text-ink flex items-center justify-between">
                <span>DD ≤ 20%, Trades ≥ 15</span>
                <span className="text-ink-muted font-semibold">passes_constraints</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
