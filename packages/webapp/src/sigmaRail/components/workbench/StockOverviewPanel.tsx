import { useId } from "react";
import type { AnnualGrowthPoint, StockIntrospectionData } from "../../types";
import { cn } from "../../lib/utils";
import { BookmarkButton } from "./BookmarkButton";

function valueOf(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

function pct(value: number | null): string {
  if (value === null) return "—";
  const normalized = Math.abs(value) <= 1.5 ? value * 100 : value;
  return `${normalized > 0 ? "+" : ""}${normalized.toFixed(1)}%`;
}

function pctChange(value: number | null): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatVolume(value: number | null): string {
  if (value === null) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}

function formatMarketCap(value: number | null): string {
  if (value === null || value === 0) return "—";
  if (Math.abs(value) >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${value.toFixed(0)}`;
}

function changePct(value: number | null): string {
  if (value === null) return "—";
  const normalized = Math.abs(value) <= 1.5 ? value * 100 : value;
  return `${normalized > 0 ? "+" : ""}${normalized.toFixed(1)}%`;
}

function plainPct(value: number | null): string {
  if (value === null) return "—";
  const normalized = Math.abs(value) <= 1.5 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function shortSales(value: number | null): string {
  if (value === null) return "—";
  return Math.abs(value) >= 1000 ? `$${(value / 1000).toFixed(1)}B` : `$${value.toFixed(0)}M`;
}

function metric(label: string, value: string) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 border-b border-line/60 py-2 last:border-0">
      <span className="min-w-0 text-ink-muted">{label}</span>
      <span className="shrink-0 font-semibold tabular-nums text-ink">{value}</span>
    </div>
  );
}

function growthClass(value: number | null | undefined): string {
  return value == null ? "text-ink-muted" : value > 0 ? "text-emerald-500" : value < 0 ? "text-rose-500" : "text-ink";
}

export function StockOverviewPanel({
  ticker,
  data,
  showYearlyEarnings = true,
}: {
  ticker?: string;
  data?: StockIntrospectionData | null;
  showYearlyEarnings?: boolean;
}) {
  const headingId = useId();
  const kpis = (data?.as_of_kpis ?? {}) as Record<string, unknown>;
  const symbol = ticker || data?.ticker || "";
  const close = valueOf(kpis, "close");
  const change = valueOf(kpis, "perf_5d");
  const high52w = valueOf(kpis, "high_52w");
  const off52wHigh = close !== null && high52w !== null && high52w > 0
    ? -((1 - close / high52w) * 100)
    : null;
  const annual: AnnualGrowthPoint[] = [...(data?.annual_growth ?? [])].sort((a, b) =>
    String(b.year).localeCompare(String(a.year)),
  );
  const fundamentals = [
    ["TTM EPS", valueOf(kpis, "mrt_epsdil") == null ? "—" : `$${valueOf(kpis, "mrt_epsdil")!.toFixed(2)}`],
    ["ROE", pct(valueOf(kpis, "mrt_roe"))],
    ["ROIC", pct(valueOf(kpis, "mrt_roic"))],
    ["Net margin", pct(valueOf(kpis, "mrt_netmargin"))],
    ["Gross margin", pct(valueOf(kpis, "mrt_grossmargin"))],
    ["Debt / equity", valueOf(kpis, "mrq_de")?.toFixed(2) ?? "—"],
    ["P/E", valueOf(kpis, "pe")?.toFixed(1) ?? "—"],
    ["P/S", valueOf(kpis, "ps")?.toFixed(1) ?? "—"],
  ] as const;

  return (
    <aside className="stock-overview-container min-w-0 border-y border-line bg-surface text-xs font-mono">
      <section aria-labelledby={`${headingId}-overview`} className="px-3 py-3 sm:px-4">
        <h2 id={`${headingId}-overview`} className="mb-3 text-sm font-bold text-ink">Overview</h2>
        <div className="stock-overview-grid min-w-0 gap-x-6 gap-y-4">
          <div className="min-w-0">
            <div className="mb-1 flex min-w-0 items-center justify-between gap-2">
              <h3 className="truncate text-[10px] font-semibold uppercase tracking-wide text-ink-muted">Trading</h3>
              {symbol ? <BookmarkButton ticker={symbol} /> : null}
            </div>
            <div className="min-w-0">
              {metric("Price", close === null ? "—" : `$${close.toFixed(2)}`)}
              <div className={change === null ? "" : change > 0 ? "text-emerald-500" : change < 0 ? "text-rose-500" : ""}>
                {metric("5-day change", changePct(change))}
              </div>
              {metric("Avg volume (50d)", formatVolume(valueOf(kpis, "avg_vol_50d")))}
              {metric("Market cap", formatMarketCap(valueOf(kpis, "marketcap")))}
              <div className={off52wHigh === null ? "" : off52wHigh < 0 ? "text-rose-500" : "text-emerald-500"}>
                {metric("From 52-week high", changePct(off52wHigh))}
              </div>
              {metric("ATR", plainPct(valueOf(kpis, "atr_14_pct")))}
            </div>
          </div>
          <div>
            <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">Ratings</h3>
            <div className="min-w-0">
              {metric("RS", valueOf(kpis, "rs_rating")?.toFixed(0) ?? "—")}
              {metric("Technical", valueOf(kpis, "technical_rating")?.toFixed(0) ?? "—")}
              {metric("Setup", valueOf(kpis, "setup_quality_rating")?.toFixed(0) ?? "—")}
              {metric("Growth", valueOf(kpis, "growth_rating")?.toFixed(0) ?? "—")}
              {metric("Overall", valueOf(kpis, "overall_score")?.toFixed(0) ?? "—")}
              {metric("EPS surprise", pct(valueOf(kpis, "eps_last_surprise_pct_display") ?? valueOf(kpis, "eps_last_surprise_pct")))}
            </div>
          </div>
          <div>
            <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">Company metrics</h3>
            <div className="min-w-0">
              {fundamentals.map(([label, value]) => <div key={label}>{metric(label, value)}</div>)}
            </div>
          </div>
        </div>
      </section>

      {showYearlyEarnings ? <section aria-labelledby={`${headingId}-yearly`} className="border-t border-line px-3 py-3 sm:px-4">
        <h2 id={`${headingId}-yearly`} className="mb-1.5 text-xs font-bold text-ink">Yearly earnings</h2>
        {annual.length === 0 ? (
          <p className="py-2 text-ink-muted">No annual series</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[280px] text-right tabular-nums">
              <thead className="text-[9px] uppercase text-ink-muted">
                <tr>
                  <th className="py-1 text-left font-medium">Year</th>
                  <th className="px-1 py-1 font-medium">EPS</th>
                  <th className="px-1 py-1 font-medium">EPS %</th>
                  <th className="px-1 py-1 font-medium">Sales</th>
                  <th className="py-1 font-medium">Sales %</th>
                </tr>
              </thead>
              <tbody>
                {annual.map((row) => (
                  <tr key={row.year} className="border-t border-line/60">
                    <th scope="row" className="py-1 text-left font-medium text-ink">
                      {String(row.year).replace(/e$/i, "")}{row.is_estimate ? "e" : ""}
                    </th>
                    <td className="px-1 py-1 text-ink">{row.eps?.toFixed(2) ?? "—"}</td>
                    <td className={cn("px-1 py-1", growthClass(row.eps_chg_pct))}>{pctChange(row.eps_chg_pct)}</td>
                    <td className="px-1 py-1 text-ink">{shortSales(row.sales_m)}</td>
                    <td className={cn("py-1", growthClass(row.sales_chg_pct))}>{pctChange(row.sales_chg_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section> : null}
    </aside>
  );
}
