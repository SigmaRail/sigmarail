import { useState } from "react";
import type { OptimizerRunPoint } from "../types";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Button } from "@sb/webapp-core/components/ui/button";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

export function OptimizerRunsTable({
  points,
  selectedRunId,
  onSelectRunId,
  onCompareRuns,
}: {
  points: OptimizerRunPoint[];
  selectedRunId?: string | null;
  onSelectRunId?: (runId: string) => void;
  onCompareRuns?: (runIds: string[]) => void;
}) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filterConstraintsOnly, setFilterConstraintsOnly] = useState(false);
  const [sortKey, setSortKey] = useState<keyof OptimizerRunPoint>("sharpe_ratio");
  const [sortAsc, setSortAsc] = useState(false);

  function toggleSelectAll() {
    if (selectedIds.size === points.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(points.map((p) => p.run_id)));
    }
  }

  function toggleSelectOne(runId: string) {
    const next = new Set(selectedIds);
    if (next.has(runId)) {
      next.delete(runId);
    } else {
      next.add(runId);
    }
    setSelectedIds(next);
  }

  const sortedPoints = [...points]
    .filter((p) => (filterConstraintsOnly ? p.passes_constraints ?? true : true))
    .sort((a, b) => {
      const va = Number(a[sortKey] ?? 0);
      const vb = Number(b[sortKey] ?? 0);
      return sortAsc ? va - vb : vb - va;
    });

  function handleSort(key: keyof OptimizerRunPoint) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface p-3 shadow-sm">
      {/* Table Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-bold text-ink">Optimization Runs Leaderboard</span>
          <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10.5px] text-ink-muted">
            {sortedPoints.length} of {points.length} variants
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Checkbox
            label="Passes Constraints Only"
            checked={filterConstraintsOnly}
            onCheckedChange={(checked) => setFilterConstraintsOnly(checked === true)}
            aria-label="Passes Constraints Only"
            className="text-ink-muted"
          />

          {selectedIds.size > 1 && onCompareRuns && (
            <Button
              type="button"
              onClick={() => onCompareRuns(Array.from(selectedIds))}
              variant="default"
              size="sm"
              className="h-8 px-2.5 text-[11px]"
            >
              Compare Selected ({selectedIds.size}) 🔍
            </Button>
          )}
        </div>
      </div>

      {/* Table Body */}
      <div className="mt-2">
        <WorkspaceTable containerClassName="max-h-72" className="min-w-[640px] text-left text-[11px]">
          <WorkspaceTableHeader className="sticky top-0 z-[4] border-b border-line bg-surface-raised text-[9.5px] uppercase tracking-wider text-ink-faint">
            <WorkspaceTableRow>
              <WorkspaceTableHead className="sticky left-0 z-[5] w-8 bg-surface-raised px-2 py-1.5">
                <Checkbox
                  label=""
                  checked={selectedIds.size === points.length && points.length > 0}
                  onCheckedChange={toggleSelectAll}
                  aria-label="Select all optimizer runs"
                  className="justify-center"
                />
              </WorkspaceTableHead>
              <WorkspaceTableHead className="sticky left-8 z-[5] cursor-pointer bg-surface-raised px-2 py-1.5 hover:text-ink" onClick={() => handleSort("score")}>
                Rank {sortKey === "score" ? (sortAsc ? "▲" : "▼") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5">Parameters</WorkspaceTableHead>
              <WorkspaceTableHead className="cursor-pointer px-2 py-1.5 hover:text-ink" onClick={() => handleSort("sharpe_ratio")}>
                Sharpe {sortKey === "sharpe_ratio" ? (sortAsc ? "▲" : "▼") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="cursor-pointer px-2 py-1.5 hover:text-ink" onClick={() => handleSort("total_return")}>
                Return {sortKey === "total_return" ? (sortAsc ? "▲" : "▼") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="cursor-pointer px-2 py-1.5 hover:text-ink" onClick={() => handleSort("max_drawdown")}>
                Drawdown {sortKey === "max_drawdown" ? (sortAsc ? "▲" : "▼") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="cursor-pointer px-2 py-1.5 hover:text-ink" onClick={() => handleSort("stability_score")}>
                Stability {sortKey === "stability_score" ? (sortAsc ? "▲" : "▼") : ""}
              </WorkspaceTableHead>
              <WorkspaceTableHead className="px-2 py-1.5">Constraints</WorkspaceTableHead>
            </WorkspaceTableRow>
          </WorkspaceTableHeader>
          <WorkspaceTableBody className="divide-y divide-border/60">
            {sortedPoints.map((pt, idx) => {
              const isSelected = pt.run_id === selectedRunId;
              const isChecked = selectedIds.has(pt.run_id);
              const passes = pt.passes_constraints ?? true;

              return (
                <WorkspaceTableRow
                  key={pt.run_id}
                  onClick={() => onSelectRunId?.(pt.run_id)}
                  className={`cursor-pointer transition-colors hover:bg-surface-sunk ${
                    isSelected ? "bg-accent/15 font-semibold" : ""
                  } ${!passes ? "opacity-50" : ""}`}
                >
                  <WorkspaceTableCell className="sticky left-0 z-[1] bg-surface px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      label=""
                      checked={isChecked}
                      onCheckedChange={() => toggleSelectOne(pt.run_id)}
                      aria-label={`Select ${pt.run_id}`}
                      className="justify-center"
                    />
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="sticky left-8 z-[1] bg-surface px-2 py-1.5 font-mono text-ink-muted">
                    #{idx + 1}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1.5 font-mono text-[10.5px]">
                    {Object.entries(pt.parameters)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1.5 font-bold text-emerald-400">
                    {pt.sharpe_ratio != null ? pt.sharpe_ratio.toFixed(2) : "—"}
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className={`px-2 py-1.5 ${pt.total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {(pt.total_return * 100).toFixed(1)}%
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1.5 text-rose-400">
                    {(pt.max_drawdown * 100).toFixed(1)}%
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[9.5px] font-bold ${
                      (pt.stability_score ?? 1.0) >= 0.7 ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                    }`}>
                      {((pt.stability_score ?? 1.0) * 100).toFixed(0)}%
                    </span>
                  </WorkspaceTableCell>
                  <WorkspaceTableCell className="px-2 py-1.5">
                    {passes ? (
                      <span className="text-emerald-400 font-bold text-[10px]">✓ PASS</span>
                    ) : (
                      <span className="text-rose-400 text-[10px]">✗ VIOLATES</span>
                    )}
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
