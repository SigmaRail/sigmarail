import { useMemo, useState } from "react";
import type { AnnualGrowthPoint, BeatMissStatus, QuarterlyGrowthPoint } from "../../types";
import { cn } from "../../lib/utils";

interface TradingViewForecastAccuracyChartProps {
  quarterlyGrowth?: QuarterlyGrowthPoint[];
  annualGrowth?: AnnualGrowthPoint[];
  ticker: string;
  asOfDate?: string;
  onClose?: () => void;
  className?: string;
}

type PeriodMode = "quarterly" | "annual";

interface ChartPoint {
  periodLabel: string;
  subLabel: string;
  isEstimate: boolean;
  actual: number | null;
  estimate: number | null;
  surpriseVal: number | null;
  surprisePct: number | null;
  beatMiss: BeatMissStatus | null;
}

function formatRevenue(val: number | null): string {
  if (val === null) return "—";
  if (Math.abs(val) >= 1000) {
    return `$${(val / 1000).toFixed(2)}B`;
  }
  return `$${val.toFixed(1)}M`;
}

function formatEps(val: number | null): string {
  if (val === null) return "—";
  return `$${val.toFixed(2)}`;
}

interface SingleForecastPaneProps {
  title: string;
  unitLabel: string;
  points: ChartPoint[];
  formatter: (v: number | null) => string;
  activeIdx: number | null;
  onHover: (idx: number | null) => void;
}

