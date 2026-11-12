import { useQuery } from "@tanstack/react-query";
import { fetchBacktestReport, fetchRunEquityCurve, fetchRunMonthlyReturns } from "../api/backtests";
import { EquityCurveChart } from "./EquityCurveChart";
import { MonthlyReturnsHeatmap } from "./MonthlyReturnsHeatmap";
import { CopyIdBadge } from "./CopyIdBadge";
import type { OptimizerRunPoint } from "../types";

export function OptimizerRunInspector({
  runPoint,
  onOpenInRunsTab,
  onPromoteRun,
  onEditInComposer,
  oosDays = 0,
}: {
  runPoint: OptimizerRunPoint | null;
  onOpenInRunsTab?: (runId: string) => void;
  onPromoteRun?: (runId: string) => void;
  onEditInComposer?: (irId: string, runPoint: OptimizerRunPoint) => void;
  oosDays?: number;
}) {
  const runId = runPoint?.run_id ?? "";

  const reportQuery = useQuery({
    queryKey: ["backtest-report", runId],
    queryFn: () => fetchBacktestReport(runId),
    enabled: Boolean(runId),
  });

  const equityQuery = useQuery({
    queryKey: ["run-equity", runId],
    queryFn: () => fetchRunEquityCurve(runId),
    enabled: Boolean(runId),
  });

  const monthlyQuery = useQuery({
    queryKey: ["run-monthly", runId],
    queryFn: () => fetchRunMonthlyReturns(runId),
    enabled: Boolean(runId),
  });

  if (!runPoint) {
    return (
      <div className="flex h-full flex-col items-center justify-center rounded-lg border border-line bg-surface p-6 text-center text-ink-muted">
        <p className="text-sm font-semibold">No Variant Selected</p>
        <p className="mt-1 text-xs text-ink-faint">
          Click any scatter point or table row to inspect full performance diagnostics, equity curves, and monthly heatmaps.
        </p>
      </div>
    );
  }

  const m = reportQuery.data?.metrics;
  const metrics = {
    sharpe: m?.sharpe_ratio ?? runPoint.sharpe_ratio,
    sortino: m?.sortino_ratio ?? runPoint.sortino_ratio,
    total_return: m?.total_return ?? runPoint.total_return,
    annual_return: m?.annual_return ?? runPoint.annual_return,
    max_drawdown: m?.max_drawdown ?? runPoint.max_drawdown,
    win_rate: m?.win_rate ?? runPoint.win_rate,
    profit_factor: m?.profit_factor ?? runPoint.profit_factor,
    orders: m?.total_orders ?? runPoint.total_orders,
  };

  const stability = runPoint.stability_score ?? 1.0;
  const isPlateau = stability >= 0.7;

  return (
    <div data-testid="optimizer-run-inspector" className="flex h-full flex-col overflow-y-auto rounded-lg border border-line bg-surface p-3.5 shadow-sm space-y-3">
      {/* Header with Title & Direct Navigation */}
      <div className="flex items-start justify-between border-b border-line pb-2.5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-bold text-ink">Variant Diagnostics</span>
            <CopyIdBadge
              id={runId}
              label="Run ID"
              head={8}
              tail={6}
              sqlQuery={`SELECT * FROM strategy_runs FINAL WHERE run_id = '${runId}'`}
            />
          </div>
          <div className="mt-1">
            <CopyIdBadge
              id={runPoint.ir_id}
              label="Variant Spec"
              head={16}
              tail={6}
              sqlQuery={`SELECT * FROM strategy_algorithm_specs FINAL WHERE ir_id = '${runPoint.ir_id}'`}
            />
          </div>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {onEditInComposer && (
            <button
              type="button"
              onClick={() => onEditInComposer(runPoint.ir_id, runPoint)}
              className="rounded bg-accent text-accent-fg px-2.5 py-1 text-[11px] font-semibold hover:opacity-90 transition-opacity flex items-center gap-1"
              title="Load this optimized variant into Strategy Composer"
            >
              <span>✏️</span>
              <span>Edit in Composer</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => onOpenInRunsTab?.(runId)}
            className="rounded border border-line bg-surface-raised px-2 py-1 text-[11px] font-semibold text-accent hover:bg-surface-sunk transition-colors"
          >
            Full Analysis ↗
          </button>
          {onPromoteRun && (
            <button
              type="button"
              onClick={() => onPromoteRun(runId)}
              className="rounded bg-surface-sunk border border-line px-2 py-1 text-[11px] font-semibold text-ink hover:text-accent transition-colors"
            >
              Promote 🚀
            </button>
          )}
        </div>
      </div>

      {/* Parameter Set Pill Badges */}
      <div className="rounded border border-line bg-surface-sunk p-2.5">
        <span className="block text-[9.5px] font-bold uppercase tracking-wider text-ink-faint">
          Evaluated Parameter Set:
        </span>
        <div className="mt-1 flex flex-wrap gap-1.5 font-mono text-[11px]">
          {Object.entries(runPoint.parameters).map(([k, v]) => (
            <span key={k} className="rounded bg-surface px-2 py-0.5 text-accent border border-line">
              {k}: <span className="font-bold text-ink">{String(v)}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Quant Scorecards (8 Metrics + Stability Index) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Sharpe</span>
          <span className="block text-[14px] font-bold text-emerald-400">
            {metrics.sharpe != null ? metrics.sharpe.toFixed(2) : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Return</span>
          <span className={`block text-[14px] font-bold ${metrics.total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {metrics.total_return != null ? `${(metrics.total_return * 100).toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Max Drawdown</span>
          <span className="block text-[14px] font-bold text-rose-400">
            {metrics.max_drawdown != null ? `${(metrics.max_drawdown * 100).toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Win Rate</span>
          <span className="block text-[14px] font-bold text-ink">
            {metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Sortino</span>
          <span className="block text-[13px] font-bold text-ink">
            {metrics.sortino != null ? metrics.sortino.toFixed(2) : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Profit Factor</span>
          <span className="block text-[13px] font-bold text-ink">
            {metrics.profit_factor != null ? metrics.profit_factor.toFixed(2) : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Orders</span>
          <span className="block text-[13px] font-bold text-ink">
            {metrics.orders != null ? metrics.orders : "—"}
          </span>
        </div>
        <div className="rounded border border-line bg-surface-sunk p-2">
          <span className="block text-[9px] uppercase text-ink-faint">Stability</span>
          <span className={`block text-[13px] font-bold ${isPlateau ? "text-emerald-400" : "text-amber-400"}`}>
            {(stability * 100).toFixed(0)}% {isPlateau ? "🛡️" : "⚠️"}
          </span>
        </div>
      </div>

      {/* Out-of-Sample (OOS) Efficiency Badge if available */}
      {oosDays > 0 && runPoint.oos_sharpe_ratio != null && (
        <div className="flex items-center justify-between rounded border border-accent/30 bg-accent/10 px-3 py-1.5 text-[11px]">
          <span className="text-ink-muted">
            OOS Validation ({oosDays} days): <span className="font-bold text-ink">Sharpe {runPoint.oos_sharpe_ratio.toFixed(2)}</span>
          </span>
          <span className="font-bold text-accent">
            Efficiency: {((runPoint.oos_efficiency ?? 0.85) * 100).toFixed(0)}%
          </span>
        </div>
      )}

      {/* Equity Curve with IS/OOS Boundary */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">
            Cumulative Equity Curve {oosDays > 0 ? "(IS vs OOS Forward Test)" : ""}
          </span>
          {equityQuery.isLoading && <span className="text-[10px] text-ink-faint">Loading…</span>}
        </div>
        <div className="h-44 w-full rounded border border-line bg-surface-sunk p-1">
          {equityQuery.data?.points && equityQuery.data.points.length > 0 ? (
            <EquityCurveChart points={equityQuery.data.points} />
          ) : (
            <div className="flex h-full items-center justify-center text-[11px] text-ink-faint">
              {equityQuery.isLoading ? "Loading equity curve…" : "No equity data available"}
            </div>
          )}
        </div>
      </div>

      {/* Monthly Returns Heatmap */}
      <div className="space-y-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">
          Monthly Returns Matrix
        </span>
        {monthlyQuery.data ? (
          <MonthlyReturnsHeatmap data={monthlyQuery.data} isLoading={monthlyQuery.isLoading} />
        ) : (
          <div className="rounded border border-line bg-surface-sunk p-3 text-center text-[11px] text-ink-faint">
            {monthlyQuery.isLoading ? "Loading monthly returns…" : "Monthly matrix pending"}
          </div>
        )}
      </div>
    </div>
  );
}
