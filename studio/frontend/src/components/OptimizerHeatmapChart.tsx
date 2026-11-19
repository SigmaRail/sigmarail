import { useState } from "react";
import type { OptimizerHeatmapData } from "../types";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

export type MetricChoice = "sharpe" | "return" | "drawdown";

function getCellColor(metric: MetricChoice, val: number | null | undefined): string {
  if (val == null) return "bg-surface-raised border-line text-ink-faint";

  if (metric === "sharpe") {
    if (val >= 2.5) return "bg-emerald-500/80 text-white font-bold border-emerald-400";
    if (val >= 1.8) return "bg-emerald-600/60 text-emerald-100 font-semibold border-emerald-500/50";
    if (val >= 1.2) return "bg-emerald-700/40 text-emerald-200 border-emerald-600/40";
    if (val >= 0.5) return "bg-emerald-900/30 text-emerald-300 border-emerald-800/30";
    if (val >= 0) return "bg-surface-raised text-ink-muted border-line";
    return "bg-rose-950/40 text-rose-300 border-rose-800/40";
  }

  if (metric === "return") {
    if (val >= 0.3) return "bg-emerald-500/80 text-white font-bold border-emerald-400";
    if (val >= 0.15) return "bg-emerald-600/60 text-emerald-100 font-semibold border-emerald-500/50";
    if (val >= 0.05) return "bg-emerald-700/40 text-emerald-200 border-emerald-600/40";
    if (val >= 0) return "bg-surface-raised text-ink-muted border-line";
    return "bg-rose-900/50 text-rose-200 border-rose-700/50";
  }

  // Drawdown (lower is better)
  if (val <= 0.04) return "bg-emerald-600/60 text-emerald-100 font-semibold border-emerald-500/50";
  if (val <= 0.08) return "bg-emerald-800/40 text-emerald-200 border-emerald-700/30";
  if (val <= 0.15) return "bg-amber-900/40 text-amber-200 border-amber-700/40";
  return "bg-rose-900/60 text-rose-200 font-bold border-rose-700/60";
}

function formatVal(metric: MetricChoice, val: number | null | undefined): string {
  if (val == null) return "—";
  if (metric === "sharpe") return val.toFixed(2);
  return `${(val * 100).toFixed(1)}%`;
}

export function OptimizerHeatmapChart({
  heatmap,
  selectedRunId,
  onSelectRunId,
}: {
  heatmap: OptimizerHeatmapData;
  selectedRunId?: string | null;
  onSelectRunId?: (runId: string) => void;
}) {
  const [activeMetric, setActiveMetric] = useState<MetricChoice>("sharpe");

  const { param_x_name, param_x_values, param_y_name, param_y_values } = heatmap;
  const yValues = param_y_name && param_y_values.length > 0 ? param_y_values : [0];

  const currentMatrix =
    activeMetric === "sharpe"
      ? heatmap.sharpe_matrix
      : activeMetric === "return"
        ? heatmap.return_matrix
        : heatmap.drawdown_matrix;

  return (
    <div className="rounded border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <h3 className="text-[13px] font-semibold text-ink">
            2D Hyperparameter Response Heatmap
          </h3>
          <p className="text-[11px] text-ink-muted">
            {param_x_name} (X-axis) vs {param_y_name || "Univariate"} (Y-axis)
          </p>
        </div>

        {/* Metric Selector Pills */}
        <Tabs value={activeMetric} onValueChange={(value) => setActiveMetric(value as MetricChoice)}>
          <TabsList className="h-9 gap-1">
          <TabsTrigger value="sharpe" className="px-2.5 text-[11px]">
            Sharpe Ratio
          </TabsTrigger>
          <TabsTrigger value="return" className="px-2.5 text-[11px]">
            Total Return
          </TabsTrigger>
          <TabsTrigger value="drawdown" className="px-2.5 text-[11px]">
            Max Drawdown
          </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Grid Matrix */}
      <div className="mt-4 overflow-x-auto">
        <WorkspaceTable className="w-full border-collapse text-center">
          <WorkspaceTableHeader>
            <WorkspaceTableRow>
              <WorkspaceTableHead className="h-auto p-2 text-left font-mono text-[11px] font-semibold uppercase text-ink-faint">
                {param_y_name || "Y"} ↓ \ {param_x_name} →
              </WorkspaceTableHead>
              {param_x_values.map((x) => (
                <WorkspaceTableHead key={x} className="h-auto p-2 font-mono text-[11.5px] font-bold text-ink">
                  {x}
                </WorkspaceTableHead>
              ))}
            </WorkspaceTableRow>
          </WorkspaceTableHeader>
          <WorkspaceTableBody>
            {yValues.map((y, yIdx) => (
              <WorkspaceTableRow key={y}>
                <WorkspaceTableCell className="p-2 text-left font-mono text-[11.5px] font-bold text-ink bg-surface-raised/40">
                  {param_y_name ? y : "Value"}
                </WorkspaceTableCell>
                {param_x_values.map((x, xIdx) => {
                  const val = currentMatrix[yIdx]?.[xIdx];
                  const runId = heatmap.run_id_matrix[yIdx]?.[xIdx];
                  const isSelected = runId && runId === selectedRunId;

                  return (
                    <WorkspaceTableCell key={x} className="p-1.5">
                      <Button
                        type="button"
                        disabled={!runId}
                        onClick={() => runId && onSelectRunId?.(runId)}
                        variant="outline"
                        className={`h-auto w-full rounded py-3 px-2 text-center transition-all ${getCellColor(
                          activeMetric,
                          val,
                        )} ${
                          isSelected
                            ? "ring-2 ring-accent ring-offset-2 ring-offset-surface scale-105 shadow-md"
                            : "hover:opacity-90 hover:scale-102"
                        } ${!runId ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
                        title={
                          runId
                            ? `${param_x_name}=${x}, ${param_y_name || ""}=${y}\n${activeMetric}: ${formatVal(
                                activeMetric,
                                val,
                              )}\nRun: ${runId}`
                            : "Pending/Running"
                        }
                      >
                        <span className="font-mono text-[12px]">{formatVal(activeMetric, val)}</span>
                      </Button>
                    </WorkspaceTableCell>
                  );
                })}
              </WorkspaceTableRow>
            ))}
          </WorkspaceTableBody>
        </WorkspaceTable>
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center justify-between text-[10.5px] text-ink-muted border-t border-line/60 pt-2.5">
        <div className="flex items-center gap-2">
          <span>Scale:</span>
          <span className="inline-block h-2.5 w-6 rounded bg-rose-900/50" />
          <span>Lower / Risk</span>
          <span className="inline-block h-2.5 w-6 rounded bg-emerald-700/50" />
          <span className="inline-block h-2.5 w-6 rounded bg-emerald-500/80" />
          <span>Optimal / Peak</span>
        </div>
        <span className="font-mono text-[10px] text-ink-faint">
          Click any cell to inspect run & parameter details
        </span>
      </div>
    </div>
  );
}
