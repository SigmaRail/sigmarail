import { useEffect, useMemo, useState } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
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

  useEffect(() => {
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
      lean_project: "SigmaRailTradingLab",
    });
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent size="lg" className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle>Launch parameter sweep</DialogTitle>
            <Badge variant="muted">Backtest optimization</Badge>
          </div>
          <DialogDescription>Choose a strategy, evaluation period, and parameters to explore.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 text-sm">
          {/* Base Spec & Title */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium">Strategy</label>
              <Select value={baseIrId} onValueChange={setBaseIrId}>
                <SelectTrigger aria-label="Base strategy"><SelectValue placeholder="Choose a strategy" /></SelectTrigger>
                <SelectContent>{specs.map((s) => <SelectItem key={s.ir_id} value={s.ir_id}>{s.title || s.ir_id}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <label htmlFor="sweep-title" className="mb-1.5 block text-sm font-medium">Study name (optional)</label>
              <Input
                id="sweep-title"
                type="text"
                placeholder="e.g. Risk and exit sweep"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="h-10"
              />
            </div>
          </div>

          {/* Strategy & Objective */}
          <Card className="grid grid-cols-1 gap-3 p-3 shadow-none sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-sm font-medium">Search method</label>
              <Select value={strategyType} onValueChange={(value) => setStrategyType(value as "euler" | "grid")}>
                <SelectTrigger aria-label="Search method"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="euler">Adaptive search</SelectItem><SelectItem value="grid">Grid search</SelectItem></SelectContent>
              </Select>
              <span className="mt-1 block text-xs text-muted-foreground">
                {strategyType === "euler"
                  ? "Adaptive coarse sweep with automatic focal zoom."
                  : "Brute-force evaluation of all coordinate pairs."}
              </span>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium">Optimize for</label>
              <Select value={objective} onValueChange={setObjective}>
                <SelectTrigger aria-label="Optimization objective"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="sharpe_ratio">Sharpe ratio</SelectItem><SelectItem value="sortino_ratio">Sortino ratio</SelectItem><SelectItem value="total_return">Total return</SelectItem><SelectItem value="min_drawdown">Lower drawdown</SelectItem></SelectContent>
              </Select>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium">Parallel runs</label>
              <Select value={String(maxConcurrent)} onValueChange={(value) => setMaxConcurrent(Number(value))}>
                <SelectTrigger aria-label="Parallel runs"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="2">2</SelectItem><SelectItem value="4">4</SelectItem><SelectItem value="8">8</SelectItem></SelectContent>
              </Select>
            </div>
          </Card>

          {/* Date Range */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium">Start date</label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-10"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium">End date</label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="h-10"
              />
            </div>
          </div>

          {/* Parameter X Sweep */}
          <Card className="space-y-3 p-3 shadow-none">
            <span className="text-sm font-semibold">Primary parameter</span>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium">Parameter</label>
                <Select value={paramXName} onValueChange={setParamXName}>
                  <SelectTrigger aria-label="Primary parameter"><SelectValue /></SelectTrigger>
                  <SelectContent>{SWEEPABLE_PARAMETERS.map((p) => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium">Min</label>
                <Input
                  type="number"
                  step="any"
                  value={paramXMin}
                  onChange={(e) => setParamXMin(Number(e.target.value))}
                  className="h-10"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium">Max</label>
                <Input
                  type="number"
                  step="any"
                  value={paramXMax}
                  onChange={(e) => setParamXMax(Number(e.target.value))}
                  className="h-10"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium">Step</label>
                <Input
                  type="number"
                  step="any"
                  value={paramXStep}
                  onChange={(e) => setParamXStep(Number(e.target.value))}
                  className="h-10"
                />
              </div>
            </div>
          </Card>

          {/* Parameter Y Sweep */}
          <Card className="space-y-3 p-3 shadow-none">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">Secondary parameter</span>
              <Checkbox label="2D sweep" checked={useParamY} onCheckedChange={(checked) => setUseParamY(checked === true)} />
            </div>

            {useParamY && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <label className="mb-1.5 block text-xs font-medium">Parameter</label>
                  <Select value={paramYName} onValueChange={setParamYName}>
                    <SelectTrigger aria-label="Secondary parameter"><SelectValue /></SelectTrigger>
                    <SelectContent>{SWEEPABLE_PARAMETERS.map((p) => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium">Min</label>
                  <Input
                    type="number"
                    step="any"
                    value={paramYMin}
                    onChange={(e) => setParamYMin(Number(e.target.value))}
                    className="h-10"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium">Max</label>
                  <Input
                    type="number"
                    step="any"
                    value={paramYMax}
                    onChange={(e) => setParamYMax(Number(e.target.value))}
                    className="h-10"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium">Step</label>
                  <Input
                    type="number"
                    step="any"
                    value={paramYStep}
                    onChange={(e) => setParamYStep(Number(e.target.value))}
                    className="h-10"
                  />
                </div>
              </div>
            )}
          </Card>

          {/* Quant Constraints */}
          <Card className="space-y-2 p-3 shadow-none">
            <span className="block text-sm font-medium">
              Run constraints
            </span>
            <div className="flex flex-wrap gap-2 text-xs">
              {constraints.map((c, i) => (
                <Badge key={i} variant="muted">
                  {c.target} {c.operator === "lessOrEqual" ? "≤" : "≥"} {c.target_value}
                </Badge>
              ))}
            </div>
          </Card>

          {/* Modal Footer & Launch Trigger */}
          <DialogFooter className="items-center justify-between border-t pt-3 sm:flex-row">
            <span className="mr-auto text-sm text-muted-foreground">
              Estimated variants: <span className="font-semibold text-foreground">{totalRunsEstimate}</span>
            </span>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                onClick={onClose}
                variant="outline"
                size="sm"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isLaunching || !baseIrId}
                size="sm"
              >
                {isLaunching ? "Launching…" : "Launch sweep"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
