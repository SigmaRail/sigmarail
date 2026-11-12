import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchRunPortfolioExposure } from "../../api/backtests";

export function PortfolioExposurePanel({ runId }: { runId: string }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["backtest-portfolio-exposure", runId],
    queryFn: () => fetchRunPortfolioExposure(runId),
    enabled: Boolean(runId),
  });

  const series = data?.series ?? [];

  const width = 760;
  const height = 150;
  const pad = { top: 12, right: 35, bottom: 22, left: 35 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  const chartData = useMemo(() => {
    if (series.length < 2) return null;

    const scaleX = (i: number) => pad.left + (i / (series.length - 1)) * chartW;
    const scaleY = (pct: number) => pad.top + chartH - (pct / 100) * chartH;

    // Long Exposure area path
    let areaPath = `M ${scaleX(0)} ${pad.top + chartH}`;
    series.forEach((p, i) => {
      areaPath += ` L ${scaleX(i)} ${scaleY(p.long_pct)}`;
    });
    areaPath += ` L ${scaleX(series.length - 1)} ${pad.top + chartH} Z`;

    // Long line path
    let linePath = "";
    series.forEach((p, i) => {
      linePath += `${i === 0 ? "M" : "L"} ${scaleX(i)} ${scaleY(p.long_pct)} `;
    });

    return {
      scaleX,
      scaleY,
      areaPath,
      linePath,
    };
  }, [series, chartW, chartH, pad.left, pad.top]);

  if (isLoading) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-[12px] text-ink-muted">
        Loading portfolio exposure & capacity…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-[12px] text-danger">
        {error ? (error as Error).message : "Failed to load exposure analytics"}
      </div>
    );
  }

  const activePoint = hoverIndex !== null && series[hoverIndex] ? series[hoverIndex] : series[series.length - 1];

  return (
    <div className="rounded border border-line bg-surface p-3.5">
      {/* Header & KPI Row */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Portfolio Exposure & Strategy Capacity
          </h3>
          <p className="mt-0.5 text-[11px] text-ink-muted">
            Daily capital deployment (Long % vs Cash %) and institutional liquidity capacity
          </p>
        </div>

        <div className="flex items-center gap-4 font-mono text-[11px]">
          <div>
            <span className="text-ink-faint">Avg Exposure: </span>
            <span className="font-semibold text-sky-400">{data.avg_long_pct}%</span>
          </div>
          <div>
            <span className="text-ink-faint">Max Holdings: </span>
            <span className="font-semibold text-ink">{data.max_holdings} pos</span>
          </div>
          <div className="rounded bg-accent/15 px-2 py-0.5 border border-accent/30 text-[10.5px]">
            <span className="text-accent-ink font-bold">Est. Capacity: ${data.estimated_capacity_m}M</span>
          </div>
        </div>
      </div>

      {/* Interactive Cursor Details */}
      {activePoint ? (
        <div className="mt-2.5 flex items-center justify-between font-mono text-[10.5px] text-ink-muted">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-ink">{activePoint.date}</span>
            <span>·</span>
            <span>Equity: ${activePoint.equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sky-400 font-semibold">
              Long: {activePoint.long_pct}% (${activePoint.long_value.toLocaleString(undefined, { maximumFractionDigits: 0 })})
            </span>
            <span className="text-emerald-400 font-semibold">
              Cash: {activePoint.cash_pct}% (${activePoint.cash_value.toLocaleString(undefined, { maximumFractionDigits: 0 })})
            </span>
            <span>Holdings: {activePoint.holdings_count}</span>
          </div>
        </div>
      ) : null}

      {/* SVG Stacked Area Chart */}
      {chartData && series.length > 1 ? (
        <div className="relative mt-2">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full rounded border border-line/60 bg-surface-sunk overflow-hidden select-none"
            style={{ maxHeight: 150 }}
          >
            <defs>
              <linearGradient id="longExposureGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0284c7" stopOpacity="0.45" />
                <stop offset="100%" stopColor="#0284c7" stopOpacity="0.05" />
              </linearGradient>
            </defs>

            {/* Gridlines */}
            {[0, 25, 50, 75, 100].map((pct) => {
              const y = chartData.scaleY(pct);
              return (
                <g key={pct}>
                  <line
                    x1={pad.left}
                    y1={y}
                    x2={width - pad.right}
                    y2={y}
                    stroke="#27272a"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                  <text
                    x={width - pad.right + 6}
                    y={y + 3.5}
                    fill="#71717a"
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    {pct}%
                  </text>
                </g>
              );
            })}

            {/* Area & Line */}
            <path d={chartData.areaPath} fill="url(#longExposureGrad)" />
            <path
              d={chartData.linePath}
              fill="none"
              stroke="#38bdf8"
              strokeWidth="2"
              strokeLinecap="round"
            />

            {/* Interactive Hover Columns */}
            {series.map((p, i) => {
              const x = chartData.scaleX(i);
              const colW = chartW / (series.length || 1);
              return (
                <g
                  key={`${p.date}-${i}`}
                  onMouseEnter={() => setHoverIndex(i)}
                  className="cursor-pointer"
                >
                  <rect
                    x={x - colW / 2}
                    y={pad.top}
                    width={colW}
                    height={chartH}
                    fill="transparent"
                  />
                  {hoverIndex === i ? (
                    <g>
                      <line
                        x1={x}
                        y1={pad.top}
                        x2={x}
                        y2={pad.top + chartH}
                        stroke="#f43f5e"
                        strokeWidth="1"
                        strokeDasharray="2 2"
                      />
                      <circle
                        cx={x}
                        cy={chartData.scaleY(p.long_pct)}
                        r={3.5}
                        fill="#38bdf8"
                        stroke="#ffffff"
                        strokeWidth="1.5"
                      />
                    </g>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </div>
      ) : null}
    </div>
  );
}
