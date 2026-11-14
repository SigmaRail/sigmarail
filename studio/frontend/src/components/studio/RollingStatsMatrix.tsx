import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchRunRollingStats } from "../../api/backtests";

type MetricKey = "sharpe" | "win_rate" | "volatility" | "beta";

const METRICS: Array<{ key: MetricKey; label: string; suffix: string; color: string }> = [
  { key: "sharpe", label: "Rolling Sharpe Ratio", suffix: "", color: "#10b981" },
  { key: "win_rate", label: "Rolling Win Rate", suffix: "%", color: "#38bdf8" },
  { key: "volatility", label: "Rolling Volatility (Ann.)", suffix: "%", color: "#fbbf24" },
  { key: "beta", label: "Rolling Market Beta (vs SPY)", suffix: "", color: "#a855f7" },
];

export function RollingStatsMatrix({ runId }: { runId: string }) {
  const [selectedMetric, setSelectedMetric] = useState<MetricKey>("sharpe");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["backtest-rolling-stats", runId],
    queryFn: () => fetchRunRollingStats(runId),
    enabled: Boolean(runId),
  });

  const matrix = data?.summary_matrix;
  const series = data?.rolling_series ?? [];

  const currentMetric = METRICS.find((m) => m.key === selectedMetric) || METRICS[0];

  // Mini sparkline data for 1M window
  const sparklineData = useMemo(() => {
    const key = `${selectedMetric}_1M`;
    const pts = series
      .map((p) => {
        const val = p[key];
        return typeof val === "number" ? val : null;
      })
      .filter((v): v is number => v !== null);

    if (pts.length < 2) return null;

    const min = Math.min(...pts);
    const max = Math.max(...pts);
    const range = max - min || 1;

    const w = 320;
    const h = 50;
    const pad = 4;

    const points = pts
      .map((val, i) => {
        const x = pad + (i / (pts.length - 1)) * (w - pad * 2);
        const y = h - pad - ((val - min) / range) * (h - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    return { points, min, max, count: pts.length };
  }, [series, selectedMetric]);

  if (isLoading) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-[12px] text-ink-muted">
        Loading rolling performance statistics…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-[12px] text-danger">
        {error ? (error as Error).message : "Failed to load rolling statistics"}
      </div>
    );
  }

  return (
    <div className="rounded border border-line bg-surface p-3.5">
      {/* Header & Metric Dropdown */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Rolling Statistics Matrix
          </h3>
          <p className="mt-0.5 text-[11px] text-ink-muted">
            QuantConnect-style multi-horizon sliding windows (1M, 3M, 6M)
          </p>
        </div>

        {/* Metric Switcher */}
        <select
          value={selectedMetric}
          onChange={(e) => setSelectedMetric(e.target.value as MetricKey)}
          className="rounded border border-line bg-surface-raised px-2.5 py-1 text-[11px] font-semibold text-ink shadow-xs focus:border-accent focus:outline-none"
        >
          {METRICS.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {/* Main Grid: Matrix Table on Left, Sparkline on Right */}
      <div className="mt-3 grid gap-3 lg:grid-cols-12 items-center">
        {/* Rolling Horizon Table (7 cols) */}
        <div className="lg:col-span-7 overflow-x-auto">
          <table className="w-full text-left font-mono text-[11px]">
            <thead>
              <tr className="border-b border-line/60 text-ink-faint text-[10px] uppercase">
                <th className="pb-1.5 font-medium">Metric</th>
                <th className="pb-1.5 text-center font-medium">1 Month (21d)</th>
                <th className="pb-1.5 text-center font-medium">3 Months (63d)</th>
                <th className="pb-1.5 text-center font-medium">6 Months (126d)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/30">
              {METRICS.map((m) => {
                const row = matrix ? matrix[m.key] : null;
                const isSelected = m.key === selectedMetric;
                return (
                  <tr
                    key={m.key}
                    onClick={() => setSelectedMetric(m.key)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? "bg-accent/10 font-bold" : "hover:bg-surface-sunk/60"
                    }`}
                  >
                    <td className="py-2 text-ink flex items-center gap-1.5">
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: m.color }}
                      />
                      <span>{m.label}</span>
                    </td>
                    <td className="py-2 text-center text-ink">
                      {row ? String(row["1M"] ?? "—") : "—"}
                    </td>
                    <td className="py-2 text-center text-ink-muted">
                      {row ? String(row["3M"] ?? "—") : "—"}
                    </td>
                    <td className="py-2 text-center text-ink-muted">
                      {row ? String(row["6M"] ?? "—") : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Rolling Sparkline Visualizer (5 cols) */}
        <div className="lg:col-span-5 rounded border border-line/70 bg-surface-sunk p-2.5">
          <div className="flex items-center justify-between text-[10px] font-mono text-ink-faint">
            <span className="font-semibold text-ink">{currentMetric.label} (1M Trend)</span>
            {sparklineData ? (
              <span>
                Range: {sparklineData.min.toFixed(1)} → {sparklineData.max.toFixed(1)}
              </span>
            ) : null}
          </div>

          <div className="mt-1.5">
            {sparklineData ? (
              <svg viewBox="0 0 320 50" className="w-full overflow-visible">
                <polyline
                  points={sparklineData.points}
                  fill="none"
                  stroke={currentMetric.color}
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            ) : (
              <div className="flex h-12 items-center justify-center text-[10.5px] text-ink-faint">
                Trendline requires multiple rolling periods
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
