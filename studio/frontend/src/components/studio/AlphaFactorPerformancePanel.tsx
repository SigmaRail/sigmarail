import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAlphaPerformance, fetchLatestTradingDate } from "../../api/screens";
import type { ScreenField } from "../../types";
import type { PipelineDocument } from "../strategy/StrategyDocument";
import {
  fmtNum,
  fmtPct,
  measureFactors,
  resolveFactorTable,
  yearsBack,
} from "../../lib/alphaPerformance";
import { cn } from "../../lib/utils";

type Props = {
  document: PipelineDocument;
  fields: ScreenField[];
  /** Default evaluation end (backtest end / as-of). */
  asOf?: string;
  /** Default evaluation start (backtest start). Falls back to end − 1y. */
  startDate?: string;
};

const VERDICT_TONE: Record<string, string> = {
  pass: "border-accent bg-accent/15 text-accent-ink",
  fail: "border-danger bg-danger/10 text-danger",
  insufficient_data: "border-warn bg-warn/10 text-warn",
};

function Kpi({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="rounded border border-line bg-surface px-2 py-1" title={title}>
      <div className="text-[9px] uppercase tracking-wide text-ink-faint">{label}</div>
      <div className="font-mono text-[12px] text-ink">{value}</div>
    </div>
  );
}

/**
 * Pre-LEAN factor scorecard (VeraProjects#70/#75): evaluates a field measure's
 * forward-return efficacy vs the EW active universe — before LEAN backtest.
 * Props-driven so the same card can mount in backtest results or standalone.
 */
