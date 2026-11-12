import { useMemo, useState } from "react";
import type { OptimizerHeatmapData, OptimizerRunPoint } from "../types";
import { OptimizerHeatmapChart } from "./OptimizerHeatmapChart";
import { OptimizerParetoChart } from "./OptimizerParetoChart";

export function OptimizerScatterChart({
  heatmap,
  allPoints,
  paretoFrontier,
  selectedRunId,
  onSelectRunId,
  strategyType = "euler",
}: {
  heatmap: OptimizerHeatmapData;
  allPoints: OptimizerRunPoint[];
  paretoFrontier: OptimizerRunPoint[];
  selectedRunId?: string | null;
  onSelectRunId?: (runId: string) => void;
  strategyType?: string;
}) {
  const [viewMode, setViewMode] = useState<"scatter" | "pareto" | "sensitivity" | "heatmap">(
    strategyType === "grid" ? "scatter" : "scatter"
  );
  const [metricKey, setMetricKey] = useState<"sharpe_ratio" | "total_return" | "max_drawdown" | "stability_score">(
    "sharpe_ratio"
  );

  const { param_x_name, param_y_name } = heatmap;

  // Compute min/max for scaling scatter plot
  const bounds = useMemo(() => {
    if (!allPoints.length) return { minX: 0, maxX: 1, minY: 0, maxY: 1, minVal: 0, maxVal: 1 };

    const xs = allPoints.map((p) => Number(p.parameters[param_x_name] ?? 0));
    const ys = param_y_name ? allPoints.map((p) => Number(p.parameters[param_y_name] ?? 0)) : [0];
    const vals = allPoints.map((p) => p[metricKey] ?? 0);

    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const minVal = Math.min(...vals);
    const maxVal = Math.max(...vals);

    return {
      minX: minX === maxX ? minX - 0.01 : minX,
      maxX: minX === maxX ? maxX + 0.01 : maxX,
      minY: minY === maxY ? minY - 0.01 : minY,
      maxY: minY === maxY ? maxY + 0.01 : maxY,
      minVal: minVal === maxVal ? minVal - 0.1 : minVal,
      maxVal: minVal === maxVal ? maxVal + 0.1 : maxVal,
    };
  }, [allPoints, param_x_name, param_y_name, metricKey]);

  // Color helper based on metric value
  function getColor(val: number, min: number, max: number): string {
    if (metricKey === "max_drawdown") {
      // For drawdown, less negative is better (green), more negative is worse (red)
      const norm = max === min ? 0.5 : (val - min) / (max - min);
      if (norm > 0.6) return "#10b981"; // Emerald
      if (norm > 0.3) return "#f59e0b"; // Amber
      return "#ef4444"; // Rose
    }
    const norm = max === min ? 0.5 : (val - min) / (max - min);
    if (norm > 0.7) return "#10b981";
    if (norm > 0.4) return "#3b82f6";
    if (norm > 0.2) return "#f59e0b";
    return "#ef4444";
  }

  // 1D Sensitivity Curve data (marginal slice of Param X)
  const sensitivityCurve = useMemo(() => {
    const map = new Map<number, { count: number; sum: number; sharpes: number[] }>();
    for (const p of allPoints) {
      const x = Number(p.parameters[param_x_name] ?? 0);
      const entry = map.get(x) ?? { count: 0, sum: 0, sharpes: [] };
      entry.count += 1;
      entry.sum += p.sharpe_ratio ?? 0;
      entry.sharpes.push(p.sharpe_ratio ?? 0);
      map.set(x, entry);
    }
    return Array.from(map.entries())
      .map(([x, data]) => ({
        x,
        avgSharpe: data.sum / data.count,
        minSharpe: Math.min(...data.sharpes),
        maxSharpe: Math.max(...data.sharpes),
      }))
      .sort((a, b) => a.x - b.x);
  }, [allPoints, param_x_name]);

  return (
    <div className="flex h-full flex-col rounded-lg border border-line bg-surface p-3.5 shadow-sm">
      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[12px] font-bold text-ink">Parameter Response Surface</span>
          <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-accent">
            {strategyType.toUpperCase()}
          </span>
        </div>

        {/* View Mode Pills */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setViewMode("scatter")}
            className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
              viewMode === "scatter"
                ? "bg-accent text-accent-ink"
                : "bg-surface-raised text-ink-muted hover:text-ink border border-line"
            }`}
          >
            ● 2D Parameter Space
          </button>
          <button
            type="button"
            onClick={() => setViewMode("sensitivity")}
            className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
              viewMode === "sensitivity"
                ? "bg-accent text-accent-ink"
                : "bg-surface-raised text-ink-muted hover:text-ink border border-line"
            }`}
          >
            📈 1D Sensitivity Slice
          </button>
          <button
            type="button"
            onClick={() => setViewMode("pareto")}
            className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
              viewMode === "pareto"
                ? "bg-accent text-accent-ink"
                : "bg-surface-raised text-ink-muted hover:text-ink border border-line"
            }`}
          >
            🎯 Pareto Frontier
          </button>
          {strategyType === "grid" && (
            <button
              type="button"
              onClick={() => setViewMode("heatmap")}
              className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                viewMode === "heatmap"
                  ? "bg-accent text-accent-ink"
                  : "bg-surface-raised text-ink-muted hover:text-ink border border-line"
              }`}
            >
              ▦ Matrix Heatmap
            </button>
          )}
        </div>
      </div>

      {/* Main Visualization Body */}
      <div className="mt-3 min-h-0 flex-1">
        {viewMode === "heatmap" ? (
          <OptimizerHeatmapChart
            heatmap={heatmap}
            selectedRunId={selectedRunId}
            onSelectRunId={onSelectRunId}
          />
        ) : viewMode === "pareto" ? (
          <OptimizerParetoChart
            allPoints={allPoints}
            paretoFrontier={paretoFrontier}
            selectedRunId={selectedRunId}
            onSelectRunId={onSelectRunId}
          />
        ) : viewMode === "sensitivity" ? (
          <div className="flex h-full flex-col">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] text-ink-muted">
                Parameter Stability & Marginal Sensitivity on <span className="font-bold text-ink">{param_x_name}</span> (Plateau vs Fragile Needle):
              </span>
            </div>
            <div className="relative flex-1 rounded border border-line bg-surface-sunk p-2 overflow-hidden">
              <svg viewBox="0 0 500 240" className="h-full w-full">
                {/* Horizontal Grid & Zero lines */}
                <line x1="45" y1="120" x2="475" y2="120" stroke="var(--line)" strokeDasharray="3,3" />
                <line x1="45" y1="205" x2="475" y2="205" stroke="var(--line)" />
                <line x1="45" y1="25" x2="45" y2="205" stroke="var(--line)" />

                {/* Sensitivity Polyline & Confidence Area */}
                {sensitivityCurve.length > 1 && (() => {
                  const sharpeVals = sensitivityCurve.flatMap(c => [c.minSharpe, c.maxSharpe, c.avgSharpe]);
                  const minS = Math.min(...sharpeVals, 0);
                  const maxS = Math.max(...sharpeVals, 2.5);
                  const sRange = maxS === minS ? 1 : maxS - minS;

                  const getY = (s: number) => 205 - ((s - minS) / sRange) * 170;
                  const getX = (idx: number) => 55 + (idx / (sensitivityCurve.length - 1)) * 405;

                  const areaPoints = [
                    ...sensitivityCurve.map((pt, idx) => `${getX(idx)},${getY(pt.maxSharpe)}`),
                    ...sensitivityCurve.slice().reverse().map((pt, idx) => `${getX(sensitivityCurve.length - 1 - idx)},${getY(pt.minSharpe)}`),
                  ].join(" ");

                  const linePoints = sensitivityCurve.map((pt, idx) => `${getX(idx)},${getY(pt.avgSharpe)}`).join(" ");

                  return (
                    <>
                      <polygon points={areaPoints} fill="var(--accent)" fillOpacity="0.15" />
                      <polyline points={linePoints} fill="none" stroke="var(--accent)" strokeWidth="2.5" />
                      {sensitivityCurve.map((pt, idx) => {
                        const cx = getX(idx);
                        const cy = getY(pt.avgSharpe);
                        return (
                          <g key={pt.x}>
                            <circle cx={cx} cy={cy} r="4.5" fill="var(--accent)" stroke="#fff" strokeWidth="1.5" />
                            <text
                              x={cx}
                              y="222"
                              textAnchor="middle"
                              className="text-[10px] fill-ink-muted font-mono"
                            >
                              {pt.x}
                            </text>
                            <text
                              x={cx}
                              y={cy - 8}
                              textAnchor="middle"
                              className="text-[10px] fill-ink font-bold"
                            >
                              {pt.avgSharpe.toFixed(2)}
                            </text>
                          </g>
                        );
                      })}
                    </>
                  );
                })()}
              </svg>
            </div>
          </div>
        ) : (
          /* 2D Parameter Space Scatter Plot */
          <div className="flex h-full flex-col">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[11px]">
              <span className="text-ink-muted">
                Color metric:
                <select
                  value={metricKey}
                  onChange={(e) => setMetricKey(e.target.value as any)}
                  className="ml-1.5 rounded border border-line bg-surface px-2 py-0.5 text-xs text-ink"
                >
                  <option value="sharpe_ratio">Sharpe Ratio</option>
                  <option value="total_return">Total Return</option>
                  <option value="max_drawdown">Max Drawdown</option>
                  <option value="stability_score">Stability Index</option>
                </select>
              </span>
              <span className="font-mono text-[10px] text-ink-faint">
                {allPoints.length} evaluated variants
              </span>
            </div>

            <div className="relative flex-1 rounded border border-line bg-surface-sunk p-2 overflow-hidden">
              {/* Y Axis Label */}
              <div className="absolute left-1.5 top-1/2 -translate-y-1/2 -rotate-90 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
                {param_y_name || "Constant"}
              </div>

              {/* X Axis Label */}
              <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
                {param_x_name}
              </div>

              {/* Scatter SVG Canvas with safe ViewBox */}
              <svg viewBox="0 0 500 240" className="h-full w-full">
                {/* Axis lines */}
                <line x1="45" y1="205" x2="475" y2="205" stroke="var(--line)" />
                <line x1="45" y1="20" x2="45" y2="205" stroke="var(--line)" />

                {allPoints.map((pt) => {
                  const px = Number(pt.parameters[param_x_name] ?? bounds.minX);
                  const py = param_y_name ? Number(pt.parameters[param_y_name] ?? bounds.minY) : bounds.minY;

                  const xNorm = bounds.maxX === bounds.minX ? 0.5 : (px - bounds.minX) / (bounds.maxX - bounds.minX);
                  const yNorm = bounds.maxY === bounds.minY ? 0.5 : (py - bounds.minY) / (bounds.maxY - bounds.minY);

                  const cx = 55 + xNorm * 410;
                  const cy = 200 - yNorm * 170;

                  const val = pt[metricKey] ?? 0;
                  const color = getColor(val, bounds.minVal, bounds.maxVal);
                  const isSelected = pt.run_id === selectedRunId;
                  const passesConstraints = pt.passes_constraints ?? true;
                  const isPareto = paretoFrontier.some((pf) => pf.run_id === pt.run_id);

                  return (
                    <g
                      key={pt.run_id}
                      className="cursor-pointer transition-transform hover:scale-125"
                      onClick={() => onSelectRunId?.(pt.run_id)}
                    >
                      {/* Generation Ring for Euler */}
                      {pt.euler_generation && pt.euler_generation > 1 && (
                        <circle
                          cx={cx}
                          cy={cy}
                          r="10"
                          fill="none"
                          stroke={color}
                          strokeWidth="1.2"
                          strokeDasharray="2,2"
                          opacity="0.6"
                        />
                      )}

                      {/* Pareto Star Indicator */}
                      {isPareto && (
                        <polygon
                          points={`${cx},${cy - 10} ${cx + 2.5},${cy - 6.5} ${cx + 7},${cy - 6.5} ${cx + 3.5},${cy - 3} ${cx + 5},${cy + 1} ${cx},${cy - 1.5} ${cx - 5},${cy + 1} ${cx - 3.5},${cy - 3} ${cx - 7},${cy - 6.5} ${cx - 2.5},${cy - 6.5}`}
                          fill="#f59e0b"
                        />
                      )}

                      {/* Core Scatter Dot */}
                      <circle
                        cx={cx}
                        cy={cy}
                        r={isSelected ? "7.5" : "5.5"}
                        fill={passesConstraints ? color : "#6b7280"}
                        opacity={passesConstraints ? "0.9" : "0.35"}
                        stroke={isSelected ? "#fff" : passesConstraints ? "var(--line)" : "#374151"}
                        strokeWidth={isSelected ? "2.5" : "1"}
                      />

                      {/* Tooltip on hover title */}
                      <title>{`Run: ${pt.run_id}\n${param_x_name}: ${px}\n${param_y_name ? `${param_y_name}: ${py}\n` : ""}Sharpe: ${pt.sharpe_ratio.toFixed(2)}\nReturn: ${(pt.total_return * 100).toFixed(1)}%\nDrawdown: ${(pt.max_drawdown * 100).toFixed(1)}%\nStability: ${(pt.stability_score ?? 1).toFixed(2)}\nConstraints: ${passesConstraints ? "PASS" : "FAIL"}`}</title>
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
