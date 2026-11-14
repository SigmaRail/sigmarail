import type { AnnualGrowthPoint, StockIntrospectionData } from "../../types";
import { cn } from "../../lib/utils";

interface FundamentalsRailProps {
  data?: StockIntrospectionData | null;
  open: boolean;
  onToggle: () => void;
  onSelectTicker?: (ticker: string) => void;
  onOpenForecastModal?: () => void;
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function asPct(value: unknown): number | null {
  const n = num(value);
  if (n === null) return null;
  return Math.abs(n) <= 1.5 ? n * 100 : n;
}

function formatNum(value: number | null, digits = 1): string {
  if (value === null) return "—";
  return value.toFixed(digits);
}

function formatSalesShort(val: number | null): string {
  if (val === null) return "—";
  if (Math.abs(val) >= 1000) return `$${(val / 1000).toFixed(1)}B`;
  return `$${val.toFixed(0)}M`;
}

function formatSignedPct(value: number | null, digits = 1): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function chgClass(value: number | null): string {
  if (value === null) return "text-ink";
  if (value > 0) return "text-emerald-500";
  if (value < 0) return "text-rose-500";
  return "text-ink";
}

function kpiNum(kpis: Record<string, unknown>, key: string): number | null {
  return num(kpis[key]);
}

function ratingRow(label: string, value: number | null, suffix = "") {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-ink-muted">{label}</span>
      <span className="font-bold text-ink">
        {value === null ? "—" : `${Math.round(value)}${suffix}`}
      </span>
    </div>
  );
}

function fundRow(label: string, value: string, valueClass?: string) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-ink-muted">{label}</span>
      <span className={cn("font-bold", valueClass ?? "text-ink")}>{value}</span>
    </div>
  );
}

