import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchRunAssetAllocation } from "../../api/backtests";
import type { AssetAllocationItem } from "../../types";

interface TreemapRect {
  item: AssetAllocationItem;
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Squarified treemap layout generator.
 */
function computeTreemap(
  items: AssetAllocationItem[],
  width: number,
  height: number,
): TreemapRect[] {
  if (!items || items.length === 0 || width <= 0 || height <= 0) return [];

  const totalVol = items.reduce((sum, item) => sum + Math.max(item.traded_volume, 1), 0);
  const rects: TreemapRect[] = [];

  function layoutRow(
    rowItems: { item: AssetAllocationItem; area: number }[],
    x: number,
    y: number,
    w: number,
    h: number,
    isHoriz: boolean,
  ) {
    const rowArea = rowItems.reduce((acc, r) => acc + r.area, 0);
    if (rowArea <= 0) return;

    if (isHoriz) {
      const rowHeight = rowArea / (w || 1);
      let currX = x;
      for (const r of rowItems) {
        const itemW = r.area / (rowHeight || 1);
        rects.push({
          item: r.item,
          x: currX,
          y: y,
          w: Math.max(0, itemW),
          h: Math.max(0, rowHeight),
        });
        currX += itemW;
      }
    } else {
      const rowWidth = rowArea / (h || 1);
      let currY = y;
      for (const r of rowItems) {
        const itemH = r.area / (rowWidth || 1);
        rects.push({
          item: r.item,
          x: x,
          y: currY,
          w: Math.max(0, rowWidth),
          h: Math.max(0, itemH),
        });
        currY += itemH;
      }
    }
  }

  function squarify(
    remaining: { item: AssetAllocationItem; area: number }[],
    x: number,
    y: number,
    w: number,
    h: number,
  ) {
    if (remaining.length === 0 || w <= 0 || h <= 0) return;

    if (remaining.length === 1) {
      rects.push({
        item: remaining[0].item,
        x,
        y,
        w,
        h,
      });
      return;
    }

    const totalRemainingArea = remaining.reduce((acc, r) => acc + r.area, 0);
    const isHoriz = w >= h;

    let splitIndex = 1;
    let accumulatedArea = remaining[0].area;
    const halfArea = totalRemainingArea / 2;

    while (
      splitIndex < remaining.length &&
      Math.abs(accumulatedArea + remaining[splitIndex].area - halfArea) <
        Math.abs(accumulatedArea - halfArea)
    ) {
      accumulatedArea += remaining[splitIndex].area;
      splitIndex++;
    }

    const groupA = remaining.slice(0, splitIndex);
    const groupB = remaining.slice(splitIndex);

    const groupAArea = groupA.reduce((acc, r) => acc + r.area, 0);

    if (isHoriz) {
      const splitW = (groupAArea / (totalRemainingArea || 1)) * w;
      layoutRow(groupA, x, y, splitW, h, false);
      squarify(groupB, x + splitW, y, w - splitW, h);
    } else {
      const splitH = (groupAArea / (totalRemainingArea || 1)) * h;
      layoutRow(groupA, x, y, w, splitH, true);
      squarify(groupB, x, y + splitH, w, h - splitH);
    }
  }

  const totalPixelArea = width * height;
  const normalized = items.map((item) => ({
    item,
    area: (Math.max(item.traded_volume, 1) / totalVol) * totalPixelArea,
  }));

  squarify(normalized, 0, 0, width, height);
  return rects;
}

export function AssetAllocationTreemap({ runId }: { runId: string }) {
  const [hoveredSymbol, setHoveredSymbol] = useState<AssetAllocationItem | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["backtest-asset-allocation", runId],
    queryFn: () => fetchRunAssetAllocation(runId),
    enabled: Boolean(runId),
  });

  const width = 760;
  const height = 220;

  const rects = useMemo(() => {
    if (!data?.items) return [];
    return computeTreemap(data.items, width, height);
  }, [data?.items, width, height]);

  if (isLoading) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-[12px] text-ink-muted">
        Loading asset volume treemap…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-[12px] text-danger">
        {error ? (error as Error).message : "Failed to load asset volume breakdown"}
      </div>
    );
  }

  if (data.items.length === 0) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
        No symbol volume data available for this run.
      </div>
    );
  }

  return (
    <div className="rounded border border-line bg-surface p-3.5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Asset Traded Volume Treemap
          </h3>
          <p className="mt-0.5 text-[11px] text-ink-muted">
            Relative capital turnover and net PnL contribution across {data.symbol_count} traded symbols
          </p>
        </div>

        <div className="flex items-center gap-4 font-mono text-[11px]">
          <div>
            <span className="text-ink-faint">Total Volume: </span>
            <span className="font-semibold text-ink">
              ${data.total_volume >= 1e6 ? `${(data.total_volume / 1e6).toFixed(2)}M` : `${data.total_volume.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
            </span>
          </div>
          <div>
            <span className="text-ink-faint">Net PnL: </span>
            <span
              className={`font-semibold ${
                data.total_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {data.total_pnl >= 0 ? `+$${data.total_pnl.toFixed(0)}` : `-$${Math.abs(data.total_pnl).toFixed(0)}`}
            </span>
          </div>
        </div>
      </div>

      {/* SVG Treemap Canvas */}
      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full rounded border border-line/70 bg-surface-sunk overflow-hidden select-none"
          style={{ maxHeight: 240 }}
        >
          {rects.map((r) => {
            const isHovered = hoveredSymbol?.symbol === r.item.symbol;
            const isWin = r.item.realized_pnl >= 0;
            const pnlAbs = Math.abs(r.item.realized_pnl);

            // Color grading based on PnL
            const fillColor = isWin
              ? isHovered
                ? "#059669"
                : pnlAbs > 500
                  ? "#065f46"
                  : "#047857"
              : isHovered
                ? "#e11d48"
                : pnlAbs > 500
                  ? "#881337"
                  : "#9f1239";

            const showLabel = r.w >= 36 && r.h >= 24;
            const showSub = r.w >= 54 && r.h >= 42;

            return (
              <g
                key={r.item.symbol}
                onMouseEnter={() => setHoveredSymbol(r.item)}
                onMouseLeave={() => setHoveredSymbol(null)}
                className="cursor-pointer transition-all duration-150"
              >
                <rect
                  x={r.x + 0.5}
                  y={r.y + 0.5}
                  width={Math.max(0, r.w - 1)}
                  height={Math.max(0, r.h - 1)}
                  fill={fillColor}
                  stroke={isHovered ? "#38bdf8" : "#18181b"}
                  strokeWidth={isHovered ? "1.8" : "1"}
                  rx={2}
                />
                {showLabel ? (
                  <text
                    x={r.x + r.w / 2}
                    y={showSub ? r.y + r.h / 2 - 4 : r.y + r.h / 2 + 4}
                    textAnchor="middle"
                    fill="#ffffff"
                    fontSize={r.w < 60 ? "10" : "12"}
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    {r.item.symbol}
                  </text>
                ) : null}
                {showSub ? (
                  <text
                    x={r.x + r.w / 2}
                    y={r.y + r.h / 2 + 10}
                    textAnchor="middle"
                    fill="#e4e4e7"
                    fontSize="9.5"
                    fontFamily="monospace"
                  >
                    {r.item.volume_pct.toFixed(1)}%
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>

        {/* Hover Inspector Tooltip */}
        {hoveredSymbol ? (
          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded border border-line bg-surface-raised px-3 py-1.5 font-mono text-[11px]">
            <div className="flex items-center gap-2">
              <span className="font-bold text-ink">{hoveredSymbol.symbol}</span>
              <span className="text-ink-faint">·</span>
              <span className="text-ink-muted">
                Vol: ${hoveredSymbol.traded_volume.toLocaleString(undefined, { maximumFractionDigits: 0 })} ({hoveredSymbol.volume_pct.toFixed(1)}%)
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-ink-muted">
                Trades: {hoveredSymbol.total_trades} (Win: {hoveredSymbol.win_rate.toFixed(0)}%)
              </span>
              <span
                className={`font-semibold ${
                  hoveredSymbol.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                PnL: {hoveredSymbol.realized_pnl >= 0 ? `+$${hoveredSymbol.realized_pnl.toFixed(2)}` : `-$${Math.abs(hoveredSymbol.realized_pnl).toFixed(2)}`}
              </span>
            </div>
          </div>
        ) : (
          <div className="mt-2.5 text-center text-[10.5px] text-ink-faint">
            Hover over any asset rectangle to inspect traded volume share, win rate, and realized PnL.
          </div>
        )}
      </div>
    </div>
  );
}
