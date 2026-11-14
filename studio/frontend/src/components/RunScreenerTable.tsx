import { useMemo, useState } from "react";
import type { BacktestRunSummary } from "../types";
import { CopyIdBadge } from "./CopyIdBadge";

function formatPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `${(val * 100).toFixed(2)}%`;
}

function formatNum(val: number | null | undefined, decimals = 2): string {
  if (val == null || Number.isNaN(val)) return "—";
  return val.toFixed(decimals);
}

type SortKey =
  | "run_timestamp"
  | "spec_title"
  | "total_return"
  | "sharpe_ratio"
  | "sortino_ratio"
  | "max_drawdown"
  | "win_rate"
  | "total_orders"
  | "alpha_type"
  | "status";

export function RunScreenerTable({
  runs,
  selectedRunId,
  onSelectRun,
  checkedRunIds,
  onToggleCheck,
  onPromoteRun,
  onEditInComposer,
  onViewLog,
}: {
  runs: BacktestRunSummary[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  checkedRunIds: string[];
  onToggleCheck: (runId: string) => void;
  onPromoteRun?: (runId: string) => void;
  onEditInComposer?: (run: BacktestRunSummary) => void;
  onViewLog?: (jobId: string, irId?: string | null, status?: string) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("run_timestamp");
  const [sortDesc, setSortDesc] = useState(true);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  const sortedRuns = useMemo(() => {
    return [...runs].sort((a, b) => {
      let vA: any = a[sortKey as keyof BacktestRunSummary];
      let vB: any = b[sortKey as keyof BacktestRunSummary];

      if (sortKey === "run_timestamp") {
        vA = a.run_timestamp || "";
        vB = b.run_timestamp || "";
      } else if (typeof vA === "number" || typeof vB === "number") {
        vA = vA ?? -999999;
        vB = vB ?? -999999;
      } else {
        vA = (vA || "").toString().toLowerCase();
        vB = (vB || "").toString().toLowerCase();
        const tA = a.run_timestamp ? new Date(a.run_timestamp).getTime() : 0;
        const tB = b.run_timestamp ? new Date(b.run_timestamp).getTime() : 0;
        if (tA < tB) return sortDesc ? 1 : -1;
        if (tA > tB) return sortDesc ? -1 : 1;
        return 0;
      }

      if (vA < vB) return sortDesc ? 1 : -1;
      if (vA > vB) return sortDesc ? -1 : 1;
      if (sortKey === "spec_title") {
        vA = a.spec_title || a.ir_id || "";
        vB = b.spec_title || b.ir_id || "";
      }

      // Handle null/undefined/NaN: always place at bottom regardless of sort direction
      const isNullA = vA == null || (typeof vA === "number" && Number.isNaN(vA));
      const isNullB = vB == null || (typeof vB === "number" && Number.isNaN(vB));
      if (isNullA && isNullB) return 0;
      if (isNullA) return 1;
      if (isNullB) return -1;

      // Numeric comparison
      if (
        sortKey === "total_return" ||
        sortKey === "sharpe_ratio" ||
        sortKey === "sortino_ratio" ||
        sortKey === "max_drawdown" ||
        sortKey === "win_rate" ||
        sortKey === "total_orders"
      ) {
        const numA = Number(vA);
        const numB = Number(vB);
        if (numA < numB) return sortDesc ? 1 : -1;
        if (numA > numB) return sortDesc ? -1 : 1;
        return 0;
      }

      // String comparison
      const strA = String(vA).toLowerCase();
      const strB = String(vB).toLowerCase();
      if (strA < strB) return sortDesc ? 1 : -1;
      if (strA > strB) return sortDesc ? -1 : 1;
      return 0;
    });
  }, [runs, sortKey, sortDesc]);

  if (runs.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center rounded-lg border border-line bg-surface p-8 text-center text-ink-muted">
        <p className="text-sm font-semibold">No Strategy Runs Match Current Filters</p>
        <p className="mt-1 text-xs text-ink-faint">
          Try clearing search keywords or resetting performance threshold filters.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-xs">
      <div className="overflow-x-auto overflow-y-auto max-h-[calc(100vh-220px)]">
        <table className="w-full text-left text-[11.5px] border-collapse">
          <thead className="sticky top-0 z-20 border-b border-line bg-surface-sunk/95 backdrop-blur-xs text-ink-faint">
            <tr>
              <th className="w-9 px-2.5 py-2 text-center">
                <span className="sr-only">Select</span>
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 hover:text-ink select-none"
                onClick={() => handleSort("status")}
              >
                Status {sortKey === "status" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 hover:text-ink select-none min-w-[200px]"
                onClick={() => handleSort(sortKey === "run_timestamp" ? "spec_title" : "run_timestamp")}
                title="Click to toggle sort between Spec Title and Date/Time"
              >
                Run / Strategy Spec{" "}
                {sortKey === "run_timestamp"
                  ? sortDesc
                    ? "(Time) ▼"
                    : "(Time) ▲"
                  : sortKey === "spec_title"
                    ? sortDesc
                      ? "(A-Z) ▼"
                      : "(Z-A) ▲"
                    : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 hover:text-ink select-none"
                onClick={() => handleSort("alpha_type")}
              >
                Alpha Model {sortKey === "alpha_type" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("total_return")}
              >
                Return % {sortKey === "total_return" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("sharpe_ratio")}
              >
                Sharpe {sortKey === "sharpe_ratio" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("max_drawdown")}
              >
                Max DD {sortKey === "max_drawdown" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("win_rate")}
              >
                Win Rate {sortKey === "win_rate" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("total_orders")}
              >
                Orders {sortKey === "total_orders" ? (sortDesc ? "▼" : "▲") : ""}
              </th>
              <th className="px-2.5 py-2 text-center">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {sortedRuns.map((r, idx) => {
              const isSelected = r.run_id === selectedRunId;
              const isChecked = checkedRunIds.includes(r.run_id);
              const isDone = r.status === "done";
              const isRunning = r.status === "running";
              const isFailed = r.status === "failed";
              const ret = r.total_return ?? 0;
              const isProfit = ret >= 0;
              const sharpe = r.sharpe_ratio;

              return (
                <tr
                  key={`${r.run_id}-${r.run_timestamp || ""}-${idx}`}
                  onClick={() => onSelectRun(r.run_id)}
                  className={`transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-accent-soft/70 border-l-2 border-l-accent"
                      : "hover:bg-surface-sunk/60"
                  }`}
                >
                  {/* Checkbox for Compare */}
                  <td
                    className="px-2.5 py-2 text-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      disabled={!isDone}
                      onChange={() => onToggleCheck(r.run_id)}
                      className="rounded border-line bg-surface text-accent focus:ring-accent disabled:opacity-30"
                    />
                  </td>

                  {/* Status Badge */}
                  <td className="px-2.5 py-2 whitespace-nowrap">
                    {isDone ? (
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 border border-emerald-500/30 px-1.5 py-0.5 font-mono text-[9.5px] font-bold text-emerald-400 uppercase">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        Done
                      </span>
                    ) : isRunning ? (
                      <span className="inline-flex items-center gap-1 rounded bg-sky-500/15 border border-sky-500/30 px-1.5 py-0.5 font-mono text-[9.5px] font-bold text-sky-400 uppercase">
                        <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
                        Running {r.progress_pct ? `${Math.round(r.progress_pct * 100)}%` : ""}
                      </span>
                    ) : isFailed ? (
                      <div className="inline-flex items-center gap-1">
                        <span
                          className="inline-flex items-center gap-1 rounded bg-rose-500/15 border border-rose-500/30 px-1.5 py-0.5 font-mono text-[9.5px] font-bold text-rose-400 uppercase"
                          title={r.error_message || "Execution failed"}
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                          Failed
                        </span>
                        {onViewLog ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onViewLog(r.run_id, r.ir_id, r.status);
                            }}
                            className="text-[10.5px] text-ink-muted hover:text-ink transition-colors"
                            title="View log"
                          >
                            📜
                          </button>
                        ) : null}
                      </div>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 font-mono text-[9.5px] font-bold text-amber-400 uppercase">
                        {r.status || "Pending"}
                      </span>
                    )}
                  </td>

                  {/* Run / Strategy Spec Column */}
                  <td className="px-2.5 py-2">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-ink truncate max-w-[280px]">
                          {r.spec_title || r.ir_id || "Untitled Strategy"}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-ink-muted font-mono">
                        <CopyIdBadge
                          id={r.run_id}
                          label="run"
                          head={6}
                          tail={4}
                          sqlQuery={`SELECT * FROM strategy_runs FINAL WHERE run_id = '${r.run_id}'`}
                        />
                        <span>{r.run_timestamp?.slice(0, 16) || "—"}</span>
                      </div>
                    </div>
                  </td>

                  {/* Alpha Model & Framework Slots */}
                  <td className="px-2.5 py-2 whitespace-nowrap">
                    <div className="flex flex-col gap-1">
                      {r.alpha_type ? (
                        <span className="inline-block rounded bg-surface-sunk border border-line/70 px-1.5 py-0.5 font-mono text-[10px] font-medium text-accent-ink">
                          {r.alpha_type}
                        </span>
                      ) : (
                        <span className="text-[10px] text-ink-faint">—</span>
                      )}
                      {r.risk_type ? (
                        <span className="text-[9.5px] text-ink-muted truncate max-w-[140px]" title={r.risk_type}>
                          Risk: {r.risk_type.replace("Model", "").replace("Security", "")}
                        </span>
                      ) : null}
                    </div>
                  </td>

                  {/* Total Return % */}
                  <td className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
                    {r.total_return != null ? (
                      <span
                        className={`font-bold ${
                          isProfit ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isProfit ? "+" : ""}
                        {formatPct(r.total_return)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>

                  {/* Sharpe Ratio */}
                  <td className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
                    {sharpe != null ? (
                      <span
                        className={`inline-block rounded px-1.5 py-0.5 text-[10.5px] font-bold ${
                          sharpe >= 1.5
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : sharpe >= 1.0
                              ? "bg-emerald-500/10 text-emerald-400"
                              : sharpe >= 0.0
                                ? "bg-sky-500/10 text-sky-300"
                                : "bg-rose-500/10 text-rose-400"
                        }`}
                      >
                        {formatNum(sharpe)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>

                  {/* Max Drawdown % */}
                  <td className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
                    {r.max_drawdown != null ? (
                      <span className="font-semibold text-rose-400/90">
                        {formatPct(r.max_drawdown)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>

                  {/* Win Rate % */}
                  <td className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
                    {r.win_rate != null ? (
                      <span className="text-ink">
                        {formatPct(r.win_rate)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </td>

                  {/* Total Orders */}
                  <td className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap text-ink-muted">
                    {r.total_orders != null ? r.total_orders.toLocaleString() : "—"}
                  </td>

                  {/* Actions */}
                  <td
                    className="px-2.5 py-2 text-center whitespace-nowrap"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => onSelectRun(r.run_id)}
                        className="rounded bg-surface-sunk px-2 py-1 text-[10px] font-semibold text-ink hover:bg-accent/20 hover:text-accent-ink transition-colors"
                        title="Inspect run performance and charts"
                      >
                        Inspect
                      </button>
                      {onEditInComposer ? (
                        <button
                          type="button"
                          onClick={() => onEditInComposer(r)}
                          className="rounded bg-surface-sunk px-2 py-1 text-[10px] font-semibold text-accent hover:bg-accent/20 transition-colors flex items-center gap-1"
                          title="Load this spec into Strategy Composer"
                        >
                          <span>✏️</span>
                          <span>Compose</span>
                        </button>
                      ) : null}
                      {onPromoteRun && isDone ? (
                        <button
                          type="button"
                          onClick={() => onPromoteRun(r.run_id)}
                          className="rounded bg-surface-sunk px-1.5 py-1 text-[10px] text-ink-muted hover:text-accent transition-colors"
                          title="Promote to paper deployment"
                        >
                          🚀
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
