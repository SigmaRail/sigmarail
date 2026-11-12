import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { fetchMultiRunCompare } from "../api/backtests";
import type { MultiRunCompareRunItem } from "../types";
import { MultiEquityCurveChart } from "./MultiEquityCurveChart";

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
        <button
          type="button"
          onClick={onClose}
          className="mt-3 rounded border border-line bg-surface px-3 py-1.5 text-[12px] text-ink hover:bg-surface-sunk"
        >
          Back to Single Run
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 space-y-4">
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

        <button
          type="button"
          onClick={onClose}
          className="rounded border border-line bg-surface px-3 py-1 text-[12px] font-medium text-ink hover:bg-surface-sunk"
        >
          Exit Comparison
        </button>
      </div>

      {/* Multi-Equity Curve Chart */}
      <MultiEquityCurveChart runs={runs} />

      {/* Side-by-Side Comparative Scorecard Table */}
      <section className="rounded border border-line bg-surface p-3.5">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
          Performance Scorecard Matrix
        </h4>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-line bg-surface-sunk text-ink-faint">
                <th className="px-3 py-2 font-semibold">Metric</th>
                {runs.map((r, i) => {
                  const color = RUN_COLORS[i % RUN_COLORS.length];
                  return (
                    <th key={r.run_id} className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{ backgroundColor: color.hex }}
                        />
                        <button
                          type="button"
                          onClick={() => onSelectRun && onSelectRun(r.run_id)}
                          className="font-mono font-bold text-ink hover:underline"
                          title={`Inspect run ${r.run_id}`}
                        >
                          {r.run_id.slice(0, 8)}…{r.run_id.slice(-4)}
                        </button>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60 font-mono">
              {/* Strategy ir_id */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Strategy Model</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 text-[10.5px] text-ink break-all">
                    {r.ir_id || "—"}
                  </td>
                ))}
              </tr>

              {/* Period */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Backtest Period</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 text-[10.5px] text-ink-muted">
                    {r.period_start || "—"} → {r.period_end || "—"}
                  </td>
                ))}
              </tr>

              {/* Total Return */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Total Return</td>
                {runs.map((r) => {
                  const isBest = r.metrics.total_return != null && r.metrics.total_return === bests.maxRet;
                  return (
                    <td key={r.run_id} className={`px-3 py-1.5 font-bold tabular-nums ${
                      isBest ? "text-emerald-400 bg-emerald-500/10" : r.metrics.total_return && r.metrics.total_return >= 0 ? "text-emerald-300" : "text-rose-400"
                    }`}>
                      {formatPct(r.metrics.total_return)} {isBest ? "★" : ""}
                    </td>
                  );
                })}
              </tr>

              {/* Annual Return */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Annual Return</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {formatPct(r.metrics.annual_return)}
                  </td>
                ))}
              </tr>

              {/* Sharpe Ratio */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Sharpe Ratio</td>
                {runs.map((r) => {
                  const isBest = r.metrics.sharpe_ratio != null && r.metrics.sharpe_ratio === bests.maxSharpe;
                  return (
                    <td key={r.run_id} className={`px-3 py-1.5 tabular-nums ${isBest ? "font-bold text-ink bg-surface-sunk" : "text-ink"}`}>
                      {formatNum(r.metrics.sharpe_ratio)} {isBest ? "★" : ""}
                    </td>
                  );
                })}
              </tr>

              {/* Sortino Ratio */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Sortino Ratio</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {formatNum(r.metrics.sortino_ratio)}
                  </td>
                ))}
              </tr>

              {/* Max Drawdown */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Max Drawdown</td>
                {runs.map((r) => {
                  const isBest = r.metrics.max_drawdown != null && r.metrics.max_drawdown === bests.minDd;
                  return (
                    <td key={r.run_id} className={`px-3 py-1.5 tabular-nums ${isBest ? "font-bold text-emerald-400 bg-emerald-500/10" : "text-warn"}`}>
                      {formatPct(r.metrics.max_drawdown)} {isBest ? "★" : ""}
                    </td>
                  );
                })}
              </tr>

              {/* Win Rate */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Win Rate</td>
                {runs.map((r) => {
                  const isBest = r.metrics.win_rate != null && r.metrics.win_rate === bests.maxWinRate;
                  return (
                    <td key={r.run_id} className={`px-3 py-1.5 tabular-nums ${isBest ? "font-bold text-emerald-400 bg-emerald-500/10" : "text-ink"}`}>
                      {formatPct(r.metrics.win_rate)} {isBest ? "★" : ""}
                    </td>
                  );
                })}
              </tr>

              {/* Profit Factor */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Profit Factor</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {formatNum(r.metrics.profit_factor)}
                  </td>
                ))}
              </tr>

              {/* Expectancy */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Trade Expectancy</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-emerald-400">
                    {r.metrics.expectancy != null ? `+${r.metrics.expectancy.toFixed(3)}` : "—"}
                  </td>
                ))}
              </tr>

              {/* Total Trades / Orders */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Total Trades / Orders</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    {r.metrics.total_trades ?? "—"} trades · {r.metrics.total_orders ?? "—"} orders
                  </td>
                ))}
              </tr>

              {/* Total Execution Fees */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Total Fees ($)</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink-muted">
                    {formatDollar(r.metrics.total_fees)}
                  </td>
                ))}
              </tr>

              {/* Max Streaks */}
              <tr className="hover:bg-surface-sunk/40">
                <td className="px-3 py-1.5 font-sans font-medium text-ink-muted">Max Win / Loss Streak</td>
                {runs.map((r) => (
                  <td key={r.run_id} className="px-3 py-1.5 tabular-nums text-ink">
                    <span className="text-emerald-400">{r.metrics.max_consecutive_wins ?? "—"}W</span>
                    <span className="text-ink-faint"> · </span>
                    <span className="text-rose-400">{r.metrics.max_consecutive_losses ?? "—"}L</span>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