function SingleForecastPane({
  title,
  unitLabel,
  points,
  formatter,
  activeIdx,
  onHover,
}: SingleForecastPaneProps) {
  const width = 480;
  const height = 210;
  const padLeft = 55;
  const padRight = 30;
  const padTop = 25;
  const padBottom = 35;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  // Calculate min/max across all valid values
  const { minVal, maxVal } = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const p of points) {
      if (p.actual !== null) {
        min = Math.min(min, p.actual);
        max = Math.max(max, p.actual);
      }
      if (p.estimate !== null) {
        min = Math.min(min, p.estimate);
        max = Math.max(max, p.estimate);
      }
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      return { minVal: 0, maxVal: 100 };
    }
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const margin = (max - min) * 0.18;
    return { minVal: min - margin, maxVal: max + margin };
  }, [points]);

  const getY = (val: number | null) => {
    if (val === null) return 0;
    const norm = (val - minVal) / (maxVal - minVal);
    return padTop + chartH * (1 - norm);
  };

  const getX = (idx: number) => {
    if (points.length <= 1) return padLeft + chartW / 2;
    return padLeft + (idx / (points.length - 1)) * chartW;
  };

  // Y-axis grid ticks (4 steps)
  const yTicks = useMemo(() => {
    const ticks = [];
    const count = 4;
    for (let i = 0; i <= count; i++) {
      const v = minVal + (i / count) * (maxVal - minVal);
      const y = padTop + chartH * (1 - i / count);
      ticks.push({ val: v, y });
    }
    return ticks;
  }, [minVal, maxVal, chartH, padTop]);

  // Actuals path line
  const actualPath = useMemo(() => {
    const valid = points
      .map((p, idx) => ({ p, idx }))
      .filter((item) => item.p.actual !== null);
    if (valid.length < 2) return "";
    return valid
      .map((item, i) => `${i === 0 ? "M" : "L"} ${getX(item.idx)} ${getY(item.p.actual)}`)
      .join(" ");
  }, [points, minVal, maxVal]);

  // Estimates path line
  const estimatePath = useMemo(() => {
    const valid = points
      .map((p, idx) => ({ p, idx }))
      .filter((item) => item.p.estimate !== null);
    if (valid.length < 2) return "";
    return valid
      .map((item, i) => `${i === 0 ? "M" : "L"} ${getX(item.idx)} ${getY(item.p.estimate)}`)
      .join(" ");
  }, [points, minVal, maxVal]);

  return (
    <div className="flex flex-col flex-1 rounded border border-line bg-surface-sunk/40 p-2.5">
      <div className="flex items-center justify-between pb-1.5 border-b border-line/60">
        <span className="text-xs font-bold text-ink uppercase tracking-wide">{title}</span>
        <span className="text-[10px] text-ink-muted">{unitLabel}</span>
      </div>

      <div className="relative w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto select-none"
          onMouseLeave={() => onHover(null)}
        >
          {/* Horizontal Gridlines & Y-labels */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line
                x1={padLeft}
                y1={t.y}
                x2={width - padRight}
                y2={t.y}
                stroke="#27272a"
                strokeDasharray="3 3"
                strokeWidth="1"
              />
              <text
                x={padLeft - 8}
                y={t.y + 3.5}
                fill="#71717a"
                fontSize="9"
                textAnchor="end"
                fontFamily="monospace"
              >
                {formatter(t.val)}
              </text>
            </g>
          ))}

          {/* Vertical Columns / X-Axis Grid */}
          {points.map((p, idx) => {
            const x = getX(idx);
            const isHovered = activeIdx === idx;
            return (
              <g key={`x-${idx}`}>
                {/* Vertical column highlight on hover */}
                {isHovered && (
                  <rect
                    x={x - 14}
                    y={padTop - 5}
                    width={28}
                    height={chartH + 10}
                    fill="#38bdf8"
                    fillOpacity="0.08"
                    rx="3"
                  />
                )}

                {/* X-axis tick label */}
                <text
                  x={x}
                  y={height - 12}
                  fill={isHovered ? "#38bdf8" : p.isEstimate ? "#38bdf8" : "#a1a1aa"}
                  fontSize="9.5"
                  fontWeight={isHovered ? "bold" : "normal"}
                  textAnchor="middle"
                  fontFamily="monospace"
                >
                  {p.periodLabel}
                  {p.isEstimate ? "e" : ""}
                </text>
              </g>
            );
          })}

          {/* Estimates Path (Cyan Dotted Line) */}
          {estimatePath && (
            <path
              d={estimatePath}
              fill="none"
              stroke="#38bdf8"
              strokeWidth="1.5"
              strokeDasharray="4 3"
              opacity="0.8"
            />
          )}

          {/* Actuals Path (Solid Cyan/Blue Line) */}
          {actualPath && (
            <path
              d={actualPath}
              fill="none"
              stroke="#0284c7"
              strokeWidth="2"
              opacity="0.95"
            />
          )}

          {/* Surprise Stems and Data Points */}
          {points.map((p, idx) => {
            const x = getX(idx);
            const yAct = p.actual !== null ? getY(p.actual) : null;
            const yEst = p.estimate !== null ? getY(p.estimate) : null;
            const isHovered = activeIdx === idx;

            return (
              <g
                key={`pts-${idx}`}
                className="cursor-pointer"
                onMouseEnter={() => onHover(idx)}
              >
                {/* Connecting stem between actual and estimate */}
                {yAct !== null && yEst !== null && (
                  <line
                    x1={x}
                    y1={yAct}
                    x2={x}
                    y2={yEst}
                    stroke={
                      p.beatMiss === "beat"
                        ? "#10b981"
                        : p.beatMiss === "miss"
                        ? "#f43f5e"
                        : "#71717a"
                    }
                    strokeWidth={isHovered ? "2.5" : "1.5"}
                    strokeDasharray="2 2"
                    opacity={isHovered ? "1" : "0.75"}
                  />
                )}

                {/* Estimate Ring: Hollow circle — fill=white so ring looks open on light bg */}
                {yEst !== null && (
                  <circle
                    cx={x}
                    cy={yEst}
                    r={isHovered ? 6 : 4.5}
                    fill="white"
                    stroke="#38bdf8"
                    strokeWidth={isHovered ? "2.5" : "1.8"}
                  />
                )}

                {/* Actual Dot: Solid Filled circle */}
                {yAct !== null && (
                  <circle
                    cx={x}
                    cy={yAct}
                    r={isHovered ? 6 : 4.5}
                    fill={
                      p.beatMiss === "beat"
                        ? "#10b981"
                        : p.beatMiss === "miss"
                        ? "#f43f5e"
                        : "#0284c7"
                    }
                    stroke="#ffffff"
                    strokeWidth="1.2"
                  />
                )}

                {/* Beat / Miss subtle chevron indicator on hover */}
                {isHovered && p.beatMiss && yAct !== null && (
                  <text
                    x={x}
                    y={yAct - 8}
                    textAnchor="middle"
                    fill={p.beatMiss === "beat" ? "#10b981" : "#f43f5e"}
                    fontSize="10"
                    fontWeight="bold"
                  >
                    {p.beatMiss === "beat" ? "▲" : "▼"}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

export function TradingViewForecastAccuracyChart({
  quarterlyGrowth = [],
  annualGrowth = [],
  ticker,
  asOfDate,
  onClose,
  className,
}: TradingViewForecastAccuracyChartProps) {
  const [periodMode, setPeriodMode] = useState<PeriodMode>("quarterly");
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Shape Quarterly points (ordered chronologically oldest to newest, up to 10 points)
  const quarterlyPoints = useMemo(() => {
    const list = [...quarterlyGrowth].sort((a, b) => {
      const ae = a.is_estimate ? 1 : 0;
      const be = b.is_estimate ? 1 : 0;
      if (ae !== be) return ae - be;
      return (a.report_date || "").localeCompare(b.report_date || "");
    });
    const recent = list.slice(-10);

    const revPoints: ChartPoint[] = [];
    const epsPoints: ChartPoint[] = [];

    for (const q of recent) {
      const dateStr = q.report_date || "";
      const periodLabel = dateStr ? dateStr.slice(2, 7) : "—";

      revPoints.push({
        periodLabel,
        subLabel: dateStr,
        isEstimate: Boolean(q.is_estimate),
        actual: q.revenue_actual ?? (!q.is_estimate ? q.revenue_m : null),
        estimate: q.revenue_estimate ?? (q.is_estimate ? q.revenue_m : null),
        surpriseVal: q.revenue_surprise_m ?? null,
        surprisePct: q.revenue_surprise_pct ?? null,
        beatMiss: q.revenue_beat_miss ?? null,
      });

      epsPoints.push({
        periodLabel,
        subLabel: dateStr,
        isEstimate: Boolean(q.is_estimate),
        actual: q.eps_actual ?? (!q.is_estimate ? q.eps : null),
        estimate: q.eps_estimate ?? (q.is_estimate ? q.eps : null),
        surpriseVal: q.eps_surprise_dollar ?? null,
        surprisePct: q.eps_surprise_pct ?? q.surprise_pct ?? null,
        beatMiss: q.eps_beat_miss ?? null,
      });
    }

    return { revPoints, epsPoints };
  }, [quarterlyGrowth]);

  // Shape Annual points (ordered oldest to newest, up to 8 points)
  const annualPoints = useMemo(() => {
    const list = [...annualGrowth].sort((a, b) =>
      String(a.year).localeCompare(String(b.year))
    );
    const recent = list.slice(-8);

    const revPoints: ChartPoint[] = [];
    const epsPoints: ChartPoint[] = [];

    for (const a of recent) {
      const yr = String(a.year).replace(/e$/i, "");
      const isEst = Boolean(a.is_estimate);

      revPoints.push({
        periodLabel: yr,
        subLabel: `FY ${yr}`,
        isEstimate: isEst,
        actual: a.sales_actual ?? (!isEst ? a.sales_m : null),
        estimate: a.sales_estimate ?? (isEst ? a.sales_m : null),
        surpriseVal: null,
        surprisePct: null,
        beatMiss: a.sales_beat_miss ?? null,
      });

      epsPoints.push({
        periodLabel: yr,
        subLabel: `FY ${yr}`,
        isEstimate: isEst,
        actual: a.eps_actual ?? (!isEst ? a.eps : null),
        estimate: a.eps_estimate ?? (isEst ? a.eps : null),
        surpriseVal: null,
        surprisePct: null,
        beatMiss: a.eps_beat_miss ?? null,
      });
    }

    return { revPoints, epsPoints };
  }, [annualGrowth]);

  const activeData = periodMode === "quarterly" ? quarterlyPoints : annualPoints;
  const activeRevPoint = hoveredIdx !== null ? activeData.revPoints[hoveredIdx] : null;
  const activeEpsPoint = hoveredIdx !== null ? activeData.epsPoints[hoveredIdx] : null;

  return (
    <div
      className={cn(
        "flex flex-col w-full rounded-lg border border-line bg-surface p-3 font-mono text-[11px] shadow-lg",
        className
      )}
    >
      {/* Header with Title, Period Switcher, and Legend */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2.5 mb-2 border-b border-line">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-ink">
            {ticker} Forecasts & Estimates Accuracy
          </span>
          {asOfDate && (
            <span className="rounded bg-surface-raised px-1.5 py-0.5 text-[10px] text-ink-muted">
              As-of {asOfDate}
            </span>
          )}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-[10.5px]">
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-sky-600 border border-white" />
            <span className="text-ink">Reported</span>
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 border border-white" />
            <span className="text-ink">Beat</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-sky-400 bg-surface" />
            <span className="text-ink-muted">Estimate</span>
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-rose-500 border border-white" />
            <span className="text-ink">Miss</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">▲ Beat</span>
            <span className="text-ink-muted">/</span>
            <span className="text-rose-400 font-bold">▼ Miss</span>
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-zinc-400 border border-white" />
            <span className="text-ink-muted">Reported</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-sky-400 bg-white" />
            <span className="text-ink-muted">Estimate</span>
          </div>
        </div>

        {/* Controls: Annual / Quarterly toggle & Close */}
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded border border-line bg-surface-sunk p-0.5 text-[10px]">
            <button
              type="button"
              onClick={() => {
                setPeriodMode("quarterly");
                setHoveredIdx(null);
              }}
              className={cn(
                "rounded px-2.5 py-0.5 font-bold transition-all",
                periodMode === "quarterly"
                  ? "bg-accent/20 text-accent font-bold shadow-sm"
                  : "text-ink-muted hover:text-ink"
              )}
            >
              Quarterly
            </button>
            <button
              type="button"
              onClick={() => {
                setPeriodMode("annual");
                setHoveredIdx(null);
              }}
              className={cn(
                "rounded px-2.5 py-0.5 font-bold transition-all",
                periodMode === "annual"
                  ? "bg-accent/20 text-accent font-bold shadow-sm"
                  : "text-ink-muted hover:text-ink"
              )}
            >
              Annual
            </button>
          </div>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-ink-muted hover:bg-surface-raised hover:text-ink"
              title="Close chart"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Dual Sub-Charts (Revenue on left, Earnings on right) */}
      <div className="flex flex-col md:flex-row items-stretch gap-3">
        <SingleForecastPane
          title="Revenue"
          unitLabel="USD (M / B)"
          points={activeData.revPoints}
          formatter={formatRevenue}
          activeIdx={hoveredIdx}
          onHover={setHoveredIdx}
        />

        <SingleForecastPane
          title="Earnings (EPS)"
          unitLabel="Diluted EPS (USD)"
          points={activeData.epsPoints}
          formatter={formatEps}
          activeIdx={hoveredIdx}
          onHover={setHoveredIdx}
        />
      </div>

      {/* Interactive Tooltip Card on Hover */}
      <div className="mt-2.5 min-h-[46px] rounded border border-line bg-surface-raised/70 px-3 py-2 text-[10.5px]">
        {activeRevPoint && activeEpsPoint ? (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2 font-bold text-ink">
              <span className="text-accent">{activeRevPoint.periodLabel}</span>
              <span className="text-ink-muted font-normal">({activeRevPoint.subLabel})</span>
              {activeRevPoint.isEstimate && (
                <span className="rounded bg-sky-500/15 border border-sky-500/40 px-1.5 py-0.2 text-[9px] text-sky-400 uppercase font-bold">
                  Consensus Estimate
                </span>
              )}
            </div>

            {/* Revenue Details */}
            <div className="flex items-center gap-3">
              <span className="text-ink-muted">Revenue:</span>
              <span className="text-ink">
                Act: <strong className="text-sky-300">{formatRevenue(activeRevPoint.actual)}</strong>
              </span>
              <span className="text-ink-muted">
                Est: {formatRevenue(activeRevPoint.estimate)}
              </span>
              {activeRevPoint.surprisePct !== null && (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.2 text-[9.5px] font-bold",
                    activeRevPoint.surprisePct > 0
                      ? "bg-emerald-500/15 text-emerald-400"
                      : activeRevPoint.surprisePct < 0
                      ? "bg-rose-500/15 text-rose-400"
                      : "text-ink-muted"
                  )}
                >
                  {activeRevPoint.surprisePct > 0 ? "+" : ""}
                  {activeRevPoint.surprisePct.toFixed(1)}%{" "}
                  {activeRevPoint.beatMiss ? activeRevPoint.beatMiss.toUpperCase() : ""}
                </span>
              )}
            </div>

            {/* EPS Details */}
            <div className="flex items-center gap-3">
              <span className="text-ink-muted">EPS:</span>
              <span className="text-ink">
                Act: <strong className="text-sky-300">{formatEps(activeEpsPoint.actual)}</strong>
              </span>
              <span className="text-ink-muted">
                Est: {formatEps(activeEpsPoint.estimate)}
              </span>
              {activeEpsPoint.surprisePct !== null && (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.2 text-[9.5px] font-bold",
                    activeEpsPoint.surprisePct > 0
                      ? "bg-emerald-500/15 text-emerald-400"
                      : activeEpsPoint.surprisePct < 0
                      ? "bg-rose-500/15 text-rose-400"
                      : "text-ink-muted"
                  )}
                >
                  {activeEpsPoint.surprisePct > 0 ? "+" : ""}
                  {activeEpsPoint.surprisePct.toFixed(1)}%{" "}
                  {activeEpsPoint.beatMiss ? activeEpsPoint.beatMiss.toUpperCase() : ""}
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between text-ink-muted">
            <span>Hover over any data point to inspect reported vs. consensus estimates & beat/miss surprises.</span>
            <span className="text-[9.5px]">Dual pane: Revenue (left) & EPS (right)</span>
          </div>
        )}
      </div>
    </div>
  );
}
