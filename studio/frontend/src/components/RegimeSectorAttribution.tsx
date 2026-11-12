import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchRunAttribution } from "../api/backtests";

function formatCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  const prefix = val < 0 ? "-$" : "$";
  return `${prefix}${Math.abs(val).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `${(val * 100).toFixed(1)}%`;
}

export function RegimeSectorAttribution({ runId }: { runId: string }) {
  const [industrySearch, setIndustrySearch] = useState("");

  const attributionQuery = useQuery({
    queryKey: ["run-attribution", runId],
    queryFn: () => fetchRunAttribution(runId),
  });

  const data = attributionQuery.data;

  const filteredIndustries = useMemo(() => {
    const list = data?.industries ?? [];
    if (!industrySearch.trim()) return list;
    const lower = industrySearch.toLowerCase();
    return list.filter(
      (i) =>
        i.industry.toLowerCase().includes(lower) ||
        i.sector.toLowerCase().includes(lower),
    );
  }, [data?.industries, industrySearch]);

  if (attributionQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-[12px] text-ink-muted">
        Analyzing sector and market regime attribution via ClickHouse…
      </div>
    );
  }

  if (attributionQuery.isError || !data || data.error) {
    return (
      <div className="p-4 text-[12px] text-danger">
        {data?.error || (attributionQuery.error as Error)?.message || "Failed to load attribution."}
      </div>
    );
  }

  const maxSectorPnl = Math.max(
    ...data.sectors.map((s) => Math.abs(s.total_pnl)),
    1,
  );

  return (
    <div className="space-y-6 p-4">
      {/* Attribution Summary KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded border border-line bg-surface p-3 shadow-sm">
          <span className="text-[10.5px] font-medium uppercase tracking-wider text-ink-faint">
            Total Closed PnL
          </span>
          <p
            className={`mt-1 font-mono text-lg font-bold ${
              data.summary.total_pnl >= 0 ? "text-accent" : "text-danger"
            }`}
          >
            {formatCurrency(data.summary.total_pnl)}
          </p>
          <span className="text-[10px] text-ink-muted">
            Across {data.summary.total_trades} closed trades
          </span>
        </div>

        <div className="rounded border border-line bg-surface p-3 shadow-sm">
          <span className="text-[10.5px] font-medium uppercase tracking-wider text-ink-faint">
            Top Sector
          </span>
          <p className="mt-1 font-mono text-base font-bold text-ink truncate">
            {data.summary.top_sector}
          </p>
          <span className="font-mono text-[10.5px] font-semibold text-accent">
            +{formatCurrency(data.summary.top_sector_pnl)}
          </span>
        </div>

        <div className="rounded border border-line bg-surface p-3 shadow-sm">
          <span className="text-[10.5px] font-medium uppercase tracking-wider text-ink-faint">
            Best Market Regime
          </span>
          <p className="mt-1 font-mono text-xs font-bold text-ink truncate">
            {data.summary.best_regime}
          </p>
          <span className="text-[10px] text-ink-muted">
            Highest cumulative alpha
          </span>
        </div>

        <div className="rounded border border-line bg-surface p-3 shadow-sm">
          <span className="text-[10.5px] font-medium uppercase tracking-wider text-ink-faint">
            Active Sectors
          </span>
          <p className="mt-1 font-mono text-lg font-bold text-ink">
            {data.sectors.length}
          </p>
          <span className="text-[10px] text-ink-muted">
            {data.industries.length} unique industries
          </span>
        </div>
      </div>

      {/* Market Regime Alpha Breakdown */}
      <div className="rounded border border-line bg-surface p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">
              Market Regime & Breadth Alpha Attribution
            </h3>
            <p className="text-[11px] text-ink-muted">
              Performance segmented by S&P 500 breadth (% above 200-day SMA) from{" "}
              <code className="font-mono text-[10px]">vera.market_regime_signals</code>
            </p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          {data.regimes.map((reg) => {
            const isBull = reg.regime.includes("Bull");
            const isBear = reg.regime.includes("Bear");
            const borderCol = isBull
              ? "border-emerald-500/40 bg-emerald-500/5"
              : isBear
                ? "border-rose-500/40 bg-rose-500/5"
                : "border-amber-500/40 bg-amber-500/5";

            const badgeCol = isBull
              ? "bg-emerald-500/20 text-emerald-400"
              : isBear
                ? "bg-rose-500/20 text-rose-400"
                : "bg-amber-500/20 text-amber-400";

            return (
              <div
                key={reg.regime}
                className={`flex flex-col justify-between rounded border p-3.5 transition-all ${borderCol}`}
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h4 className="text-[12.5px] font-bold text-ink">
                        {reg.regime}
                      </h4>
                      <p className="text-[10.5px] text-ink-muted">
                        {reg.description}
                      </p>
                    </div>
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${badgeCol}`}
                    >
                      {reg.total_trades} trades
                    </span>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      <span className="text-[10px] text-ink-faint">Net PnL</span>
                      <p
                        className={`font-mono text-sm font-bold ${
                          reg.total_pnl >= 0 ? "text-accent" : "text-danger"
                        }`}
                      >
                        {formatCurrency(reg.total_pnl)}
                      </p>
                    </div>

                    <div>
                      <span className="text-[10px] text-ink-faint">Win Rate</span>
                      <p className="font-mono text-sm font-bold text-ink">
                        {formatPct(reg.win_rate)}
                      </p>
                    </div>

                    <div>
                      <span className="text-[10px] text-ink-faint">Profit Factor</span>
                      <p className="font-mono font-semibold text-ink">
                        {reg.profit_factor != null ? reg.profit_factor.toFixed(2) : "—"}
                      </p>
                    </div>

                    <div>
                      <span className="text-[10px] text-ink-faint">Expectancy</span>
                      <p className="font-mono font-semibold text-ink">
                        {reg.expectancy != null ? reg.expectancy.toFixed(3) : "—"}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-3 border-t border-line/50 pt-2 text-[10px] text-ink-faint">
                  Avg Return / Trade:{" "}
                  <span className="font-mono font-semibold text-ink-muted">
                    {formatPct(reg.avg_return_pct)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sector Attribution Breakdown */}
      <div className="rounded border border-line bg-surface p-4 shadow-sm">
        <div className="border-b border-line pb-3">
          <h3 className="text-sm font-semibold text-ink">
            GICS Sector Performance & Alpha Decomposition
          </h3>
          <p className="text-[11px] text-ink-muted">
            Net dollar profit and win rate distribution across sectors
          </p>
        </div>

        {/* Sector Visual Bars */}
        <div className="mt-4 space-y-2.5">
          {data.sectors.map((sec) => {
            const isPos = sec.total_pnl >= 0;
            const barWidthPct = Math.min(
              100,
              Math.max(4, Math.round((Math.abs(sec.total_pnl) / maxSectorPnl) * 100)),
            );

            return (
              <div key={sec.sector} className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-medium text-ink">{sec.sector}</span>
                  <div className="flex items-center gap-3 font-mono text-[10.5px]">
                    <span className="text-ink-muted">
                      {sec.total_trades} trades ({formatPct(sec.win_rate)} win)
                    </span>
                    <span
                      className={`font-bold ${
                        isPos ? "text-accent" : "text-danger"
                      }`}
                    >
                      {formatCurrency(sec.total_pnl)}
                    </span>
                  </div>
                </div>

                {/* Bar */}
                <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunk border border-line/40">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isPos ? "bg-accent" : "bg-danger"
                    }`}
                    style={{ width: `${barWidthPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Sector Table */}
        <div className="mt-5 overflow-x-auto border-t border-line pt-4">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-line text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                <th className="py-2 pl-2">Sector</th>
                <th className="py-2 text-right">Net PnL</th>
                <th className="py-2 text-right">Trades</th>
                <th className="py-2 text-right">Win Rate</th>
                <th className="py-2 text-right">Profit Factor</th>
                <th className="py-2 text-right">Avg Return</th>
                <th className="py-2 pl-4">Top Symbols</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60 font-mono">
              {data.sectors.map((sec) => (
                <tr key={sec.sector} className="hover:bg-surface-sunk/40 transition-colors">
                  <td className="py-2 pl-2 font-sans font-medium text-ink">
                    {sec.sector}
                  </td>
                  <td
                    className={`py-2 text-right font-bold ${
                      sec.total_pnl >= 0 ? "text-accent" : "text-danger"
                    }`}
                  >
                    {formatCurrency(sec.total_pnl)}
                  </td>
                  <td className="py-2 text-right text-ink-muted">
                    {sec.total_trades}
                  </td>
                  <td className="py-2 text-right text-ink">
                    {formatPct(sec.win_rate)}
                  </td>
                  <td className="py-2 text-right text-ink-muted">
                    {sec.profit_factor != null ? sec.profit_factor.toFixed(2) : "—"}
                  </td>
                  <td className="py-2 text-right text-ink-muted">
                    {formatPct(sec.avg_return_pct)}
                  </td>
                  <td className="py-2 pl-4 text-[10px] text-ink-faint truncate max-w-xs">
                    {sec.symbols.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Industry Drilldown Table */}
      {data.industries.length > 0 ? (
        <div className="rounded border border-line bg-surface p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <div>
              <h3 className="text-sm font-semibold text-ink">
                Industry-Level Drilldown
              </h3>
              <p className="text-[11px] text-ink-muted">
                Granular industry performance and win rates
              </p>
            </div>
            <input
              type="text"
              value={industrySearch}
              onChange={(e) => setIndustrySearch(e.target.value)}
              placeholder="Search industry or sector..."
              className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
            />
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead>
                <tr className="border-b border-line text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                  <th className="py-2 pl-2">Industry</th>
                  <th className="py-2">Sector</th>
                  <th className="py-2 text-right">Net PnL</th>
                  <th className="py-2 text-right">Trades</th>
                  <th className="py-2 text-right">Win Rate</th>
                  <th className="py-2 text-right">Profit Factor</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60 font-mono">
                {filteredIndustries.map((ind, idx) => (
                  <tr key={idx} className="hover:bg-surface-sunk/40 transition-colors">
                    <td className="py-2 pl-2 font-sans font-medium text-ink">
                      {ind.industry}
                    </td>
                    <td className="py-2 font-sans text-ink-muted text-[10.5px]">
                      {ind.sector}
                    </td>
                    <td
                      className={`py-2 text-right font-bold ${
                        ind.total_pnl >= 0 ? "text-accent" : "text-danger"
                      }`}
                    >
                      {formatCurrency(ind.total_pnl)}
                    </td>
                    <td className="py-2 text-right text-ink-muted">
                      {ind.total_trades}
                    </td>
                    <td className="py-2 text-right text-ink">
                      {formatPct(ind.win_rate)}
                    </td>
                    <td className="py-2 text-right text-ink-muted">
                      {ind.profit_factor != null ? ind.profit_factor.toFixed(2) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