export function AlphaFactorPerformancePanel({
  document,
  fields,
  asOf = "",
  startDate = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [alias, setAlias] = useState("");
  const [horizon, setHorizon] = useState<"5d" | "21d">("5d");
  const [quantiles, setQuantiles] = useState(10);
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");

  const measures = useMemo(
    () => measureFactors(document.stages ?? []),
    [document.stages],
  );
  const evaluable = measures.filter((m) => m.column);
  const selected = measures.find((m) => m.alias === alias) ?? null;
  const column = selected?.column ?? null;
  const table = column ? resolveFactorTable(column, fields) : null;

  // Auto-select first evaluable measure when opening / on doc change.
  useEffect(() => {
    if (!open) return;
    setAlias((prev) =>
      measures.some((m) => m.alias === prev) ? prev : (evaluable[0]?.alias ?? ""),
    );
  }, [open, measures, evaluable]);

  const latestDateQuery = useQuery({
    queryKey: ["latest-trading-date"],
    queryFn: fetchLatestTradingDate,
    enabled: open && !asOf,
    staleTime: 10 * 60_000,
  });
  const endDate = endInput || asOf || latestDateQuery.data || "";
  const startD = startInput || startDate || yearsBack(endDate);

  const query = useQuery({
    queryKey: ["alpha-performance", column, table, startD, endDate, horizon, quantiles],
    queryFn: () =>
      fetchAlphaPerformance(column!, {
        start: startD,
        end: endDate,
        horizon,
        quantiles,
        table: table ?? undefined,
      }),
    enabled: open && Boolean(column && startD && endDate),
    staleTime: 60_000,
  });
  const data = query.data ?? null;
  const maxAbsSpread = useMemo(() => {
    if (!data) return 0;
    return Math.max(
      0,
      ...data.quantiles.map((q) => Math.abs(q.mean_active_spread)),
    );
  }, [data]);

  return (
    <div className="rounded border border-line bg-surface-sunk/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-[10.5px] font-semibold uppercase tracking-wide text-ink-muted hover:bg-surface-raised/50"
      >
        <span>Factor performance (pre-LEAN)</span>
        <span className="font-mono text-[10px]">{open ? "▼" : "▶"}</span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-line px-2.5 py-2">
          <p className="text-[10px] text-ink-faint leading-tight">
            Forward-return scorecard vs equal-weight active universe (ClickHouse,
            no LEAN). Field measures only — expression/filter measures need a
            materialized factor column.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
            >
              {evaluable.length === 0 ? (
                <option value="">(no field measures)</option>
              ) : null}
              {evaluable.map((m) => (
                <option key={m.alias} value={m.alias}>
                  {m.alias} := {m.column}
                </option>
              ))}
              {measures
                .filter((m) => !m.column)
                .map((m) => (
                  <option key={m.alias} value={m.alias} disabled title={m.reason}>
                    {m.alias} (unsupported)
                  </option>
                ))}
            </select>

            <div className="flex items-center gap-1">
              {(["5d", "21d"] as const).map((h) => (
                <button
                  key={h}
                  type="button"
                  onClick={() => setHorizon(h)}
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[10px] font-mono",
                    horizon === h
                      ? "border-accent bg-accent/15 text-accent-ink"
                      : "border-line text-ink-muted hover:bg-surface",
                  )}
                >
                  {h}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1">
              {([5, 10] as const).map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuantiles(q)}
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[10px] font-mono",
                    quantiles === q
                      ? "border-accent bg-accent/15 text-accent-ink"
                      : "border-line text-ink-muted hover:bg-surface",
                  )}
                >
                  q{q}
                </button>
              ))}
            </div>

            <label className="flex items-center gap-1 text-[10px] text-ink-faint">
              start
              <input
                type="date"
                value={startD}
                onChange={(e) => setStartInput(e.target.value)}
                className="rounded border border-line bg-surface px-1 py-0.5 font-mono text-[10px] text-ink"
              />
            </label>
            <label className="flex items-center gap-1 text-[10px] text-ink-faint">
              end
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndInput(e.target.value)}
                className="rounded border border-line bg-surface px-1 py-0.5 font-mono text-[10px] text-ink"
              />
            </label>
          </div>

          {evaluable.length === 0 ? (
            <p className="font-mono text-[10px] text-ink-faint">
              Add a field measure (Measures → “Add field as Insight sort key”) to
              evaluate its forward alpha.
            </p>
          ) : null}
          {selected && !selected.column ? (
            <p className="font-mono text-[10px] text-warn">{selected.reason}</p>
          ) : null}
          {!endDate ? (
            <p className="font-mono text-[10px] text-ink-faint">
              Set evaluation end (as-of) to run.
            </p>
          ) : null}

          {query.isLoading ? (
            <p className="font-mono text-[10px] text-ink-muted">Evaluating factor…</p>
          ) : null}
          {query.error ? (
            <p className="font-mono text-[10px] text-danger">
              {(query.error as Error).message}
            </p>
          ) : null}

          {data ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                    VERDICT_TONE[data.verdict] ?? "border-line text-ink-muted",
                  )}
                >
                  {data.verdict}
                </span>
                <span className="font-mono text-[10px] text-ink-faint">
                  {data.factor} · {data.factor_table} · {data.horizon} · days=
                  {data.summary.n_days}
                </span>
              </div>
              {data.verdict_reasons.length ? (
                <p className="font-mono text-[10px] text-ink-faint">
                  {data.verdict_reasons.join(" · ")}
                </p>
              ) : null}

              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-6">
                <Kpi label="Top−Bottom" value={fmtPct(data.summary.top_minus_bottom_active_spread)} title="Top quantile minus bottom quantile mean active spread" />
                <Kpi label="Top active" value={fmtPct(data.summary.top_mean_active_spread)} title="Top quantile mean fwd_ret − EW universe" />
                <Kpi label="EW universe" value={fmtPct(data.summary.ew_mean_fwd_ret)} title="Equal-weight universe mean forward return" />
                <Kpi label="IC mean" value={fmtNum(data.ic_stats.mean_ic)} title="Mean daily Spearman rank IC" />
                <Kpi label="ICIR" value={fmtNum(data.ic_stats.icir)} title="IC mean/std × √252" />
                <Kpi label="Monotonicity" value={fmtNum(data.monotonicity_score, 2)} title="Corr(bucket index, bucket mean fwd ret); 1.0 = monotone" />
              </div>

              {data.quantiles.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse font-mono text-[10px]">
                    <thead>
                      <tr className="text-left text-ink-faint">
                        <th className="py-0.5 pr-2 font-normal">bucket</th>
                        <th className="py-0.5 pr-2 font-normal">n</th>
                        <th className="py-0.5 pr-2 font-normal">fwd ret</th>
                        <th className="py-0.5 pr-2 font-normal">active</th>
                        <th className="py-0.5 pr-2 font-normal">hit</th>
                        <th className="py-0.5 font-normal">spread</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.quantiles.map((q) => (
                        <tr key={q.bucket} className="border-t border-line/40">
                          <td className="py-0.5 pr-2 text-ink">{q.bucket}</td>
                          <td className="py-0.5 pr-2 text-ink-muted">{q.n_obs}</td>
                          <td
                            className={cn(
                              "py-0.5 pr-2",
                              q.mean_fwd_ret >= 0 ? "text-accent-ink" : "text-danger",
                            )}
                          >
                            {fmtPct(q.mean_fwd_ret)}
                          </td>
                          <td
                            className={cn(
                              "py-0.5 pr-2",
                              q.mean_active_spread >= 0 ? "text-accent-ink" : "text-danger",
                            )}
                          >
                            {fmtPct(q.mean_active_spread)}
                          </td>
                          <td className="py-0.5 pr-2 text-ink-muted">
                            {(q.hit_rate * 100).toFixed(0)}%
                          </td>
                          <td className="py-0.5 w-32">
                            <div className="h-1.5 w-full rounded bg-surface">
                              <div
                                className={cn(
                                  "h-1.5 rounded",
                                  q.mean_active_spread >= 0 ? "bg-accent" : "bg-danger",
                                )}
                                style={{
                                  width: `${maxAbsSpread > 0 ? Math.min(100, (Math.abs(q.mean_active_spread) / maxAbsSpread) * 100) : 0}%`,
                                }}
                              />
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="font-mono text-[10px] text-ink-faint">
                  No overlapping factor/forward-return rows in window.
                </p>
              )}

              {Object.keys(data.regime_attribution).length ? (
                <div>
                  <div className="text-[9px] uppercase tracking-wide text-ink-faint">
                    Regime attribution (top bucket active spread)
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {Object.entries(data.regime_attribution).map(([frac, v]) => (
                      <div
                        key={frac}
                        className="rounded border border-line bg-surface px-2 py-1"
                        title={`${v.n_days} days at allocation fraction ${frac}`}
                      >
                        <span className="font-mono text-[10px] text-ink-muted">
                          {frac === "none" ? "no regime" : `alloc ${frac}`}
                        </span>
                        <span
                          className={cn(
                            "ml-1.5 font-mono text-[10px]",
                            v.active_spread >= 0 ? "text-accent-ink" : "text-danger",
                          )}
                        >
                          {fmtPct(v.active_spread)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