export function FundamentalsRail({
  data,
  open,
  onToggle,
  onSelectTicker,
  onOpenForecastModal,
}: FundamentalsRailProps) {
  const kpis = (data?.as_of_kpis ?? {}) as Record<string, unknown>;
  const annual: AnnualGrowthPoint[] = data?.annual_growth ?? [];
  const peers = [...(data?.industry_peers ?? [])].sort(
    (a, b) => (b.rs_rating ?? 0) - (a.rs_rating ?? 0),
  );

  const surprise = num(kpis.eps_last_surprise_pct_display) ?? asPct(kpis.eps_last_surprise_pct);
  // Prefer clamped *_display fields only — null means hide (do not fall back to raw)
  const cyRev = num(kpis.eps_cy_rev_pct_90d_display);
  const nyRev = num(kpis.eps_ny_rev_pct_90d_display);
  const salesNyRev = num(kpis.sales_ny_rev_pct_90d_display);

  // Latest Reported vs Consensus Estimates & Beat/Miss Flags
  const epsBeatFlag = num(kpis.eps_beat_flag);
  const epsAct = num(kpis.eps_last_reported);
  const epsEst = num(kpis.eps_last_estimate);
  const salesBeatFlag = num(kpis.sales_beat_flag);
  const salesAct = num(kpis.sales_last_reported);
  const salesEst = num(kpis.sales_last_estimate);
  const salesSurprise = num(kpis.sales_last_surprise_pct);

  // Fallback to quarterly series if L7 screener row hasn't been backfilled yet
  const lastQuarter = [...(data?.quarterly_growth ?? [])]
    .filter((q) => !q.is_estimate && (q.eps_actual != null || q.eps != null))
    .sort((a, b) => (b.report_date || "").localeCompare(a.report_date || ""))[0];

  const resolvedEpsAct = epsAct ?? lastQuarter?.eps_actual ?? lastQuarter?.eps ?? null;
  const resolvedEpsEst = epsEst ?? lastQuarter?.eps_estimate ?? null;
  const resolvedEpsBeatFlag =
    epsBeatFlag ??
    (lastQuarter?.eps_beat_miss === "beat"
      ? 1
      : lastQuarter?.eps_beat_miss === "miss"
      ? 0
      : null);

  const resolvedSalesAct =
    salesAct ?? lastQuarter?.revenue_actual ?? lastQuarter?.revenue_m ?? null;
  const resolvedSalesEst = salesEst ?? lastQuarter?.revenue_estimate ?? null;
  const resolvedSalesBeatFlag =
    salesBeatFlag ??
    (lastQuarter?.revenue_beat_miss === "beat"
      ? 1
      : lastQuarter?.revenue_beat_miss === "miss"
      ? 0
      : null);
  const resolvedSalesSurprise = salesSurprise ?? lastQuarter?.revenue_surprise_pct ?? null;

  const roe = asPct(kpis.mrt_roe);
  const roic = asPct(kpis.mrt_roic);
  const netMgn = asPct(kpis.mrt_netmargin);
  const grossMgn = asPct(kpis.mrt_grossmargin);

  if (!open) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="flex w-7 flex-shrink-0 flex-col items-center border-r border-line bg-surface-raised py-2 text-[10px] font-mono font-bold text-ink-muted hover:bg-surface-sunk hover:text-accent"
        title="Open fundamentals rail"
      >
        <span>›</span>
        <span className="mt-2 [writing-mode:vertical-rl] rotate-180 tracking-widest">FUND</span>
      </button>
    );
  }

  return (
    <aside className="flex w-60 flex-shrink-0 flex-col overflow-hidden border-r border-line bg-surface text-[11px] font-mono">
      <div className="flex items-center justify-between border-b border-line bg-surface-raised px-2 py-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-accent">Fundamentals</span>
        <div className="flex items-center gap-1.5">
          {onOpenForecastModal && (
            <button
              type="button"
              onClick={onOpenForecastModal}
              className="rounded border border-accent/40 bg-accent/10 px-1 py-0.5 text-[8.5px] font-bold text-accent hover:bg-accent/20 transition-colors"
              title="Open Forecasts & Accuracy Chart"
            >
              📊 Accuracy
            </button>
          )}
          <button
            type="button"
            onClick={onToggle}
            className="rounded px-1 text-ink-muted hover:text-ink"
            title="Collapse fundamentals rail"
          >
            ‹
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-2 py-2">
        <section>
          <div className="mb-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
            Annual EPS / Sales
          </div>
          {annual.length === 0 ? (
            <div className="text-[10px] text-ink-muted">No annual series</div>
          ) : (
            <table className="w-full text-left">
              <thead className="text-[8.5px] uppercase text-ink-muted">
                <tr>
                  <th className="py-0.5 font-bold">Yr</th>
                  <th className="py-0.5 text-right font-bold">EPS</th>
                  <th className="py-0.5 text-right font-bold">%</th>
                  <th className="py-0.5 text-right font-bold">Sales</th>
                  <th className="py-0.5 text-right font-bold">%</th>
                </tr>
              </thead>
              <tbody>
                {annual.map((row) => (
                  <tr key={row.year} className="border-t border-line/70">
                    <td className="py-0.5 text-[10px] text-ink">
                      {String(row.year).replace(/e$/i, "")}
                      {row.is_estimate ? " e" : ""}
                    </td>
                    <td
                      className="py-0.5 text-right"
                      title={
                        row.eps_actual != null && row.eps_estimate != null
                          ? `Act: $${row.eps_actual.toFixed(2)} | Est: $${row.eps_estimate.toFixed(2)}`
                          : undefined
                      }
                    >
                      <span className="inline-flex items-center justify-end gap-1">
                        {row.eps_beat_miss === "beat" && (
                          <span className="text-[8px] text-emerald-500 font-bold" title="Beat estimate">▲</span>
                        )}
                        {row.eps_beat_miss === "miss" && (
                          <span className="text-[8px] text-rose-500 font-bold" title="Missed estimate">▼</span>
                        )}
                        <span>{row.eps !== null ? row.eps.toFixed(2) : "—"}</span>
                      </span>
                    </td>
                    <td className={cn("py-0.5 text-right", chgClass(row.eps_chg_pct))}>
                      {formatSignedPct(row.eps_chg_pct, 0)}
                    </td>
                    <td
                      className="py-0.5 text-right"
                      title={
                        row.revenue_actual != null && row.revenue_estimate != null
                          ? `Act: ${formatSalesShort(row.revenue_actual)} | Est: ${formatSalesShort(row.revenue_estimate)}`
                          : undefined
                      }
                    >
                      <span className="inline-flex items-center justify-end gap-1">
                        {row.revenue_beat_miss === "beat" && (
                          <span className="text-[8px] text-emerald-500 font-bold" title="Beat estimate">▲</span>
                        )}
                        {row.revenue_beat_miss === "miss" && (
                          <span className="text-[8px] text-rose-500 font-bold" title="Missed estimate">▼</span>
                        )}
                        <span>{row.sales_m !== null ? row.sales_m.toFixed(0) : "—"}</span>
                      </span>
                    </td>
                    <td className={cn("py-0.5 text-right", chgClass(row.sales_chg_pct))}>
                      {formatSignedPct(row.sales_chg_pct, 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Latest Reported vs Consensus Estimates & Beat/Miss Section */}
        <section className="space-y-1.5 border-t border-line pt-2">
          <div className="flex items-center justify-between">
            <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
              Last Print vs Est
            </span>
            {onOpenForecastModal && (
              <button
                type="button"
                onClick={onOpenForecastModal}
                className="text-[9px] text-accent hover:underline flex items-center gap-0.5"
                title="View TradingView-style forecast accuracy chart"
              >
                <span>Chart</span>
                <span>›</span>
              </button>
            )}
          </div>

          {/* EPS Card */}
          <div className="rounded border border-line bg-surface-raised p-1.5 space-y-1 text-[10px]">
            <div className="flex items-center justify-between">
              <span className="font-bold text-ink">EPS</span>
              {resolvedEpsBeatFlag !== null ? (
                <span
                  className={cn(
                    "px-1 py-0.2 rounded text-[8.5px] font-bold uppercase tracking-wide",
                    resolvedEpsBeatFlag === 1
                      ? "bg-emerald-500/15 text-emerald-500 border border-emerald-500/30"
                      : "bg-rose-500/15 text-rose-500 border border-rose-500/30",
                  )}
                >
                  {resolvedEpsBeatFlag === 1 ? "Beat" : "Miss"}
                </span>
              ) : (
                <span className="text-[8.5px] text-ink-muted">—</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-1 text-[9px]">
              <div>
                <div className="text-[8px] text-ink-muted">ACTUAL</div>
                <div className="font-bold text-ink">
                  {resolvedEpsAct !== null ? `$${resolvedEpsAct.toFixed(2)}` : "—"}
                </div>
              </div>
              <div>
                <div className="text-[8px] text-ink-muted">ESTIMATE</div>
                <div className="text-ink-muted">
                  {resolvedEpsEst !== null ? `$${resolvedEpsEst.toFixed(2)}` : "—"}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[8px] text-ink-muted">SURPRISE</div>
                <div className={cn("font-bold", chgClass(surprise))}>{formatSignedPct(surprise)}</div>
              </div>
            </div>
          </div>

          {/* Sales Card */}
          <div className="rounded border border-line bg-surface-raised p-1.5 space-y-1 text-[10px]">
            <div className="flex items-center justify-between">
              <span className="font-bold text-ink">Sales</span>
              {resolvedSalesBeatFlag !== null ? (
                <span
                  className={cn(
                    "px-1 py-0.2 rounded text-[8.5px] font-bold uppercase tracking-wide",
                    resolvedSalesBeatFlag === 1
                      ? "bg-emerald-500/15 text-emerald-500 border border-emerald-500/30"
                      : "bg-rose-500/15 text-rose-500 border border-rose-500/30",
                  )}
                >
                  {resolvedSalesBeatFlag === 1 ? "Beat" : "Miss"}
                </span>
              ) : (
                <span className="text-[8.5px] text-ink-muted">—</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-1 text-[9px]">
              <div>
                <div className="text-[8px] text-ink-muted">ACTUAL</div>
                <div className="font-bold text-ink">{formatSalesShort(resolvedSalesAct)}</div>
              </div>
              <div>
                <div className="text-[8px] text-ink-muted">ESTIMATE</div>
                <div className="text-ink-muted">{formatSalesShort(resolvedSalesEst)}</div>
              </div>
              <div className="text-right">
                <div className="text-[8px] text-ink-muted">SURPRISE</div>
                <div className={cn("font-bold", chgClass(resolvedSalesSurprise))}>
                  {formatSignedPct(resolvedSalesSurprise)}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-0.5 border-t border-line pt-2">
          <div className="mb-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">Ratings</div>
          {ratingRow("RS", kpiNum(kpis, "rs_rating"))}
          {ratingRow("Tech", kpiNum(kpis, "technical_rating"))}
          {ratingRow("Setup", kpiNum(kpis, "setup_quality_rating"))}
          {ratingRow("Growth", kpiNum(kpis, "growth_rating"))}
          {ratingRow("Overall", kpiNum(kpis, "overall_score"))}
          <div className="flex items-center justify-between gap-2 pt-0.5">
            <span className="text-ink-muted">Surprise</span>
            <span className={cn("font-bold", chgClass(surprise))}>{formatSignedPct(surprise)}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-ink-muted">CY 90d</span>
            <span className={cn("font-bold", chgClass(cyRev))}>{formatSignedPct(cyRev)}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-ink-muted">NY 90d</span>
            <span className={cn("font-bold", chgClass(nyRev))}>{formatSignedPct(nyRev)}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-ink-muted">Sales NY 90d</span>
            <span className={cn("font-bold", chgClass(salesNyRev))}>{formatSignedPct(salesNyRev)}</span>
          </div>
        </section>

        <section className="space-y-0.5 border-t border-line pt-2">
          <div className="mb-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
            Fundamentals
          </div>
          {fundRow("TTM EPS", kpiNum(kpis, "mrt_epsdil") !== null ? `$${formatNum(kpiNum(kpis, "mrt_epsdil"), 2)}` : "—")}
          {fundRow("ROE", formatSignedPct(roe))}
          {fundRow("ROIC", formatSignedPct(roic))}
          {fundRow("Net mgn", formatSignedPct(netMgn))}
          {fundRow("Gross mgn", formatSignedPct(grossMgn))}
          {fundRow("D/E", formatNum(kpiNum(kpis, "mrq_de"), 2))}
          {fundRow("P/E", formatNum(kpiNum(kpis, "pe"), 1))}
          {fundRow("P/S", formatNum(kpiNum(kpis, "ps"), 1))}
        </section>

        <section className="border-t border-line pt-2">
          <div className="mb-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
            Top RS peers
          </div>
          {peers.length === 0 ? (
            <div className="text-[10px] text-ink-muted">No peers</div>
          ) : (
            <table className="w-full text-left">
              <thead className="text-[8.5px] uppercase text-ink-muted">
                <tr>
                  <th className="py-0.5 font-bold">Tkr</th>
                  <th className="py-0.5 text-right font-bold">RS</th>
                  <th className="py-0.5 text-right font-bold">Close</th>
                </tr>
              </thead>
              <tbody>
                {peers.map((peer) => (
                  <tr
                    key={peer.ticker}
                    className={cn(onSelectTicker ? "cursor-pointer hover:bg-surface-sunk" : "")}
                    onClick={() => onSelectTicker?.(peer.ticker)}
                  >
                    <td className="py-0.5 font-bold text-accent">{peer.ticker}</td>
                    <td className="py-0.5 text-right">{peer.rs_rating ?? "—"}</td>
                    <td className="py-0.5 text-right">${peer.close.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </aside>
  );
}
