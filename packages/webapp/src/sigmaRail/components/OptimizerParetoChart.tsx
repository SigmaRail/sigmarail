import { useMemo } from "react";
import type { OptimizerRunPoint } from "../types";

export function OptimizerParetoChart({
  allPoints,
  paretoFrontier,
  selectedRunId,
  onSelectRunId,
}: {
  allPoints: OptimizerRunPoint[];
  paretoFrontier: OptimizerRunPoint[];
  selectedRunId?: string | null;
  onSelectRunId?: (runId: string) => void;
}) {
  const paretoIds = useMemo(
    () => new Set(paretoFrontier.map((p) => p.run_id)),
    [paretoFrontier],
  );

  // SVG Chart bounds
  const width = 500;
  const height = 280;
  const padding = { top: 20, right: 30, bottom: 40, left: 50 };

  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  // Find min/max for scale
  const { minReturn, maxReturn, minDD, maxDD } = useMemo(() => {
    if (allPoints.length === 0) {
      return { minReturn: 0, maxReturn: 0.3, minDD: 0, maxDD: 0.2 };
    }
    const returns = allPoints.map((p) => p.total_return);
    const dds = allPoints.map((p) => p.max_drawdown);
    return {
      minReturn: Math.min(0, ...returns),
      maxReturn: Math.max(0.1, ...returns) * 1.1,
      minDD: 0,
      maxDD: Math.max(0.05, ...dds) * 1.15,
    };
  }, [allPoints]);

  const scaleX = (dd: number) =>
    padding.left + ((dd - minDD) / (maxDD - minDD || 1)) * plotWidth;

  const scaleY = (ret: number) =>
    padding.top +
    plotHeight -
    ((ret - minReturn) / (maxReturn - minReturn || 1)) * plotHeight;

  // Build SVG path for Pareto Frontier line
  const paretoPath = useMemo(() => {
    if (paretoFrontier.length < 2) return "";
    const sorted = [...paretoFrontier].sort((a, b) => a.max_drawdown - b.max_drawdown);
    return sorted
      .map(
        (p, idx) =>
          `${idx === 0 ? "M" : "L"} ${scaleX(p.max_drawdown)} ${scaleY(p.total_return)}`,
      )
      .join(" ");
  }, [paretoFrontier, minDD, maxDD, minReturn, maxReturn, plotWidth, plotHeight]);

  return (
    <div className="rounded border border-line bg-surface p-4">
      <div className="flex items-center justify-between border-b border-line pb-3">
        <div>
          <h3 className="text-[13px] font-semibold text-ink">
            Pareto Frontier (Risk vs Return)
          </h3>
          <p className="text-[11px] text-ink-muted">
            Total Return % vs Max Drawdown % across parameter combinations
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10.5px]">
          <span className="flex items-center gap-1 text-accent font-semibold">
            <span className="inline-block h-2 w-2 rounded-full bg-accent" />
            Pareto Optimal
          </span>
          <span className="flex items-center gap-1 text-ink-muted">
            <span className="inline-block h-2 w-2 rounded-full bg-ink-faint" />
            Dominated
          </span>
        </div>
      </div>

      <div className="mt-3 relative flex-1 min-h-[220px]">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
          {/* Grid lines */}
          <line
            x1={padding.left}
            y1={padding.top + plotHeight}
            x2={width - padding.right}
            y2={padding.top + plotHeight}
            stroke="var(--color-line, #333)"
            strokeWidth="1"
          />
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={padding.top + plotHeight}
            stroke="var(--color-line, #333)"
            strokeWidth="1"
          />

          {/* Zero Return Line if visible */}
          {minReturn < 0 && (
            <line
              x1={padding.left}
              y1={scaleY(0)}
              x2={width - padding.right}
              y2={scaleY(0)}
              stroke="var(--color-line, #444)"
              strokeDasharray="2,2"
            />
          )}

          {/* Pareto Frontier Line */}
          {paretoPath && (
            <path
              d={paretoPath}
              fill="none"
              stroke="rgb(59, 130, 246)"
              strokeWidth="2"
              strokeDasharray="4,3"
            />
          )}

          {/* Scatter points */}
          {allPoints.map((pt) => {
            const isPareto = paretoIds.has(pt.run_id);
            const isSelected = pt.run_id === selectedRunId;
            const cx = scaleX(pt.max_drawdown);
            const cy = scaleY(pt.total_return);

            return (
              <g
                key={pt.run_id}
                className="cursor-pointer transition-transform hover:scale-125"
                onClick={() => onSelectRunId?.(pt.run_id)}
              >
                <circle
                  cx={cx}
                  cy={cy}
                  r={isSelected ? 6 : isPareto ? 4.5 : 3.5}
                  className={`${
                    isSelected
                      ? "fill-accent stroke-white stroke-2"
                      : isPareto
                        ? "fill-accent stroke-accent/40 stroke-1"
                        : "fill-ink-faint hover:fill-ink"
                  }`}
                />
                <title>{`Return: ${(pt.total_return * 100).toFixed(1)}%\nMax DD: ${(
                  pt.max_drawdown * 100
                ).toFixed(1)}%\nSharpe: ${pt.sharpe_ratio.toFixed(2)}\nRun: ${pt.run_id}`}</title>
              </g>
            );
          })}

          {/* Axis Labels */}
          <text
            x={padding.left + plotWidth / 2}
            y={height - 8}
            textAnchor="middle"
            className="fill-ink-muted text-[10px] font-mono"
          >
            Max Drawdown % →
          </text>
          <text
            x={15}
            y={padding.top + plotHeight / 2}
            textAnchor="middle"
            transform={`rotate(-90 15 ${padding.top + plotHeight / 2})`}
            className="fill-ink-muted text-[10px] font-mono"
          >
            Total Return % →
          </text>

          {/* Axis ticks */}
          <text
            x={padding.left}
            y={padding.top + plotHeight + 14}
            textAnchor="middle"
            className="fill-ink-faint text-[9px] font-mono"
          >
            {(minDD * 100).toFixed(0)}%
          </text>
          <text
            x={width - padding.right}
            y={padding.top + plotHeight + 14}
            textAnchor="middle"
            className="fill-ink-faint text-[9px] font-mono"
          >
            {(maxDD * 100).toFixed(1)}%
          </text>
          <text
            x={padding.left - 6}
            y={padding.top + 5}
            textAnchor="end"
            className="fill-ink-faint text-[9px] font-mono"
          >
            {(maxReturn * 100).toFixed(1)}%
          </text>
        </svg>
      </div>
    </div>
  );
}
