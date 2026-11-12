/**
 * MiniSparklineCard — compact screener card with SVG price sparkline.
 *
 * Fetches a 90-day history for the ticker and renders a tiny sparkline path.
 * All KPI data comes from the parent RankedRow (no extra API calls).
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStockIntrospection } from "../../api/screens";
import { BookmarkButton } from "./BookmarkButton";
import { cn } from "../../lib/utils";
import type { RankedRow } from "../../types";

interface MiniSparklineCardProps {
  row: RankedRow;
  asOfDate: string;
  rank: number;
  onClick: () => void;
}

/**
 * Build a normalised SVG polyline `points` string from close prices.
 * Output fits a 200×56 viewBox.
 */
function buildSparkPoints(closes: number[], w = 200, h = 56): string {
  if (closes.length < 2) return "";
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const pad = 4; // px padding top/bottom
  return closes
    .map((v, i) => {
      const x = (i / (closes.length - 1)) * w;
      const y = pad + ((max - v) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function MiniSparklineCard({ row, asOfDate, rank, onClick }: MiniSparklineCardProps) {
  const ticker = String(row.ticker ?? "");

  // Fetch a compact 90-day price history
  const historyQuery = useQuery({
    queryKey: ["sparkline", ticker, asOfDate],
    queryFn: () => fetchStockIntrospection(ticker, asOfDate, 90, 0),
    staleTime: 600_000,
    enabled: !!ticker && !!asOfDate,
  });

  const closes = useMemo(() => {
    const series = historyQuery.data?.chart_series ?? [];
    return series.map((p: { close?: number; c?: number }) => Number(p.close ?? p.c ?? 0)).filter((v) => v > 0);
  }, [historyQuery.data]);

  const sparkPoints = useMemo(() => buildSparkPoints(closes), [closes]);

  // Derived from sparkline: whether price is trending up over the period
  const sparkTrend = closes.length >= 2 ? closes[closes.length - 1] >= closes[0] : null;

  const rs = row.rs_rating != null ? Math.round(Number(row.rs_rating)) : null;
  const close = row.close != null ? Number(row.close) : null;
  const cagr = (row as Record<string, unknown>).fwd_cagr_2y_normal_pe != null
    ? Number((row as Record<string, unknown>).fwd_cagr_2y_normal_pe)
    : null;
  const valStatus = String((row as Record<string, unknown>).valuation_status ?? "");
  const stage = (row as Record<string, unknown>).stage_code;
  const stageNumber = typeof stage === "string" ? Number(stage[0]) : NaN;
  const companyName = String(row.company_name ?? ticker);

  const isUndervalued = valStatus.toLowerCase().includes("undervalued");
  const isOvervalued = valStatus.toLowerCase().includes("overvalued");

  const sparkColor = sparkTrend === true ? "#10b981" : sparkTrend === false ? "#f43f5e" : "#6366f1";

  return (
    <div
      onClick={onClick}
      className="group relative flex flex-col rounded-xl border border-line bg-surface hover:border-accent/50 hover:bg-surface-raised transition-all cursor-pointer overflow-hidden"
    >
      {/* Header: rank + ticker + bookmark */}
      <div className="flex items-start justify-between px-3 pt-2.5 pb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] text-ink-muted font-mono tabular-nums w-4 shrink-0">{rank}</span>
          <div className="min-w-0">
            <div className="flex items-center gap-1">
              <span className="font-bold text-sm text-accent group-hover:underline font-mono">{ticker}</span>
              {rs !== null && (
                <span
                  className={cn(
                    "text-[9px] font-bold px-1 py-0.5 rounded",
                    rs >= 80 ? "bg-emerald-500/20 text-emerald-400" :
                    rs >= 70 ? "bg-sky-500/20 text-sky-400" :
                    "bg-surface-sunk text-ink-muted"
                  )}
                >
                  {rs}
                </span>
              )}
            </div>
            <p className="text-[10px] text-ink-muted truncate max-w-[120px] leading-tight">{companyName}</p>
          </div>
        </div>
        <BookmarkButton ticker={ticker} />
      </div>

      {/* Sparkline */}
      <div className="px-0 py-0 bg-surface-sunk/40 mx-0">
        {historyQuery.isLoading ? (
          <div className="h-14 flex items-center justify-center">
            <div className="h-0.5 w-16 bg-line rounded animate-pulse" />
          </div>
        ) : sparkPoints ? (
          <svg viewBox="0 0 200 56" className="w-full h-14" preserveAspectRatio="none">
            {/* Gradient fill under the sparkline */}
            <defs>
              <linearGradient id={`spark-fill-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={sparkColor} stopOpacity="0.25" />
                <stop offset="100%" stopColor={sparkColor} stopOpacity="0.02" />
              </linearGradient>
            </defs>
            {/* Filled area */}
            <polygon
              points={`${sparkPoints} 200,56 0,56`}
              fill={`url(#spark-fill-${ticker})`}
            />
            {/* Line */}
            <polyline
              points={sparkPoints}
              fill="none"
              stroke={sparkColor}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        ) : (
          <div className="h-14 flex items-center justify-center text-[10px] text-ink-muted">No chart data</div>
        )}
      </div>

      {/* KPI Row */}
      <div className="flex items-center justify-between px-3 py-1.5 text-xs font-mono">
        {/* Price */}
        <span className="font-bold text-ink">
          {close !== null ? `$${close.toFixed(2)}` : "—"}
        </span>

        {/* Stage badge */}
        <span className={cn(
          "text-[10px] font-bold",
          stageNumber === 2 ? "text-emerald-400" :
          stageNumber === 4 ? "text-rose-400" : "text-amber-400"
        )}>
          {typeof stage === "string" && stage.length > 0 ? stage : "—"}
        </span>

        {/* CAGR */}
        {cagr !== null ? (
          <span className={cn(
            "text-[10px] font-bold",
            cagr >= 20 ? "text-emerald-400" :
            cagr >= 0 ? "text-ink" :
            "text-rose-400"
          )}>
            {cagr >= 0 ? "+" : ""}{cagr.toFixed(1)}%
          </span>
        ) : (
          <span className="text-[10px] text-ink-muted">—</span>
        )}
      </div>

      {/* Valuation Status Footer */}
      {valStatus && (
        <div className={cn(
          "px-3 py-1 text-[9.5px] font-bold border-t border-line",
          isUndervalued ? "bg-emerald-500/10 text-emerald-400" :
          isOvervalued ? "bg-rose-500/10 text-rose-400" :
          "bg-surface-sunk/50 text-ink-muted"
        )}>
          {valStatus}
        </div>
      )}

      {/* Hover overlay: Chart ↗ button */}
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <span className="bg-accent text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow-lg">
          Chart ↗
        </span>
      </div>
    </div>
  );
}
