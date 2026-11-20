import { useMemo, useState } from "react";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";
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

  const renderStatus = (run: BacktestRunSummary) => {
    const variant = run.status === "done"
      ? "success"
      : run.status === "running"
        ? "info"
        : run.status === "failed"
          ? "destructive"
          : "warning";
    const label = run.status === "running" && run.progress_pct
      ? `Running ${Math.round(run.progress_pct * 100)}%`
      : run.status || "Pending";
    return <Badge variant={variant} className="w-fit px-2 py-0.5 text-[10px] uppercase">{label}</Badge>;
  };

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
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-xs">
      <div className="space-y-2 overflow-y-auto p-2 md:hidden">
        {sortedRuns.map((run) => {
          const isDone = run.status === "done";
          const title = run.spec_title || run.ir_id || "Untitled Strategy";
          return (
            <Card
              key={run.run_id}
              data-testid={`run-card-${run.run_id}`}
              className={`space-y-3 p-3 shadow-none ${run.run_id === selectedRunId ? "border-primary ring-1 ring-primary/30" : ""}`}
            >
              <div className="flex min-w-0 items-start gap-2">
                <Checkbox
                  checked={checkedRunIds.includes(run.run_id)}
                  disabled={!isDone}
                  onCheckedChange={() => onToggleCheck(run.run_id)}
                  aria-label={`Select run ${run.run_id} for comparison`}
                  className="mt-1 shrink-0"
                />
                <div className="min-w-0 flex-1">
                  <Button
                    type="button"
                    variant="link"
                    onClick={() => onSelectRun(run.run_id)}
                    className="h-auto max-w-full justify-start whitespace-normal p-0 text-left text-sm font-semibold"
                  >
                    {title}
                  </Button>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted-foreground">
                    {renderStatus(run)}
                    {run.is_shared ? <Badge variant="muted" className="px-2 py-0.5 text-[10px]">Shared</Badge> : null}
                    <span>{run.run_timestamp?.slice(0, 16) || "—"}</span>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Metric label="Return" value={formatPct(run.total_return)} />
                <Metric label="Sharpe" value={formatNum(run.sharpe_ratio)} />
                <Metric label="Max drawdown" value={formatPct(run.max_drawdown)} />
                <Metric label="Win rate" value={formatPct(run.win_rate)} />
              </div>
              <div className="flex flex-wrap items-center gap-1.5 border-t pt-2">
                <Button type="button" size="sm" variant="outline" onClick={() => onSelectRun(run.run_id)}>Inspect</Button>
                {onEditInComposer ? <Button type="button" size="sm" variant="ghost" onClick={() => onEditInComposer(run)}>Compose</Button> : null}
                {onPromoteRun && isDone ? <Button type="button" size="sm" variant="ghost" onClick={() => onPromoteRun(run.run_id)}>Promote</Button> : null}
                {onViewLog && run.status === "failed" ? <Button type="button" size="sm" variant="ghost" onClick={() => onViewLog(run.run_id, run.ir_id, run.status)}>View log</Button> : null}
              </div>
            </Card>
          );
        })}
      </div>
      <div className="hidden min-h-0 flex-1 overflow-auto md:block">
        <WorkspaceTable className="w-full text-left text-[11.5px] border-collapse">
          <WorkspaceTableHeader className="sticky top-0 z-20 border-b border-line bg-surface-sunk/95 backdrop-blur-xs text-ink-faint">
            <WorkspaceTableRow>
              <WorkspaceTableHead className="w-9 px-2.5 py-2 text-center">
                <span className="sr-only">Select</span>
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 hover:text-ink select-none"
                onClick={() => handleSort("status")}
              >
                Status {sortKey === "status" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
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
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 hover:text-ink select-none"
                onClick={() => handleSort("alpha_type")}
              >
                Alpha Model {sortKey === "alpha_type" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("total_return")}
              >
                Return % {sortKey === "total_return" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("sharpe_ratio")}
              >
                Sharpe {sortKey === "sharpe_ratio" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("max_drawdown")}
              >
                Max DD {sortKey === "max_drawdown" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("win_rate")}
              >
                Win Rate {sortKey === "win_rate" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead
                className="cursor-pointer px-2.5 py-2 text-right hover:text-ink select-none"
                onClick={() => handleSort("total_orders")}
              >
                Orders {sortKey === "total_orders" ? (sortDesc ? "▼" : "▲") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="px-2.5 py-2 text-center">Actions</WorkspaceTableHead>
            </WorkspaceTableRow>
          </WorkspaceTableHeader>
          <WorkspaceTableBody className="divide-y divide-line/60">
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
                <WorkspaceTableRow
                  key={`${r.run_id}-${r.run_timestamp || ""}-${idx}`}
                  onClick={() => onSelectRun(r.run_id)}
                  className={`transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-accent-soft/70 border-l-2 border-l-accent"
                      : "hover:bg-surface-sunk/60"
                  }`}
                >
                  {/* Checkbox for Compare */}
                  <WorkspaceTableCell
                    className="px-2.5 py-2 text-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Checkbox
                      checked={isChecked}
                      disabled={!isDone}
                      onCheckedChange={() => onToggleCheck(r.run_id)}
                      aria-label={`Select run ${r.run_id} for comparison`}
                      className="justify-center"
                    />
                  </WorkspaceTableCell>

                  {/* Status Badge */}
                  <WorkspaceTableCell className="px-2.5 py-2 whitespace-nowrap">
                    {isDone || isRunning || !isFailed ? (
                      renderStatus(r)
                    ) : (
                      <div className="inline-flex items-center gap-1">
                        <Badge variant="destructive" title={r.error_message || "Execution failed"} className="px-2 py-0.5 text-[10px] uppercase">Failed</Badge>
                        {onViewLog ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            onClick={(e) => {
                              e.stopPropagation();
                              onViewLog(r.run_id, r.ir_id, r.status);
                            }}
                            className="h-7 w-7"
                            aria-label={`View log for ${r.run_id}`}
                            title="View log"
                          >
                            📜
                          </Button>
                        ) : null}
                      </div>
                    )}
                  </WorkspaceTableCell>

                  {/* Run / Strategy Spec Column */}
                  <WorkspaceTableCell className="px-2.5 py-2">
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-ink truncate max-w-[280px]">
                          {r.spec_title || r.ir_id || "Untitled Strategy"}
                        </span>
                        {r.is_shared ? <Badge variant="muted" className="px-2 py-0.5 text-[10px]">Shared</Badge> : null}
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
                  </WorkspaceTableCell>

                  {/* Alpha Model & Framework Slots */}
                  <WorkspaceTableCell className="px-2.5 py-2 whitespace-nowrap">
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
                  </WorkspaceTableCell>

                  {/* Total Return % */}
                  <WorkspaceTableCell className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
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
                  </WorkspaceTableCell>

                  {/* Sharpe Ratio */}
                  <WorkspaceTableCell className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
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
                  </WorkspaceTableCell>

                  {/* Max Drawdown % */}
                  <WorkspaceTableCell className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
                    {r.max_drawdown != null ? (
                      <span className="font-semibold text-rose-400/90">
                        {formatPct(r.max_drawdown)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </WorkspaceTableCell>

                  {/* Win Rate % */}
                  <WorkspaceTableCell className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap">
                    {r.win_rate != null ? (
                      <span className="text-ink">
                        {formatPct(r.win_rate)}
                      </span>
                    ) : (
                      <span className="text-ink-faint">—</span>
                    )}
                  </WorkspaceTableCell>

                  {/* Total Orders */}
                  <WorkspaceTableCell className="px-2.5 py-2 text-right font-mono tabular-nums whitespace-nowrap text-ink-muted">
                    {r.total_orders != null ? r.total_orders.toLocaleString() : "—"}
                  </WorkspaceTableCell>

                  {/* Actions */}
                  <WorkspaceTableCell
                    className="px-2.5 py-2 text-center whitespace-nowrap"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-center gap-1.5">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => onSelectRun(r.run_id)}
                        className="h-7 px-2 text-[10px]"
                        title="Inspect run performance and charts"
                      >
                        Inspect
                      </Button>
                      {onEditInComposer ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onEditInComposer(r)}
                          className="h-7 px-2 text-[10px]"
                          title="Load this spec into Strategy Composer"
                        >
                          <span>✏️</span>
                          <span>Compose</span>
                        </Button>
                      ) : null}
                      {onPromoteRun && isDone ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onPromoteRun(r.run_id)}
                          className="h-7 px-2 text-[10px]"
                          title="Promote to paper deployment"
                        >
                          Promote
                        </Button>
                      ) : null}
                    </div>
                  </WorkspaceTableCell>
                </WorkspaceTableRow>
              );
            })}
          </WorkspaceTableBody>
        </WorkspaceTable>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md bg-muted/50 px-2 py-1.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="truncate font-mono text-xs font-semibold tabular-nums">{value}</div>
    </div>
  );
}
