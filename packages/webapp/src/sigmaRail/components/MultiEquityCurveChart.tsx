import { useMemo } from "react";
import type { MultiRunCompareRunItem } from "../types";

const RUN_COLORS = [
  { stroke: "#38bdf8", bg: "bg-sky-400", text: "text-sky-400", hex: "#38bdf8" }, // Sky
  { stroke: "#34d399", bg: "bg-emerald-400", text: "text-emerald-400", hex: "#34d399" }, // Emerald
  { stroke: "#fbbf24", bg: "bg-amber-400", text: "text-amber-400", hex: "#fbbf24" }, // Amber
  { stroke: "#c084fc", bg: "bg-purple-400", text: "text-purple-400", hex: "#c084fc" }, // Purple
  { stroke: "#f87171", bg: "bg-rose-400", text: "text-rose-400", hex: "#f87171" }, // Rose
  { stroke: "#94a3b8", bg: "bg-slate-400", text: "text-slate-400", hex: "#94a3b8" }, // Slate
];

const W = 680;
const H = 240;
const PAD = { top: 20, right: 30, bottom: 36, left: 52 };

function truncateId(id: string, head = 6, tail = 4): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

export function MultiEquityCurveChart({
  runs,
  title = "Multi-Run Normalized Equity Overlay (Base 100)",
}: {
  runs: MultiRunCompareRunItem[];
  title?: string;
}) {
  const seriesData = useMemo(() => {
    if (!runs || runs.length === 0) return null;

    // Determine global min and max timestamp across all runs
    let minT = Infinity;
    let maxT = -Infinity;
    let minVal = Infinity;
    let maxVal = -Infinity;

    runs.forEach((r) => {
      r.points.forEach((p) => {
        if (p.t < minT) minT = p.t;
        if (p.t > maxT) maxT = p.t;
        if (p.normalized < minVal) minVal = p.normalized;
        if (p.normalized > maxVal) maxVal = p.normalized;
      });
    });

    if (minT === Infinity || maxT === -Infinity || minT === maxT) {
      return null;
    }

    // Pad Y-axis bounds slightly
    const ySpan = maxVal - minVal || 1;
    const yMin = Math.max(0, Math.floor(minVal - ySpan * 0.05));
    const yMax = Math.ceil(maxVal + ySpan * 0.05);

    const innerW = W - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;

    const toX = (t: number) => PAD.left + ((t - minT) / (maxT - minT)) * innerW;
    const toY = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH;

    const paths = runs.map((r, i) => {
      const color = RUN_COLORS[i % RUN_COLORS.length];
      if (!r.points || r.points.length === 0) return { run: r, color, d: "" };

      const d = r.points.reduce((acc, p, idx) => {
        const x = toX(p.t);
        const y = toY(p.normalized);
        return idx === 0 ? `M ${x.toFixed(1)} ${y.toFixed(1)}` : `${acc} L ${x.toFixed(1)} ${y.toFixed(1)}`;
      }, "");

      return { run: r, color, d };
    });

    const startDate = new Date(minT > 1e12 ? minT : minT * 1000).toISOString().slice(0, 10);
    const endDate = new Date(maxT > 1e12 ? maxT : maxT * 1000).toISOString().slice(0, 10);

    return {
      minT,
      maxT,
      yMin,
      yMax,
      startDate,
      endDate,
      toX,
      toY,
      paths,
      innerW,
      innerH,
    };
  }, [runs]);

  if (!seriesData) {
    return (
      <div className="flex h-56 items-center justify-center rounded border border-line bg-surface text-[12px] text-ink-muted">
        No equity curve data available for compared runs.
      </div>
    );
  }

  const base100Y = seriesData.toY(100.0);

  return (
    <div className="rounded border border-line bg-surface p-3.5">
      {/* Title & Legend Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-ink">
          {title}
        </h4>
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          {seriesData.paths.map((p) => (
            <div key={p.run.run_id} className="flex items-center gap-1.5 font-mono">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: p.color.hex }}
              />
              <span className="font-semibold text-ink">
                {truncateId(p.run.run_id)}
              </span>
              {p.run.metrics.total_return != null ? (
                <span className={p.run.metrics.total_return >= 0 ? "text-emerald-400" : "text-rose-400"}>
                  ({(p.run.metrics.total_return * 100).toFixed(2)}%)
                </span>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-60 w-full rounded border border-line bg-surface-sunk"
        >
          {/* Baseline 100.0 Line */}
          {base100Y >= PAD.top && base100Y <= H - PAD.bottom ? (
            <>
              <line
                x1={PAD.left}
                y1={base100Y}
                x2={W - PAD.right}
                y2={base100Y}
                stroke="currentColor"
                strokeDasharray="4 3"
                className="text-line-soft"
                strokeWidth="1"
              />
              <text
                x={PAD.left - 6}
                y={base100Y + 3}
                textAnchor="end"
                className="fill-ink-faint font-mono text-[9px]"
              >
                100.0 (0%)
              </text>
            </>
          ) : null}

          {/* Top & Bottom Y-axis Labels */}
          <text
            x={PAD.left - 6}
            y={PAD.top + 4}
            textAnchor="end"
            className="fill-ink-faint font-mono text-[9px]"
          >
            {seriesData.yMax.toFixed(0)} ({seriesData.yMax > 100 ? `+${(seriesData.yMax - 100).toFixed(0)}%` : `${(seriesData.yMax - 100).toFixed(0)}%`})
          </text>
          <text
            x={PAD.left - 6}
            y={H - PAD.bottom}
            textAnchor="end"
            className="fill-ink-faint font-mono text-[9px]"
          >
            {seriesData.yMin.toFixed(0)} ({seriesData.yMin > 100 ? `+${(seriesData.yMin - 100).toFixed(0)}%` : `${(seriesData.yMin - 100).toFixed(0)}%`})
          </text>

          {/* X-axis Date Labels */}
          <text
            x={PAD.left}
            y={H - 12}
            className="fill-ink-faint font-mono text-[9px]"
          >
            {seriesData.startDate}
          </text>
          <text
            x={W - PAD.right}
            y={H - 12}
            textAnchor="end"
            className="fill-ink-faint font-mono text-[9px]"
          >
            {seriesData.endDate}
          </text>

          {/* Render Curve Paths */}
          {seriesData.paths.map((p) => (
            <path
              key={p.run.run_id}
              d={p.d}
              fill="none"
              stroke={p.color.hex}
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </svg>
      </div>
    </div>
  );
}
