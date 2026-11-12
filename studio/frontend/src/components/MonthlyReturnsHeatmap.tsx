import { useMemo } from "react";
import type { MonthlyReturnsResponse } from "../types";

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function getCellColor(val: number | undefined): string {
  if (val == null) return "text-ink-faint/40 bg-surface/30";
  if (val >= 0.05) return "bg-emerald-500/25 text-emerald-300 font-bold";
  if (val >= 0.02) return "bg-emerald-500/18 text-emerald-300 font-medium";
  if (val > 0) return "bg-emerald-500/10 text-emerald-400";
  if (val <= -0.05) return "bg-rose-500/25 text-rose-300 font-bold";
  if (val <= -0.02) return "bg-rose-500/18 text-rose-300 font-medium";
  if (val < 0) return "bg-rose-500/10 text-rose-400";
  return "text-ink-muted bg-surface/40";
}

function formatCell(val: number | undefined): string {
  if (val == null) return "—";
  const pct = val * 100;
  const prefix = pct > 0 ? "+" : "";
  return `${prefix}${pct.toFixed(2)}%`;
}

export function MonthlyReturnsHeatmap({
  data,
  isLoading,
}: {
  data: MonthlyReturnsResponse | undefined;
  isLoading?: boolean;
}) {
  const years = useMemo(() => {
    if (!data?.years || data.years.length === 0) return [];
    return [...data.years].sort((a, b) => b - a); // Descending years
  }, [data]);

  if (isLoading) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
        Loading monthly returns…
      </div>
    );
  }

  if (!data || years.length === 0) {
    return (
      <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
        Monthly returns data unavailable for this run.
      </div>
    );
  }

  const winPct = (data.win_rate_months * 100).toFixed(1);

  return (
    <section className="mb-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
          Monthly Returns
        </h3>
        <span className="text-[11px] text-ink-muted">
          Profitable months:{" "}
          <span className="font-semibold text-emerald-400">
            {data.win_months} / {data.total_months} ({winPct}%)
          </span>
        </span>
      </div>

      <div className="mt-2 overflow-x-auto rounded border border-line bg-surface">
        <table className="w-full text-center text-[11px]">
          <thead className="border-b border-line bg-surface-sunk text-ink-faint">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium">Year</th>
              {MONTH_NAMES.map((m) => (
                <th key={m} className="px-1.5 py-1.5 font-medium">
                  {m}
                </th>
              ))}
              <th className="border-l border-line px-2 py-1.5 font-semibold text-ink">
                YTD
              </th>
            </tr>
          </thead>
          <tbody>
            {years.map((yr) => {
              const yrStr = String(yr);
              const months = data.matrix[yrStr] || {};
              const ytd = months["YTD"];
              return (
                <tr key={yr} className="border-t border-line/60 hover:bg-surface-sunk/40">
                  <td className="px-2 py-1 text-left font-mono font-medium text-ink">
                    {yr}
                  </td>
                  {MONTH_NAMES.map((_, idx) => {
                    const moKey = String(idx + 1);
                    const val = months[moKey];
                    return (
                      <td
                        key={idx}
                        className={`px-1 py-1 font-mono text-[10.5px] tabular-nums transition-colors ${getCellColor(
                          val,
                        )}`}
                        title={val != null ? `${MONTH_NAMES[idx]} ${yr}: ${formatCell(val)}` : undefined}
                      >
                        {formatCell(val)}
                      </td>
                    );
                  })}
                  <td
                    className={`border-l border-line px-2 py-1 font-mono text-[11px] font-bold tabular-nums ${getCellColor(
                      ytd,
                    )}`}
                    title={`Year ${yr} Total: ${formatCell(ytd)}`}
                  >
                    {formatCell(ytd)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
