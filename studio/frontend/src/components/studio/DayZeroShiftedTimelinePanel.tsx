import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunEquityCurve, fetchRunOrders } from "../../api/backtests";

export interface ShiftedTimelineDay {
  dayIndex: number; // 0, 1, 2, ...
  date: string;
  dailyReturnPct: number;
  cumulativeReturnPct: number;
  equity: number;
  isPeak?: boolean;
  isInitial?: boolean;
}

export function DayZeroShiftedTimelinePanel({ runId }: { runId: string }) {
  const [horizonDays, setHorizonDays] = useState<number>(30);
  const [hoverDay, setHoverDay] = useState<ShiftedTimelineDay | null>(null);

  const equityQuery = useQuery({
    queryKey: ["equity-curve", runId],
    queryFn: () => fetchRunEquityCurve(runId),
    enabled: Boolean(runId),
  });

  const ordersQuery = useQuery({
    queryKey: ["run-orders", runId, "day0"],
    queryFn: () => fetchRunOrders(runId, 2000),
    enabled: Boolean(runId),
  });

  const timelineData = useMemo(() => {
    const points = equityQuery.data?.points ?? [];
    const orders = ordersQuery.data?.orders ?? [];

    if (points.length === 0) return null;

    // 1. Identify first buy timestamp
    let firstBuyTs: number | null = null;
    for (const raw of orders) {
      const o = raw as Record<string, unknown>;
      const status = String(o.status ?? "").toLowerCase();
      const direction = String(o.direction ?? "").toLowerCase();
      const isFilled = status.includes("fill") || status === "3" || status === "2";
      if (isFilled && direction === "buy") {
        const t = typeof o.time === "number" ? o.time : Number(o.time);
        if (!Number.isNaN(t) && t > 0) {
          const sec = t > 1e12 ? t / 1000 : t;
          if (firstBuyTs === null || sec < firstBuyTs) {
            firstBuyTs = sec;
          }
        }
      }
    }

    // 2. Aggregate points by calendar trading day (YYYY-MM-DD -> latest equity)
    const byDate = new Map<string, number>();
    for (const pt of points) {
      const ms = pt.t > 1e12 ? pt.t : pt.t * 1000;
      const dStr = new Date(ms).toISOString().slice(0, 10);
      byDate.set(dStr, pt.equity);
    }

    const sortedDates = Array.from(byDate.keys()).sort();
    if (sortedDates.length === 0) return null;

    let day0DateStr = sortedDates[0];
    if (firstBuyTs !== null) {
      const buyDStr = new Date(firstBuyTs * 1000).toISOString().slice(0, 10);
      if (byDate.has(buyDStr)) {
        day0DateStr = buyDStr;
      } else {
        const found = sortedDates.find((d) => d >= buyDStr);
        if (found) day0DateStr = found;
      }
    }

    const day0Idx = sortedDates.indexOf(day0DateStr);
    const effectiveDay0Idx = day0Idx >= 0 ? day0Idx : 0;
    const baseEquity = byDate.get(sortedDates[effectiveDay0Idx]) || points[0].equity || 100000;

    // 3. Build shifted days from Day 0 onwards
    const days: ShiftedTimelineDay[] = [];
    const maxDays = Math.min(sortedDates.length - effectiveDay0Idx, horizonDays + 1);

    let peakIdx = 0;
    let maxCum = -Infinity;

    for (let i = 0; i < maxDays; i++) {
      const dStr = sortedDates[effectiveDay0Idx + i];
      const eq = byDate.get(dStr)!;
      const prevEq = i > 0 ? byDate.get(sortedDates[effectiveDay0Idx + i - 1])! : baseEquity;

      const dailyReturnPct = ((eq - prevEq) / prevEq) * 100;
      const cumulativeReturnPct = ((eq - baseEquity) / baseEquity) * 100;

      if (cumulativeReturnPct > maxCum) {
        maxCum = cumulativeReturnPct;
        peakIdx = i;
      }

      days.push({
        dayIndex: i,
        date: dStr,
        dailyReturnPct,
        cumulativeReturnPct,
        equity: eq,
        isInitial: i === 0,
      });
    }

    if (days[peakIdx]) {
      days[peakIdx].isPeak = true;
    }

    // 4. Geometry calculations for Chart
    const svgW = 740;
    const svgH = 220;
    const pad = { top: 24, right: 36, bottom: 32, left: 54 };
    const innerW = svgW - pad.left - pad.right;
    const innerH = svgH - pad.top - pad.bottom;

    const cumVals = days.map((d) => d.cumulativeReturnPct);
    const rawMin = Math.min(0, ...cumVals);
    const rawMax = Math.max(0, ...cumVals);
    const span = rawMax - rawMin || 2;
    const minVal = Math.floor(rawMin - span * 0.15);
    const maxVal = Math.ceil(rawMax + span * 0.15);

    const scaleX = (dIdx: number) =>
      pad.left + (dIdx / Math.max(1, days.length - 1)) * innerW;
    const scaleY = (v: number) =>
      pad.top + innerH - ((v - minVal) / (maxVal - minVal || 1)) * innerH;

    const linePoints = days.map((d) => `${scaleX(d.dayIndex)},${scaleY(d.cumulativeReturnPct)}`).join(" ");
    const areaPoints = `${scaleX(0)},${scaleY(0)} ` + linePoints + ` ${scaleX(days.length - 1)},${scaleY(0)}`;

    return {
      days,
      day0DateStr,
      baseEquity,
      peakDay: days[peakIdx],
      finalDay: days[days.length - 1],
      svgW,
      svgH,
      pad,
      innerW,
      innerH,
      minVal,
      maxVal,
      scaleX,
      scaleY,
      linePoints,
      areaPoints,
    };
  }, [equityQuery.data, ordersQuery.data, horizonDays]);

  const isLoading = equityQuery.isLoading || ordersQuery.isLoading;

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface shadow-sm overflow-hidden">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-raised px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-bold text-ink">
            Shifted Timeline Matrix (Day 0 Baseline)
          </span>
          <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10px] text-ink-muted">
            First Buy Entry = Day 0
          </span>
        </div>

        {/* Horizon Selector */}
        <div className="flex items-center gap-1">
          <span className="text-[11px] text-ink-faint mr-1">Horizon:</span>
          {([14, 30, 60, 90] as const).map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHorizonDays(h)}
              className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                horizonDays === h
                  ? "bg-accent text-accent-ink"
                  : "bg-surface-sunk text-ink-muted hover:text-ink"
              }`}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      {/* Summary Scorecard */}
      {timelineData ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 border-b border-line bg-surface-sunk/30 p-3 text-[11px]">
          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Day 0 Inception Date</div>
            <div className="font-mono text-[13px] font-bold text-ink">
              {timelineData.day0DateStr}
            </div>
          </div>
          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Base Capital Deploy</div>
            <div className="font-mono text-[13px] font-bold text-ink">
              ${timelineData.baseEquity.toLocaleString("en-US", { maximumFractionDigits: 0 })}
            </div>
          </div>
          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Peak Return (Since Buy)</div>
            <div className="font-mono text-[13px] font-bold text-emerald-400">
              +{timelineData.peakDay?.cumulativeReturnPct.toFixed(2)}%
              <span className="text-[10px] font-normal text-ink-faint ml-1">
                (Day {timelineData.peakDay?.dayIndex})
              </span>
            </div>
          </div>
          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Final Return ({timelineData.finalDay?.dayIndex}d)</div>
            <div className={`font-mono text-[13px] font-bold ${
              (timelineData.finalDay?.cumulativeReturnPct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}>
              {(timelineData.finalDay?.cumulativeReturnPct ?? 0) >= 0 ? "+" : ""}
              {timelineData.finalDay?.cumulativeReturnPct.toFixed(2)}%
            </div>
          </div>
        </div>
      ) : null}

      {/* Chart Canvas */}
      <div className="p-3">
        {isLoading ? (
          <div className="flex h-48 items-center justify-center text-[12px] text-ink-muted">
            Loading shifted baseline timeline…
          </div>
        ) : !timelineData || timelineData.days.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-[12px] text-ink-muted">
            No order inception data found to anchor Day 0.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Active inspection banner */}
            <div className="flex flex-wrap items-center justify-between text-[11px] font-mono pb-1 border-b border-line/40">
              {hoverDay ? (
                <div className="flex items-center gap-3">
                  <span className="font-bold text-accent">
                    Day {hoverDay.dayIndex} ({hoverDay.date})
                  </span>
                  <span className="text-ink">
                    Daily: <span className={hoverDay.dailyReturnPct >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                      {hoverDay.dailyReturnPct >= 0 ? "+" : ""}{hoverDay.dailyReturnPct.toFixed(2)}%
                    </span>
                  </span>
                  <span className="text-ink">
                    Cumulative: <span className={hoverDay.cumulativeReturnPct >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                      {hoverDay.cumulativeReturnPct >= 0 ? "+" : ""}{hoverDay.cumulativeReturnPct.toFixed(2)}%
                    </span>
                  </span>
                  <span className="text-ink-muted">
                    Equity: ${hoverDay.equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-ink-faint">
                  <span>Cumulative Backtest Return Since First Buy (%)</span>
                  <span>· Hover any day point to inspect</span>
                </div>
              )}
            </div>

            {/* SVG Chart */}
            <svg
              viewBox={`0 0 ${timelineData.svgW} ${timelineData.svgH}`}
              className="w-full h-52 select-none"
              onMouseLeave={() => setHoverDay(null)}
            >
              <defs>
                <linearGradient id="dayZeroGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.22" />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Zero return reference line */}
              <line
                x1={timelineData.pad.left}
                y1={timelineData.scaleY(0)}
                x2={timelineData.svgW - timelineData.pad.right}
                y2={timelineData.scaleY(0)}
                stroke="#475569"
                strokeWidth="1.2"
              />

              {/* Day 0 Vertical Baseline Axis */}
              <line
                x1={timelineData.scaleX(0)}
                y1={timelineData.pad.top}
                x2={timelineData.scaleX(0)}
                y2={timelineData.pad.top + timelineData.innerH}
                stroke="#64748b"
                strokeWidth="1.5"
              />

              {/* Grid Lines & Labels */}
              {[-4, -2, 0, 2, 4, 6, 8, 10, 12, 14, 16].filter(
                (v) => v >= timelineData.minVal && v <= timelineData.maxVal
              ).map((v) => {
                const y = timelineData.scaleY(v);
                return (
                  <g key={v}>
                    <line
                      x1={timelineData.pad.left}
                      y1={y}
                      x2={timelineData.svgW - timelineData.pad.right}
                      y2={y}
                      stroke="#334155"
                      strokeWidth="0.8"
                      strokeDasharray="3 3"
                    />
                    <text
                      x={timelineData.pad.left - 6}
                      y={y + 3}
                      fill="#94a3b8"
                      fontSize="9"
                      fontFamily="monospace"
                      textAnchor="end"
                    >
                      {v.toFixed(1)}%
                    </text>
                  </g>
                );
              })}

              {/* Day 10 Time-Stop Reference Guide */}
              {timelineData.days.length > 10 && (
                <g>
                  <line
                    x1={timelineData.scaleX(10)}
                    y1={timelineData.pad.top}
                    x2={timelineData.scaleX(10)}
                    y2={timelineData.pad.top + timelineData.innerH}
                    stroke="#f59e0b"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                  <text
                    x={timelineData.scaleX(10)}
                    y={timelineData.pad.top - 6}
                    fill="#f59e0b"
                    fontSize="8.5"
                    fontFamily="monospace"
                    textAnchor="middle"
                  >
                    Day 10 (Time-Stop)
                  </text>
                </g>
              )}

              {/* Area polygon */}
              <polygon points={timelineData.areaPoints} fill="url(#dayZeroGrad)" />

              {/* Cumulative Return Polyline (Blue) */}
              <polyline
                points={timelineData.linePoints}
                fill="none"
                stroke="#3b82f6"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />

              {/* Data points & Interactive Hover columns */}
              {timelineData.days.map((d) => {
                const cx = timelineData.scaleX(d.dayIndex);
                const cy = timelineData.scaleY(d.cumulativeReturnPct);
                const isHovered = hoverDay?.dayIndex === d.dayIndex;
                const colW = timelineData.innerW / Math.max(1, timelineData.days.length);

                return (
                  <g
                    key={d.dayIndex}
                    onMouseEnter={() => setHoverDay(d)}
                    className="cursor-pointer"
                  >
                    {/* Hit target */}
                    <rect
                      x={cx - colW / 2}
                      y={timelineData.pad.top}
                      width={colW}
                      height={timelineData.innerH}
                      fill="transparent"
                    />

                    {/* Point Circle */}
                    <circle
                      cx={cx}
                      cy={cy}
                      r={isHovered ? 5 : d.isInitial || d.isPeak ? 4 : 2.5}
                      fill={d.isPeak ? "#10b981" : "#3b82f6"}
                      stroke="#ffffff"
                      strokeWidth={isHovered ? 2 : 1}
                    />

                    {/* X-axis Day tick label */}
                    {d.dayIndex % (timelineData.days.length > 30 ? 5 : 2) === 0 && (
                      <text
                        x={cx}
                        y={timelineData.svgH - 12}
                        fill="#94a3b8"
                        fontSize="9"
                        fontFamily="monospace"
                        textAnchor="middle"
                      >
                        {d.dayIndex}
                      </text>
                    )}

                    {/* Key Callout Annotations */}
                    {d.isInitial && (
                      <text
                        x={cx + 8}
                        y={cy - 6}
                        fill="#94a3b8"
                        fontSize="9"
                        fontFamily="monospace"
                      >
                        Initial Entry (0.0%)
                      </text>
                    )}
                    {d.isPeak && (
                      <text
                        x={cx}
                        y={cy - 10}
                        fill="#10b981"
                        fontSize="9"
                        fontFamily="monospace"
                        textAnchor="middle"
                        fontWeight="bold"
                      >
                        Peak ({d.cumulativeReturnPct > 0 ? "+" : ""}{d.cumulativeReturnPct.toFixed(2)}%)
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>

            {/* Shifted Timeline Matrix Data Table */}
            <div className="mt-3 max-h-64 overflow-auto rounded border border-line bg-surface-sunk/40">
              <table className="w-full text-left text-[11px]">
                <thead className="sticky top-0 bg-surface-raised border-b border-line text-ink-faint font-mono text-[10px]">
                  <tr>
                    <th className="px-3 py-1.5">Timeline</th>
                    <th className="px-3 py-1.5">Session Date</th>
                    <th className="px-3 py-1.5">Daily Return (Bar Metric)</th>
                    <th className="px-3 py-1.5">Cumulative Return (Line Metric)</th>
                    <th className="px-3 py-1.5 text-right">Equity</th>
                    <th className="px-3 py-1.5">Milestone</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60 font-mono text-[10.5px]">
                  {timelineData.days.map((d) => (
                    <tr
                      key={d.dayIndex}
                      onMouseEnter={() => setHoverDay(d)}
                      onMouseLeave={() => setHoverDay(null)}
                      className={`hover:bg-accent/10 transition-colors ${
                        hoverDay?.dayIndex === d.dayIndex ? "bg-accent/15" : ""
                      }`}
                    >
                      <td className="px-3 py-1 font-bold text-accent">
                        Day {d.dayIndex}
                      </td>
                      <td className="px-3 py-1 text-ink-muted">
                        {d.date}
                      </td>
                      <td className="px-3 py-1">
                        <span className={`font-semibold ${d.dailyReturnPct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                          {d.dailyReturnPct >= 0 ? "+" : ""}{d.dailyReturnPct.toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-3 py-1">
                        <span className={`font-semibold ${d.cumulativeReturnPct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                          {d.cumulativeReturnPct >= 0 ? "+" : ""}{d.cumulativeReturnPct.toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-3 py-1 text-right text-ink">
                        ${d.equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                      </td>
                      <td className="px-3 py-1">
                        {d.isInitial ? (
                          <span className="rounded bg-surface px-1.5 py-0.5 text-[9.5px] text-ink-faint border border-line">
                            First Buy Entry
                          </span>
                        ) : d.isPeak ? (
                          <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9.5px] font-bold text-emerald-400 border border-emerald-500/40">
                            Strategy Peak
                          </span>
                        ) : d.dayIndex === 10 ? (
                          <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9.5px] font-semibold text-amber-300 border border-amber-500/40">
                            Time-Stop Window
                          </span>
                        ) : d.dayIndex === timelineData.finalDay?.dayIndex ? (
                          <span className="rounded bg-surface px-1.5 py-0.5 text-[9.5px] text-ink-muted border border-line">
                            Current Horizon
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DayZeroShiftedTimelinePanel;
