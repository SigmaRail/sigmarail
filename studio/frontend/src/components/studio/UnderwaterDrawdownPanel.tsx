import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunDrawdowns } from "../../api/backtests";

export function UnderwaterDrawdownPanel({ runId }: { runId: string }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const query = useQuery({
    queryKey: ["run-drawdowns", runId],
    queryFn: () => fetchRunDrawdowns(runId),
    enabled: Boolean(runId),
  });

  const series = query.data?.series ?? [];
  const episodes = query.data?.episodes ?? [];
  const maxDrawdown = query.data?.max_drawdown ?? 0;
  const currentDrawdown = query.data?.current_drawdown ?? 0;

  const chartData = useMemo(() => {
    if (series.length === 0) return null;

    let minDD = 0;
    for (const p of series) {
      if (p.drawdown_pct < minDD) minDD = p.drawdown_pct;
    }

    const minPct = Math.min(-0.02, minDD * 1.15); // minimum floor for chart visibility
    const maxPct = 0.002;

    const width = 800;
    const height = 180;
    const pad = { top: 15, right: 55, bottom: 25, left: 15 };
    const chartW = width - pad.left - pad.right;
    const chartH = height - pad.top - pad.bottom;

    const scaleX = (idx: number) => pad.left + (idx / (series.length - 1 || 1)) * chartW;
    const scaleY = (val: number) => pad.top + ((0 - val) / (0 - minPct || 1)) * chartH;

    const linePoints = series.map((p, i) => `${scaleX(i)},${scaleY(p.drawdown_pct)}`).join(" ");
    const areaPoints = `${scaleX(0)},${scaleY(0)} ` + linePoints + ` ${scaleX(series.length - 1)},${scaleY(0)}`;

    return {
      width,
      height,
      minPct,
      maxPct,
      pad,
      chartW,
      chartH,
      scaleX,
      scaleY,
      linePoints,
      areaPoints,
    };
  }, [series]);

  const activeIdx = hoverIndex !== null ? hoverIndex : (series.length > 0 ? series.length - 1 : null);
  const activePt = activeIdx !== null ? series[activeIdx] : null;

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface shadow-sm overflow-hidden">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-raised px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-bold text-ink">
            Underwater Drawdown & Recovery Analysis
          </span>
          <span className="rounded bg-rose-500/20 px-2 py-0.5 font-mono text-[10.5px] font-bold text-rose-400">
            Max DD: {(maxDrawdown * 100).toFixed(2)}%
          </span>
          <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10.5px] text-ink-muted">
            Current: {(currentDrawdown * 100).toFixed(2)}%
          </span>
        </div>
      </div>

      {/* Underwater Area Chart */}
      <div className="p-3 border-b border-line">
        {query.isLoading ? (
          <div className="flex h-36 items-center justify-center text-[12px] text-ink-muted">
            Calculating drawdown timeseries…
          </div>
        ) : query.isError ? (
          <div className="flex h-36 items-center justify-center text-[12px] text-danger">
            {(query.error as Error).message}
          </div>
        ) : !chartData || series.length === 0 ? (
          <div className="flex h-36 items-center justify-center text-[12px] text-ink-muted">
            No drawdown data available.
          </div>
        ) : (
          <div className="relative">
            {/* Hover Legend Line */}
            {activePt ? (
              <div className="flex flex-wrap items-center gap-4 pb-1.5 text-[11px] font-mono">
                <span className="font-bold text-ink">{activePt.date}</span>
                <span className="font-bold text-rose-400">
                  Drawdown: {(activePt.drawdown_pct * 100).toFixed(2)}%
                </span>
                <span className="text-ink-muted">
                  Equity: ${activePt.equity.toLocaleString()} (Peak: ${activePt.peak.toLocaleString()})
                </span>
              </div>
            ) : null}

            <svg
              viewBox={`0 0 ${chartData.width} ${chartData.height}`}
              className="w-full h-36 select-none"
              onMouseLeave={() => setHoverIndex(null)}
            >
              <defs>
                <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.10" />
                  <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.45" />
                </linearGradient>
              </defs>

              {/* Grid Lines */}
              {[0, -0.01, -0.02, -0.03, -0.05].map((dd) => {
                if (dd < chartData.minPct) return null;
                const y = chartData.scaleY(dd);
                return (
                  <g key={dd}>
                    <line
                      x1={chartData.pad.left}
                      y1={y}
                      x2={chartData.width - chartData.pad.right}
                      y2={y}
                      stroke="#27272a"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                    />
                    <text
                      x={chartData.width - chartData.pad.right + 6}
                      y={y + 3}
                      fill="#71717a"
                      fontSize="9.5"
                      fontFamily="monospace"
                    >
                      {(dd * 100).toFixed(1)}%
                    </text>
                  </g>
                );
              })}

              {/* Baseline 0% line */}
              <line
                x1={chartData.pad.left}
                y1={chartData.scaleY(0)}
                x2={chartData.width - chartData.pad.right}
                y2={chartData.scaleY(0)}
                stroke="#71717a"
                strokeWidth="1.2"
              />

              {/* Drawdown Area & Polyline */}
              <polygon points={chartData.areaPoints} fill="url(#ddGradient)" />
              <polyline
                points={chartData.linePoints}
                fill="none"
                stroke="#f43f5e"
                strokeWidth="1.8"
                strokeLinecap="round"
              />

              {/* Hover Cursor */}
              {series.map((p, i) => {
                const x = chartData.scaleX(i);
                const colW = chartData.chartW / (series.length || 1);
                return (
                  <g key={`${p.date}-${i}`} onMouseEnter={() => setHoverIndex(i)} className="cursor-pointer">
                    <rect
                      x={x - colW / 2}
                      y={chartData.pad.top}
                      width={colW}
                      height={chartData.chartH}
                      fill="transparent"
                    />
                    {hoverIndex === i ? (
                      <g>
                        <line
                          x1={x}
                          y1={chartData.pad.top}
                          x2={x}
                          y2={chartData.pad.top + chartData.chartH}
                          stroke="#38bdf8"
                          strokeWidth="1"
                          strokeDasharray="2 2"
                        />
                        <circle cx={x} cy={chartData.scaleY(p.drawdown_pct)} r="4" fill="#f43f5e" />
                      </g>
                    ) : null}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </div>

      {/* Worst Drawdowns Table */}
      <div className="p-3 bg-surface-sunk/30">
        <div className="text-[11px] font-bold text-ink pb-2">
          Worst Drawdown Episodes
        </div>
        {episodes.length === 0 ? (
          <div className="text-[11px] text-ink-muted">No significant drawdowns recorded.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="border-b border-line bg-surface text-ink-faint">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Rank</th>
                  <th className="px-3 py-1.5 font-medium">Depth (%)</th>
                  <th className="px-3 py-1.5 font-medium">Peak Date</th>
                  <th className="px-3 py-1.5 font-medium">Trough Date</th>
                  <th className="px-3 py-1.5 font-medium">Recovery Date</th>
                  <th className="px-3 py-1.5 font-medium">Duration</th>
                  <th className="px-3 py-1.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {episodes.map((ep, idx) => (
                  <tr key={`${ep.peak_date}-${idx}`} className="hover:bg-surface-sunk/60">
                    <td className="px-3 py-1.5 font-bold text-ink font-mono">#{idx + 1}</td>
                    <td className="px-3 py-1.5 font-bold font-mono text-rose-400">
                      {(ep.depth_pct * 100).toFixed(2)}%
                    </td>
                    <td className="px-3 py-1.5 font-mono text-ink">{ep.peak_date}</td>
                    <td className="px-3 py-1.5 font-mono text-ink">{ep.trough_date}</td>
                    <td className="px-3 py-1.5 font-mono text-ink-muted">
                      {ep.recovery_date || "—"}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-ink">
                      {ep.duration_days} days
                    </td>
                    <td className="px-3 py-1.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[9.5px] font-bold ${
                          ep.status === "Recovered"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-amber-500/20 text-amber-400"
                        }`}
                      >
                        {ep.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
