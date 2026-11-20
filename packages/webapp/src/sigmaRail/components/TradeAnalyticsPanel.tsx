import { useMemo, useState } from "react";
import type { TradeAnalyticsResponse, TradeExcursionPoint } from "../types";

const SCATTER_W = 600;
const SCATTER_H = 220;
const PAD = { top: 16, right: 24, bottom: 32, left: 48 };

function formatDuration(dur: string): string {
  if (!dur || dur === "—") return "—";
  // Convert LEAN duration format "3.19:46:36" to "3.8 days"
  if (dur.includes(".")) {
    const parts = dur.split(".");
    const days = parseInt(parts[0], 10);
    if (parts[1]) {
      const timeParts = parts[1].split(":");
      const hours = parseInt(timeParts[0], 10) || 0;
      const frac = (days + hours / 24).toFixed(1);
      return `${frac} days`;
    }
    return `${days} days`;
  }
  return dur;
}

export function TradeAnalyticsPanel({
  data,
  isLoading,
}: {
  data: TradeAnalyticsResponse | undefined;
  isLoading?: boolean;
}) {
  const [hoveredTrade, setHoveredTrade] = useState<TradeExcursionPoint | null>(null);

  const stats = data?.trade_statistics;
  const excursions = data?.excursions ?? [];

  const scatterGeometry = useMemo(() => {
    if (excursions.length === 0) return null;

    // Filter valid non-infinite numbers
    const valid = excursions.filter(
      (e) => !Number.isNaN(e.mae_pct) && !Number.isNaN(e.mfe_pct),
    );
    if (valid.length === 0) return null;

    const xs = valid.map((e) => Math.abs(e.mae_pct) * 100);
    const ys = valid.map((e) => Math.max(0, e.mfe_pct) * 100);

    const maxX = Math.max(5, Math.min(100, Math.max(...xs)));
    const maxY = Math.max(5, Math.min(100, Math.max(...ys)));

    const innerW = SCATTER_W - PAD.left - PAD.right;
    const innerH = SCATTER_H - PAD.top - PAD.bottom;

    const toX = (mae: number) => PAD.left + (Math.min(maxX, Math.abs(mae) * 100) / maxX) * innerW;
    const toY = (mfe: number) => PAD.top + (1 - Math.min(maxY, Math.max(0, mfe) * 100) / maxY) * innerH;

    return {
      valid,
      maxX,
      maxY,
      toX,
      toY,
    };
  }, [excursions]);

  if (isLoading) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
        Loading trade analytics…
      </div>
    );
  }

  if (!data || !stats) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
        Trade analytics unavailable for this run.
      </div>
    );
  }

  return (
    <section className="mb-6 space-y-4">
      {/* Top Metrics Row */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        <div className="rounded border border-line bg-surface px-3 py-2">
          <div className="text-[10px] text-ink-muted">Expectancy</div>
          <div className="mt-0.5 text-[14px] font-bold tabular-nums text-emerald-400">
            +{stats.expectancy.toFixed(3)}
          </div>
        </div>

        <div className="rounded border border-line bg-surface px-3 py-2">
          <div className="text-[10px] text-ink-muted">Avg Win / Loss</div>
          <div className="mt-0.5 text-[13px] font-semibold tabular-nums text-ink">
            <span className="text-emerald-400">+${stats.average_profit.toFixed(0)}</span>
            <span className="text-ink-faint"> / </span>
            <span className="text-rose-400">-${Math.abs(stats.average_loss).toFixed(0)}</span>
          </div>
        </div>

        <div className="rounded border border-line bg-surface px-3 py-2">
          <div className="text-[10px] text-ink-muted">Largest Win / Loss</div>
          <div className="mt-0.5 text-[13px] font-semibold tabular-nums text-ink">
            <span className="text-emerald-400">+${stats.largest_profit.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            <span className="text-ink-faint"> / </span>
            <span className="text-rose-400">-${Math.abs(stats.largest_loss).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
          </div>
        </div>

        <div className="rounded border border-line bg-surface px-3 py-2">
          <div className="text-[10px] text-ink-muted">Avg Holding Time</div>
          <div className="mt-0.5 text-[13px] font-semibold text-ink">
            {formatDuration(stats.average_trade_duration)}
          </div>
        </div>

        <div className="rounded border border-line bg-surface px-3 py-2">
          <div className="text-[10px] text-ink-muted">Win / Loss Streaks</div>
          <div className="mt-0.5 text-[13px] font-semibold tabular-nums text-ink">
            <span className="text-emerald-400">{stats.max_consecutive_wins} wins</span>
            <span className="text-ink-faint"> · </span>
            <span className="text-rose-400">{stats.max_consecutive_losses} loss</span>
          </div>
        </div>

        <div className="rounded border border-line bg-surface px-3 py-2">
          <div className="text-[10px] text-ink-muted">Avg MAE / MFE</div>
          <div className="mt-0.5 text-[13px] font-semibold tabular-nums text-ink">
            <span className="text-rose-400">-${Math.abs(stats.average_mae).toFixed(0)}</span>
            <span className="text-ink-faint"> / </span>
            <span className="text-emerald-400">+${stats.average_mfe.toFixed(0)}</span>
          </div>
        </div>
      </div>

      {/* MAE / MFE Excursion Scatter Plot */}
      {scatterGeometry ? (
        <div className="rounded border border-line bg-surface p-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-ink">
                MAE vs MFE Excursion Distribution
              </h4>
              <p className="text-[10px] text-ink-faint">
                Trade Drawdown (MAE %) vs Peak Profit (MFE %) for {scatterGeometry.valid.length} closed trades
              </p>
            </div>
            {hoveredTrade ? (
              <div className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11px] font-mono">
                <span className="font-bold text-ink">{hoveredTrade.symbol}</span> ·{" "}
                <span className={hoveredTrade.profit_loss >= 0 ? "text-emerald-400" : "text-rose-400"}>
                  {hoveredTrade.profit_loss >= 0 ? "+" : ""}${hoveredTrade.profit_loss.toFixed(2)} ({(hoveredTrade.return_pct * 100).toFixed(1)}%)
                </span>{" "}
                · MAE: {(hoveredTrade.mae_pct * 100).toFixed(1)}% · MFE: {(hoveredTrade.mfe_pct * 100).toFixed(1)}%
              </div>
            ) : (
              <span className="text-[10px] text-ink-faint">Hover a trade dot to inspect</span>
            )}
          </div>

          <div className="relative mt-2">
            <svg
              viewBox={`0 0 ${SCATTER_W} ${SCATTER_H}`}
              className="h-52 w-full rounded border border-line bg-surface-sunk"
            >
              {/* Grid Lines */}
              <line
                x1={PAD.left}
                y1={PAD.top}
                x2={PAD.left}
                y2={SCATTER_H - PAD.bottom}
                stroke="currentColor"
                className="text-line"
                strokeWidth="1"
              />
              <line
                x1={PAD.left}
                y1={SCATTER_H - PAD.bottom}
                x2={SCATTER_W - PAD.right}
                y2={SCATTER_H - PAD.bottom}
                stroke="currentColor"
                className="text-line"
                strokeWidth="1"
              />

              {/* Diagonal Equality Guide (MFE = MAE) */}
              <line
                x1={scatterGeometry.toX(0)}
                y1={scatterGeometry.toY(0)}
                x2={scatterGeometry.toX(Math.min(scatterGeometry.maxX, scatterGeometry.maxY))}
                y2={scatterGeometry.toY(Math.min(scatterGeometry.maxX, scatterGeometry.maxY))}
                stroke="currentColor"
                strokeDasharray="3 3"
                className="text-line-soft"
                strokeWidth="1"
              />

              {/* Axis Labels */}
              <text
                x={PAD.left + 4}
                y={PAD.top + 10}
                className="fill-ink-faint"
                fontSize="9"
                fontFamily="ui-monospace, monospace"
              >
                MFE % ({scatterGeometry.maxY.toFixed(0)}%)
              </text>
              <text
                x={SCATTER_W - PAD.right}
                y={SCATTER_H - PAD.bottom - 4}
                textAnchor="end"
                className="fill-ink-faint"
                fontSize="9"
                fontFamily="ui-monospace, monospace"
              >
                MAE % ({scatterGeometry.maxX.toFixed(0)}%)
              </text>
              <text
                x={PAD.left}
                y={SCATTER_H - 12}
                className="fill-ink-faint"
                fontSize="9"
                fontFamily="ui-monospace, monospace"
              >
                0%
              </text>

              {/* Data Points */}
              {scatterGeometry.valid.map((t, idx) => {
                const cx = scatterGeometry.toX(t.mae_pct);
                const cy = scatterGeometry.toY(t.mfe_pct);
                const isHovered = hoveredTrade?.id === t.id;
                return (
                  <circle
                    key={t.id || idx}
                    cx={cx}
                    cy={cy}
                    r={isHovered ? 5 : 3}
                    className={`cursor-pointer transition-all ${
                      t.is_win
                        ? "fill-emerald-400/80 stroke-emerald-600 hover:fill-emerald-300"
                        : "fill-rose-400/80 stroke-rose-600 hover:fill-rose-300"
                    }`}
                    strokeWidth={isHovered ? 2 : 0.5}
                    onMouseEnter={() => setHoveredTrade(t)}
                    onMouseLeave={() => setHoveredTrade(null)}
                  />
                );
              })}
            </svg>
          </div>
        </div>
      ) : null}
    </section>
  );
}
