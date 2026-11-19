import type { ChartCandlePoint } from "../../types";
import { stockPath } from "../../routes";

type WeeklyClose = { week: string; close: number };

function weekStart(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() - day + 1);
  return date.toISOString().slice(0, 10);
}

function weeklyCloses(candles: ChartCandlePoint[], asOfDate: string): WeeklyClose[] {
  const byWeek = new Map<string, number>();
  for (const candle of [...candles].sort((a, b) => a.time.localeCompare(b.time))) {
    const date = candle.time.slice(0, 10);
    if (date <= asOfDate && Number.isFinite(candle.close) && candle.close > 0) {
      byWeek.set(weekStart(date), candle.close);
    }
  }
  return [...byWeek.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-52)
    .map(([week, close]) => ({ week, close }));
}

function percent(current: number, prior: number | undefined): string {
  if (!prior || prior <= 0) return "—";
  const value = ((current / prior) - 1) * 100;
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function returnClass(value: string): string {
  if (value.startsWith("+")) return "text-emerald-500";
  if (value.startsWith("-")) return "text-rose-500";
  return "text-ink-muted";
}

export function WeeklyPriceChart({
  ticker,
  asOfDate,
  candles,
}: {
  ticker: string;
  asOfDate: string;
  candles: ChartCandlePoint[];
}) {
  const points = weeklyCloses(candles, asOfDate);
  const values = points.map((point) => point.close);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const range = max - min || Math.max(max * 0.05, 1);
  const coords = values.map((value, index) => {
    const x = points.length <= 1 ? 0 : (index / (points.length - 1)) * 1000;
    const y = 170 - ((value - min) / range) * 150;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = values.at(-1);
  const findPrior = (days: number) => {
    const target = new Date(`${asOfDate}T00:00:00Z`);
    target.setUTCDate(target.getUTCDate() - days);
    const targetDate = target.toISOString().slice(0, 10);
    return [...candles]
      .filter((candle) => candle.time.slice(0, 10) <= targetDate)
      .sort((a, b) => b.time.localeCompare(a.time))[0]?.close;
  };
  const yearStart = `${asOfDate.slice(0, 4)}-01-01`;
  const ytdPrior = [...candles]
    .filter((candle) => candle.time.slice(0, 10) < yearStart)
    .sort((a, b) => b.time.localeCompare(a.time))[0]?.close;
  const returns = [
    ["1W", findPrior(7)],
    ["1M", findPrior(30)],
    ["3M", findPrior(91)],
    ["6M", findPrior(182)],
    ["YTD", ytdPrior],
    ["1Y", findPrior(365)],
  ] as const;
  const chartHref = `${stockPath(ticker)}?as_of=${encodeURIComponent(asOfDate)}`;

  return (
    <section className="min-w-0 border-b border-line bg-surface px-3 py-3 sm:px-4" aria-label={`${ticker} 52-week price chart`}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xs font-semibold text-ink">Price · weekly closes</h2>
          <p className="text-[10px] text-ink-muted">52 available weeks through {asOfDate}</p>
        </div>
        <a href={chartHref} className="shrink-0 rounded border border-line px-2.5 py-1.5 text-[10px] font-semibold text-ink hover:bg-surface-raised">
          Full chart <span aria-hidden="true">↗</span>
        </a>
      </div>
      {points.length < 2 ? (
        <div className="flex h-32 items-center justify-center text-xs text-ink-muted">Not enough weekly price history</div>
      ) : (
        <svg viewBox="0 0 1000 190" role="img" aria-label={`${ticker} weekly closing prices`} className="block h-32 w-full overflow-visible sm:h-40">
          <line x1="0" x2="1000" y1="20" y2="20" stroke="currentColor" opacity="0.12" />
          <line x1="0" x2="1000" y1="95" y2="95" stroke="currentColor" opacity="0.12" />
          <line x1="0" x2="1000" y1="170" y2="170" stroke="currentColor" opacity="0.18" />
          <polyline points={coords.join(" ")} fill="none" stroke="currentColor" strokeWidth="3" vectorEffect="non-scaling-stroke" className={last !== undefined && values[0] !== undefined && last >= values[0] ? "text-emerald-500" : "text-rose-500"} />
          <text x="0" y="187" fill="currentColor" opacity="0.55" fontSize="22">{points[0]?.week.slice(0, 7)}</text>
          <text x="1000" y="187" fill="currentColor" opacity="0.55" fontSize="22" textAnchor="end">{points.at(-1)?.week.slice(0, 7)}</text>
        </svg>
      )}
      <div className="grid grid-cols-3 gap-2 border-t border-line/60 pt-2 sm:grid-cols-6">
        {returns.map(([label, prior]) => {
          const value = last === undefined ? "—" : percent(last, prior);
          return <div key={label} className="text-center">
            <div className="text-[9px] text-ink-muted">{label}</div>
            <div className={`font-mono text-[11px] font-semibold tabular-nums ${returnClass(value)}`}>{value}</div>
          </div>;
        })}
      </div>
    </section>
  );
}
