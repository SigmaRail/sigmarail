import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTickerCandles } from "../../api/backtests";

function addDays(isoDate: string, days: number): string {
  try {
    const d = new Date(isoDate);
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  } catch {
    return isoDate;
  }
}

// Simple moving average calculation
function calculateSMA(candles: { close: number }[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) {
        sum += candles[j].close;
      }
      result.push(sum / period);
    }
  }
  return result;
}

export function VeraCandidateChart({
  ticker,
  asOfDate,
  height = 360,
}: {
  ticker: string;
  asOfDate?: string;
  height?: number;
}) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [lookbackDays, setLookbackDays] = useState<number>(120);

  const anchorDate = asOfDate || new Date().toISOString().slice(0, 10);
  const startDate = useMemo(() => addDays(anchorDate, -lookbackDays), [anchorDate, lookbackDays]);
  const endDate = useMemo(() => addDays(anchorDate, 20), [anchorDate]);

  const candlesQuery = useQuery({
    queryKey: ["candidate-candles", ticker, startDate, endDate],
    queryFn: () => fetchTickerCandles(ticker, startDate, endDate),
    enabled: Boolean(ticker),
  });

  const candles = candlesQuery.data?.candles ?? [];
  const meta = candlesQuery.data?.meta;

  // Moving averages
  const sma20 = useMemo(() => calculateSMA(candles, 20), [candles]);
  const sma50 = useMemo(() => calculateSMA(candles, 50), [candles]);

  const chartMetrics = useMemo(() => {
    if (candles.length === 0) return null;

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVolume = 0;

    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (c.volume > maxVolume) maxVolume = c.volume;

      const s20 = sma20[i];
      if (s20 !== null) {
        if (s20 < minPrice) minPrice = s20;
        if (s20 > maxPrice) maxPrice = s20;
      }
      const s50 = sma50[i];
      if (s50 !== null) {
        if (s50 < minPrice) minPrice = s50;
        if (s50 > maxPrice) maxPrice = s50;
      }
    }

    const pricePadding = (maxPrice - minPrice) * 0.08 || 1.0;
    minPrice -= pricePadding;
    maxPrice += pricePadding;

    const width = 800;
    const priceHeight = Math.max(160, height - 120);
    const volumeHeight = 50;
    const padding = { top: 15, right: 65, bottom: 25, left: 10 };

    const chartWidth = width - padding.left - padding.right;
    const slotWidth = chartWidth / candles.length;
    const candleWidth = Math.max(3, Math.min(12, slotWidth * 0.7));

    const scaleY = (p: number) =>
      padding.top +
      priceHeight -
      ((p - minPrice) / (maxPrice - minPrice)) * priceHeight;

    const scaleVol = (v: number) =>
      maxVolume > 0 ? (v / maxVolume) * volumeHeight : 0;

    // Locate anchor asOfDate index
    let asOfIdx = -1;
    for (let i = candles.length - 1; i >= 0; i--) {
      if (candles[i].date <= anchorDate) {
        asOfIdx = i;
        break;
      }
    }

    return {
      width,
      height,
      priceHeight,
      volumeHeight,
      padding,
      minPrice,
      maxPrice,
      maxVolume,
      slotWidth,
      candleWidth,
      scaleY,
      scaleVol,
      asOfIdx,
    };
  }, [candles, sma20, sma50, height, anchorDate]);

  const activeIndex = hoverIndex !== null ? hoverIndex : chartMetrics?.asOfIdx ?? (candles.length - 1);
  const activeCandle = candles[activeIndex] || null;

  if (!ticker) {
    return (
      <div className="flex h-full items-center justify-center text-[12px] text-ink-muted">
        Select a ticker to preview chart.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-surface overflow-hidden">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-raised px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[14px] font-bold text-ink">{ticker}</span>
          {meta?.name ? (
            <span className="text-[11px] text-ink-muted truncate max-w-[200px]">
              {meta.name}
            </span>
          ) : null}
          <div className="flex items-center gap-2 pl-2 text-[10.5px]">
            <span className="flex items-center gap-1 font-mono text-sky-400">
              <span className="inline-block h-1.5 w-3 rounded bg-sky-400"></span> 20 SMA
            </span>
            <span className="flex items-center gap-1 font-mono text-amber-400">
              <span className="inline-block h-1.5 w-3 rounded bg-amber-400"></span> 50 SMA
            </span>
          </div>
        </div>

        {/* Lookback Filter Tabs */}
        <div className="flex items-center gap-1 text-[10px]">
          {[
            { label: "1M", days: 30 },
            { label: "3M", days: 90 },
            { label: "6M", days: 180 },
            { label: "1Y", days: 365 },
          ].map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => setLookbackDays(item.days)}
              className={`rounded px-2 py-0.5 font-medium transition-colors ${
                lookbackDays === item.days
                  ? "bg-accent text-accent-ink font-semibold"
                  : "bg-surface-sunk text-ink-muted hover:text-ink"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Active Candle Metrics Bar */}
      {activeCandle ? (
        <div className="flex flex-wrap items-center gap-3 border-b border-line/60 bg-surface-sunk/60 px-3.5 py-1.5 font-mono text-[10.5px] text-ink-muted">
          <span className="font-bold text-ink">{activeCandle.date}</span>
          <span>O: <strong className="text-ink">${activeCandle.open.toFixed(2)}</strong></span>
          <span>H: <strong className="text-ink">${activeCandle.high.toFixed(2)}</strong></span>
          <span>L: <strong className="text-ink">${activeCandle.low.toFixed(2)}</strong></span>
          <span>C: <strong className="text-ink">${activeCandle.close.toFixed(2)}</strong></span>
          <span>Vol: <strong className="text-ink">{activeCandle.volume.toLocaleString()}</strong></span>
          <span
            className={`font-semibold ${
              activeCandle.close >= activeCandle.open ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {activeCandle.close >= activeCandle.open ? "+" : ""}
            {(((activeCandle.close - activeCandle.open) / activeCandle.open) * 100).toFixed(2)}%
          </span>
          {chartMetrics && chartMetrics.asOfIdx === activeIndex ? (
            <span className="rounded bg-accent/20 px-1.5 py-0.2 text-[9.5px] font-bold text-accent">
              📍 Replay Date
            </span>
          ) : null}
        </div>
      ) : null}

      {/* SVG Canvas Area */}
      <div className="flex-1 overflow-hidden p-2">
        {candlesQuery.isLoading ? (
          <div className="flex h-full items-center justify-center text-[12px] text-ink-muted">
            Loading market candles from ClickHouse <code className="font-mono ml-1">vera.sep</code>…
          </div>
        ) : candlesQuery.isError ? (
          <div className="flex h-full items-center justify-center text-[12px] text-danger">
            {(candlesQuery.error as Error).message}
          </div>
        ) : !chartMetrics || candles.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[12px] text-ink-muted">
            No historical candles found for {ticker}.
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${chartMetrics.width} ${chartMetrics.height}`}
            className="w-full h-full select-none"
            onMouseLeave={() => setHoverIndex(null)}
          >
            {/* Horizontal Grid lines & Price Labels */}
            {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
              const y = chartMetrics.padding.top + ratio * chartMetrics.priceHeight;
              const price = chartMetrics.maxPrice - ratio * (chartMetrics.maxPrice - chartMetrics.minPrice);
              return (
                <g key={ratio}>
                  <line
                    x1={chartMetrics.padding.left}
                    y1={y}
                    x2={chartMetrics.width - chartMetrics.padding.right}
                    y2={y}
                    stroke="#27272a"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                  <text
                    x={chartMetrics.width - chartMetrics.padding.right + 6}
                    y={y + 3}
                    fill="#71717a"
                    fontSize="9.5"
                    fontFamily="monospace"
                  >
                    ${price.toFixed(2)}
                  </text>
                </g>
              );
            })}

            {/* As-Of Date Vertical Cursor & Highlight */}
            {chartMetrics.asOfIdx >= 0 ? (
              (() => {
                const x =
                  chartMetrics.padding.left +
                  chartMetrics.asOfIdx * chartMetrics.slotWidth +
                  chartMetrics.slotWidth / 2;
                return (
                  <g>
                    <line
                      x1={x}
                      y1={chartMetrics.padding.top}
                      x2={x}
                      y2={chartMetrics.padding.top + chartMetrics.priceHeight + chartMetrics.volumeHeight + 15}
                      stroke="#38bdf8"
                      strokeWidth="1.5"
                      strokeDasharray="4 2"
                    />
                    <rect
                      x={x - 30}
                      y={chartMetrics.padding.top - 12}
                      width="60"
                      height="12"
                      rx="2"
                      fill="#0284c7"
                    />
                    <text
                      x={x}
                      y={chartMetrics.padding.top - 3}
                      textAnchor="middle"
                      fill="#ffffff"
                      fontSize="8"
                      fontWeight="bold"
                      fontFamily="monospace"
                    >
                      AS-OF DATE
                    </text>
                  </g>
                );
              })()
            ) : null}

            {/* Candlesticks & Volume Bars */}
            {candles.map((c, i) => {
              const isBull = c.close >= c.open;
              const color = isBull ? "#10b981" : "#f43f5e";
              const xCenter =
                chartMetrics.padding.left +
                i * chartMetrics.slotWidth +
                chartMetrics.slotWidth / 2;
              const xBox = xCenter - chartMetrics.candleWidth / 2;

              const yHigh = chartMetrics.scaleY(c.high);
              const yLow = chartMetrics.scaleY(c.low);
              const yOpen = chartMetrics.scaleY(c.open);
              const yClose = chartMetrics.scaleY(c.close);

              const boxTop = Math.min(yOpen, yClose);
              const boxHeight = Math.max(1.5, Math.abs(yClose - yOpen));

              // Volume bar
              const volHeight = chartMetrics.scaleVol(c.volume);
              const volY =
                chartMetrics.padding.top +
                chartMetrics.priceHeight +
                15 +
                (chartMetrics.volumeHeight - volHeight);

              return (
                <g
                  key={c.date}
                  onMouseEnter={() => setHoverIndex(i)}
                  className="cursor-pointer"
                >
                  {/* Hover column background highlight */}
                  {hoverIndex === i ? (
                    <rect
                      x={xCenter - chartMetrics.slotWidth / 2}
                      y={chartMetrics.padding.top}
                      width={chartMetrics.slotWidth}
                      height={chartMetrics.priceHeight + chartMetrics.volumeHeight + 15}
                      fill="#ffffff"
                      opacity="0.05"
                    />
                  ) : null}

                  {/* Wick */}
                  <line
                    x1={xCenter}
                    y1={yHigh}
                    x2={xCenter}
                    y2={yLow}
                    stroke={color}
                    strokeWidth="1.2"
                  />

                  {/* Body */}
                  <rect
                    x={xBox}
                    y={boxTop}
                    width={chartMetrics.candleWidth}
                    height={boxHeight}
                    fill={color}
                    rx="1"
                  />

                  {/* Volume bar */}
                  <rect
                    x={xBox}
                    y={volY}
                    width={chartMetrics.candleWidth}
                    height={volHeight}
                    fill={color}
                    opacity="0.45"
                  />
                </g>
              );
            })}

            {/* SMA 20 Polyline (Sky Blue) */}
            {(() => {
              const points: string[] = [];
              for (let i = 0; i < sma20.length; i++) {
                const val = sma20[i];
                if (val !== null) {
                  const x =
                    chartMetrics.padding.left +
                    i * chartMetrics.slotWidth +
                    chartMetrics.slotWidth / 2;
                  const y = chartMetrics.scaleY(val);
                  points.push(`${x},${y}`);
                }
              }
              return points.length > 1 ? (
                <polyline
                  points={points.join(" ")}
                  fill="none"
                  stroke="#38bdf8"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              ) : null;
            })()}

            {/* SMA 50 Polyline (Amber) */}
            {(() => {
              const points: string[] = [];
              for (let i = 0; i < sma50.length; i++) {
                const val = sma50[i];
                if (val !== null) {
                  const x =
                    chartMetrics.padding.left +
                    i * chartMetrics.slotWidth +
                    chartMetrics.slotWidth / 2;
                  const y = chartMetrics.scaleY(val);
                  points.push(`${x},${y}`);
                }
              }
              return points.length > 1 ? (
                <polyline
                  points={points.join(" ")}
                  fill="none"
                  stroke="#fbbf24"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              ) : null;
            })()}

            {/* Volume Separator */}
            <line
              x1={chartMetrics.padding.left}
              y1={chartMetrics.padding.top + chartMetrics.priceHeight + 10}
              x2={chartMetrics.width - chartMetrics.padding.right}
              y2={chartMetrics.padding.top + chartMetrics.priceHeight + 10}
              stroke="#27272a"
              strokeWidth="1"
            />
          </svg>
        )}
      </div>
    </div>
  );
}
