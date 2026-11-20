import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { fetchMultiRunCompare } from "../api/backtests";
import type { MultiRunCompareRunItem } from "../types";
import { MultiEquityCurveChart } from "./MultiEquityCurveChart";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

const RUN_COLORS = [
  { stroke: "#38bdf8", bg: "bg-sky-500/20 text-sky-300 border-sky-500/40", hex: "#38bdf8" },
  { stroke: "#34d399", bg: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40", hex: "#34d399" },
  { stroke: "#fbbf24", bg: "bg-amber-500/20 text-amber-300 border-amber-500/40", hex: "#fbbf24" },
  { stroke: "#c084fc", bg: "bg-purple-500/20 text-purple-300 border-purple-500/40", hex: "#c084fc" },
  { stroke: "#f87171", bg: "bg-rose-500/20 text-rose-300 border-rose-500/40", hex: "#f87171" },
  { stroke: "#94a3b8", bg: "bg-slate-500/20 text-slate-300 border-slate-500/40", hex: "#94a3b8" },
];

function formatPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  const pct = val * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function formatNum(val: number | null | undefined, digits = 2): string {
  if (val == null || Number.isNaN(val)) return "—";
  return val.toFixed(digits);
}

function formatDollar(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `$${val.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function MultiRunCompareView({
  runIds,
  onClose,
  onSelectRun,
}: {
  runIds: string[];
  onClose: () => void;
  onSelectRun?: (runId: string) => void;
}) {
  const compareQuery = useQuery({
    queryKey: ["backtest-compare", ...runIds],
    queryFn: () => fetchMultiRunCompare(runIds),
    enabled: runIds.length > 0,
  });

  const runs = compareQuery.data?.runs ?? [];

  // Determine best value in each metric for subtle highlighting
  const bests = useMemo(() => {
    if (runs.length === 0) return {};
    const valid = (fn: (r: MultiRunCompareRunItem) => number | null | undefined) =>
      runs.map(fn).filter((v): v is number => v != null && !Number.isNaN(v));

    const maxRet = Math.max(...valid((r) => r.metrics.total_return));
    const maxSharpe = Math.max(...valid((r) => r.metrics.sharpe_ratio));
    const minDd = Math.min(...valid((r) => r.metrics.max_drawdown));
    const maxWinRate = Math.max(...valid((r) => r.metrics.win_rate));
    const maxProfitFactor = Math.max(...valid((r) => r.metrics.profit_factor));

    return { maxRet, maxSharpe, minDd, maxWinRate, maxProfitFactor };
  }, [runs]);

  if (compareQuery.isLoading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-8 text-[12px] text-ink-muted">
        Loading multi-run comparison data…
      </div>
    );
  }

  if (compareQuery.isError || runs.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-8 text-[12px] text-danger">
        {compareQuery.error ? (compareQuery.error as Error).message : "No run comparison data returned."}
        <Button
          type="button"
          onClick={onClose}
          className="mt-3"
          variant="outline"
          size="sm"
        >
          Back to Single Run
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-[14px] font-bold text-ink">
              Multi-Run Strategy Comparison
            </h2>
            <span className="rounded bg-accent/20 px-2 py-0.5 text-[11px] font-semibold text-accent-ink">
              {runs.length} Runs Selected
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-ink-muted">
            Side-by-side normalized equity curves and quantitative performance metrics.
          </p>
        </div>

        <Button type="button" onClick={onClose} variant="outline" size="sm">
          Exit Comparison
        </Button>
      </div>

      {/* Multi-Equity Curve Chart */}
      <MultiEquityCurveChart runs={runs} />

      {/* Side-by-Side Comparative Scorecard Table */}
      <Card className="p-3.5 shadow-none">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
          Performance Scorecard Matrix
        </h4>

        <div className="mt-3 space-y-3 md:hidden">
          {runs.map((run, index) => {
            const color = RUN_COLORS[index % RUN_COLORS.length];
            const metrics = [
              ["Total return", formatPct(run.metrics.total_return)],
              ["Annual return", formatPct(run.metrics.annual_return)],
              ["Sharpe ratio", formatNum(run.metrics.sharpe_ratio)],
              ["Sortino ratio", formatNum(run.metrics.sortino_ratio)],
              ["Max drawdown", formatPct(run.metrics.max_drawdown)],
              ["Win rate", formatPct(run.metrics.win_rate)],
              ["Profit factor", formatNum(run.metrics.profit_factor)],
              ["Trade expectancy", run.metrics.expectancy == null ? "—" : `+${run.metrics.expectancy.toFixed(3)}`],
              ["Trades / orders", `${run.metrics.total_trades ?? "—"} / ${run.metrics.total_orders ?? "—"}`],
              ["Execution fees", formatDollar(run.metrics.total_fees)],
              ["Win / loss streak", `${run.metrics.max_consecutive_wins ?? "—"} / ${run.metrics.max_consecutive_losses ?? "—"}`],
            ];
            return (
              <Card key={run.run_id} className="p-3 shadow-none">
                <div className="flex min-w-0 items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color.hex }} />
                      <Button type="button" variant="link" size="sm" className="h-auto min-w-0 justify-start p-0 font-mono" onClick={() => onSelectRun?.(run.run_id)} title={`Inspect run ${run.run_id}`}>
                        {run.run_id.slice(0, 8)}…{run.run_id.slice(-4)}
                      </Button>
                    </div>
                    <p className="mt-1 break-all text-[11px] text-muted-foreground">{run.ir_id || "No strategy ID"}</p>
                  </div>
                  <Badge variant="secondary" className="shrink-0">Run {index + 1}</Badge>
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  {run.period_start || "—"} → {run.period_end || "—"}
                </p>
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t pt-3">
                  {metrics.map(([label, value]) => (
                    <div key={label} className="min-w-0">
                      <dt className="text-[10px] text-muted-foreground">{label}</dt>
                      <dd className="mt-0.5 truncate font-mono text-xs font-medium tabular-nums text-foreground" title={value}>{value}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            );
          })}
        </div>

        <div className="mt-3 hidden overflow-x-auto md:block">
          <WorkspaceTable className="w-full text-left text-[11px]">
            <WorkspaceTableHeader>
              <WorkspaceTableRow className="border-b border-line bg-surface-sunk text-ink-faint">
                <WorkspaceTableHead className="px-3 py-2 font-semibold">Metric</WorkspaceTableHead>
                {runs.map((r, i) => {
                  const color = RUN_COLORS[i % RUN_COLORS.length];
                  return (
                    <WorkspaceTableHead key={r.run_id} className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{ backgroundColor: color.hex }}
                        />
                        <Button
                          type="button"
                          onClick={() => onSelectRun && onSelectRun(r.run_id)}
                          variant="link"
                          size="sm"
                          className="h-auto justify-start p-0 font-mono font-bold text-ink"
                          title={`Inspect run ${r.run_id}`}
                        >
                          {r.run_id.slice(0, 8)}…{r.run_id.slice(-4)}
                        </Button>
                      </div>
                    </WorkspaceTableHead>
                  );
                })}
              </WorkspaceTableRow>
            </WorkspaceTableHeader>
            <WorkspaceTableBody className="divide-y divide-line/60 font-mono">
              {/* Strategy ir_id */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Strategy Model</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 text-[10.5px] text-ink break-all">
                    {r.ir_id || "—"}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Period */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Backtest Period</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 text-[10.5px] text-ink-muted">
                    {r.period_start || "—"} → {r.period_end || "—"}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Total Return */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Total Return</WorkspaceTableCell>
                {runs.map((r) => {
                  const isBest = r.metrics.total_return != null && r.metrics.total_return === bests.maxRet;
                  return (
                    <WorkspaceTableCell key={r.run_id} className={`px-3 py-1.5 font-bold tabular-nums ${
                      isBest ? "text-emerald-400 bg-emerald-500/10" : r.metrics.total_return && r.metrics.total_return >= 0 ? "text-emerald-300" : "text-rose-400"
                    }`}>
                      {formatPct(r.metrics.total_return)} {isBest ? "★" : ""}
                    </WorkspaceTableCell>
                  );
                })}
              </WorkspaceTableRow>

              {/* Annual Return */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Annual Return</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {formatPct(r.metrics.annual_return)}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Sharpe Ratio */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Sharpe Ratio</WorkspaceTableCell>
                {runs.map((r) => {
                  const isBest = r.metrics.sharpe_ratio != null && r.metrics.sharpe_ratio === bests.maxSharpe;
                  return (
                    <WorkspaceTableCell key={r.run_id} className={`px-3 py-1.5 tabular-nums ${isBest ? "font-bold text-ink bg-surface-sunk" : "text-ink"}`}>
                      {formatNum(r.metrics.sharpe_ratio)} {isBest ? "★" : ""}
                    </WorkspaceTableCell>
                  );
                })}
              </WorkspaceTableRow>

              {/* Sortino Ratio */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Sortino Ratio</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {formatNum(r.metrics.sortino_ratio)}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Max Drawdown */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Max Drawdown</WorkspaceTableCell>
                {runs.map((r) => {
                  const isBest = r.metrics.max_drawdown != null && r.metrics.max_drawdown === bests.minDd;
                  return (
                    <WorkspaceTableCell key={r.run_id} className={`px-3 py-1.5 tabular-nums ${isBest ? "font-bold text-emerald-400 bg-emerald-500/10" : "text-warn"}`}>
                      {formatPct(r.metrics.max_drawdown)} {isBest ? "★" : ""}
                    </WorkspaceTableCell>
                  );
                })}
              </WorkspaceTableRow>

              {/* Win Rate */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Win Rate</WorkspaceTableCell>
                {runs.map((r) => {
                  const isBest = r.metrics.win_rate != null && r.metrics.win_rate === bests.maxWinRate;
                  return (
                    <WorkspaceTableCell key={r.run_id} className={`px-3 py-1.5 tabular-nums ${isBest ? "font-bold text-emerald-400 bg-emerald-500/10" : "text-ink"}`}>
                      {formatPct(r.metrics.win_rate)} {isBest ? "★" : ""}
                    </WorkspaceTableCell>
                  );
                })}
              </WorkspaceTableRow>

              {/* Profit Factor */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Profit Factor</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {formatNum(r.metrics.profit_factor)}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Expectancy */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Trade Expectancy</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-emerald-400">
                    {r.metrics.expectancy != null ? `+${r.metrics.expectancy.toFixed(3)}` : "—"}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Total Trades / Orders */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Total Trades / Orders</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {r.metrics.total_trades ?? "—"} trades · {r.metrics.total_orders ?? "—"} orders
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Total Execution Fees */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Total Fees ($)</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink-muted">
                    {formatDollar(r.metrics.total_fees)}
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>

              {/* Max Streaks */}
              <WorkspaceTableRow className="hover:bg-surface-sunk/40">
                <WorkspaceTableCell className="px-3 py-1.5 font-sans font-medium text-ink-muted">Max Win / Loss Streak</WorkspaceTableCell>
                {runs.map((r) => (
                  <WorkspaceTableCell key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    <span className="text-emerald-400">{r.metrics.max_consecutive_wins ?? "—"}W</span>
                    <span className="text-ink-faint"> · </span>
                    <span className="text-rose-400">{r.metrics.max_consecutive_losses ?? "—"}L</span>
                  </WorkspaceTableCell>
                ))}
              </WorkspaceTableRow>
            </WorkspaceTableBody>
          </WorkspaceTable>
        </div>
      </Card>
    </div>
  );
}
