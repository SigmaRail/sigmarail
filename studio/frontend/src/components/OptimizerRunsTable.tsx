import { useState } from "react";
import type { OptimizerRunPoint } from "../types";

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
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-ink-muted">
            <input
              type="checkbox"
              checked={filterConstraintsOnly}
              onChange={(e) => setFilterConstraintsOnly(e.target.checked)}
              className="rounded border-line"
            />
            Passes Constraints Only
          </label>

          {selectedIds.size > 1 && onCompareRuns && (
            <button
              type="button"
              onClick={() => onCompareRuns(Array.from(selectedIds))}
              className="rounded bg-accent px-2.5 py-1 text-[11px] font-semibold text-accent-ink hover:opacity-90 transition-opacity"
            >
              Compare Selected ({selectedIds.size}) 🔍
            </button>
          )}
        </div>
      </div>

      {/* Table Body */}
      <div className="max-h-72 overflow-auto mt-2">
        <table className="w-full text-left text-[11px] min-w-[640px]">
          <thead className="sticky top-0 bg-surface-raised text-ink-faint border-b border-line text-[9.5px] uppercase tracking-wider z-[4]">
            <tr>
              <th className="w-8 px-2 py-1.5 sticky left-0 bg-surface-raised z-[5]">
                <input
                  type="checkbox"
                  checked={selectedIds.size === points.length && points.length > 0}
                  onChange={toggleSelectAll}
                  className="rounded border-line"
                />
              </th>
              <th className="px-2 py-1.5 cursor-pointer hover:text-ink sticky left-8 bg-surface-raised z-[5]" onClick={() => handleSort("score")}>
                Rank {sortKey === "score" ? (sortAsc ? "▲" : "▼") : ""}
              </th>
              <th className="px-2 py-1.5">Parameters</th>
              <th className="px-2 py-1.5 cursor-pointer hover:text-ink" onClick={() => handleSort("sharpe_ratio")}>
                Sharpe {sortKey === "sharpe_ratio" ? (sortAsc ? "▲" : "▼") : ""}
              </th>
              <th className="px-2 py-1.5 cursor-pointer hover:text-ink" onClick={() => handleSort("total_return")}>
                Return {sortKey === "total_return" ? (sortAsc ? "▲" : "▼") : ""}
              </th>
              <th className="px-2 py-1.5 cursor-pointer hover:text-ink" onClick={() => handleSort("max_drawdown")}>
                Drawdown {sortKey === "max_drawdown" ? (sortAsc ? "▲" : "▼") : ""}
              </th>
              <th className="px-2 py-1.5 cursor-pointer hover:text-ink" onClick={() => handleSort("stability_score")}>
                Stability {sortKey === "stability_score" ? (sortAsc ? "▲" : "▼") : ""}
              </th>
              <th className="px-2 py-1.5">Constraints</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {sortedPoints.map((pt, idx) => {
              const isSelected = pt.run_id === selectedRunId;
              const isChecked = selectedIds.has(pt.run_id);
              const passes = pt.passes_constraints ?? true;

              return (
                <tr
                  key={pt.run_id}
                  onClick={() => onSelectRunId?.(pt.run_id)}
                  className={`cursor-pointer transition-colors hover:bg-surface-sunk ${
                    isSelected ? "bg-accent/15 font-semibold" : ""
                  } ${!passes ? "opacity-50" : ""}`}
                >
                  <td className="px-2 py-1.5 sticky left-0 bg-surface z-[1]" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleSelectOne(pt.run_id)}
                      className="rounded border-line"
                    />
                  </td>
                  <td className="px-2 py-1.5 font-mono text-ink-muted sticky left-8 bg-surface z-[1]">
                    #{idx + 1}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-[10.5px]">
                    {Object.entries(pt.parameters)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}
                  </td>
                  <td className="px-2 py-1.5 font-bold text-emerald-400">
                    {pt.sharpe_ratio != null ? pt.sharpe_ratio.toFixed(2) : "—"}
                  </td>
                  <td className={`px-2 py-1.5 ${pt.total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {(pt.total_return * 100).toFixed(1)}%
                  </td>
                  <td className="px-2 py-1.5 text-rose-400">
                    {(pt.max_drawdown * 100).toFixed(1)}%
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[9.5px] font-bold ${
                      (pt.stability_score ?? 1.0) >= 0.7 ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                    }`}>
                      {((pt.stability_score ?? 1.0) * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    {passes ? (
                      <span className="text-emerald-400 font-bold text-[10px]">✓ PASS</span>
                    ) : (
                      <span className="text-rose-400 text-[10px]">✗ VIOLATES</span>
                    )}
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
