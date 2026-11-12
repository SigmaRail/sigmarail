import React, { useState, useEffect, useMemo } from "react";
import katex from "katex";
import type { FieldEvaluationResult } from "../../types";

export interface FieldEvaluatorDrawerProps {
  fieldName: string;
  table?: string;
  defaultTicker?: string;
  asOfDate?: string;
}

export function FieldEvaluatorDrawer({
  fieldName,
  table,
  defaultTicker = "NVDA",
  asOfDate = "",
}: FieldEvaluatorDrawerProps) {
  const [ticker, setTicker] = useState(defaultTicker);
  const [inputTicker, setInputTicker] = useState(defaultTicker);
  const [data, setData] = useState<FieldEvaluationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEvaluation = async (t: string) => {
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams({ ticker: t });
      if (table) q.set("table", table);
      if (asOfDate) q.set("as_of_date", asOfDate);
      const response = await fetch(
        `/api/screens/fields/${encodeURIComponent(fieldName)}/evaluate?${q.toString()}`
      );
      if (!response.ok) {
        throw new Error(`Failed to evaluate: HTTP ${response.status}`);
      }
      const json: FieldEvaluationResult = await response.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "Failed to fetch evaluation");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvaluation(ticker);
  }, [fieldName, table, ticker, asOfDate]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputTicker.trim()) {
      setTicker(inputTicker.trim().toUpperCase());
    }
  };

  const subHtml = useMemo(() => {
    if (!data?.substituted_latex) return null;
    try {
      return katex.renderToString(data.substituted_latex, {
        throwOnError: false,
        displayMode: true,
      });
    } catch {
      return null;
    }
  }, [data?.substituted_latex]);

  const dist = data?.distribution;

  const pctPosition = useMemo(() => {
    if (data?.cohort_percentile != null) {
      return Math.max(2, Math.min(98, data.cohort_percentile));
    }
    if (dist && typeof data?.value === "number" && dist.max > dist.min) {
      const norm = ((data.value - dist.min) / (dist.max - dist.min)) * 100;
      return Math.max(2, Math.min(98, norm));
    }
    return 50;
  }, [data?.cohort_percentile, data?.value, dist]);

  const p25Pos =
    dist && dist.max > dist.min ? ((dist.p25 - dist.min) / (dist.max - dist.min)) * 100 : 25;
  const p75Pos =
    dist && dist.max > dist.min ? ((dist.p75 - dist.min) / (dist.max - dist.min)) * 100 : 75;
  const medPos =
    dist && dist.max > dist.min ? ((dist.median - dist.min) / (dist.max - dist.min)) * 100 : 50;

  return (
    <div className="space-y-2.5 rounded-lg border border-line bg-surface-sunk/60 p-2.5 text-ink">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
          Live Worked Example
        </span>
        <form onSubmit={handleSubmit} className="flex items-center gap-1">
          <input
            type="text"
            value={inputTicker}
            onChange={(e) => setInputTicker(e.target.value.toUpperCase())}
            placeholder="Ticker"
            className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded bg-accent/15 px-1.5 py-0.5 text-[9.5px] font-semibold text-accent hover:bg-accent/25"
          >
            Eval
          </button>
        </form>
      </div>

      {loading && (
        <div className="py-4 text-center font-mono text-[10.5px] text-ink-muted animate-pulse">
          Evaluating {ticker} on ClickHouse...
        </div>
      )}

      {error && (
        <div className="rounded border border-red-500/30 bg-red-500/10 p-2 text-[10px] text-red-400">
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <div className="space-y-2.5 text-[11px]">
          <div className="flex items-center justify-between rounded-md bg-surface p-2 border border-line">
            <div>
              <span className="font-bold text-ink">{data.ticker}</span>
              <span className="ml-1.5 text-[9.5px] text-ink-muted">({data.date})</span>
            </div>
            <div className="text-right">
              <span className="font-mono font-bold text-accent text-sm">
                {typeof data.value === "number" ? data.value.toFixed(1) : String(data.value ?? "N/A")}
              </span>
              {data.rank && data.universe_size && (
                <div className="text-[9px] text-ink-muted">
                  Rank #{data.rank} / {data.universe_size}
                </div>
              )}
            </div>
          </div>

          {subHtml && (
            <div className="rounded-md border border-line bg-surface p-2 space-y-1">
              <span className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                Evaluated Equation (Plug-in Numbers)
              </span>
              <div
                className="overflow-x-auto py-1 text-center font-medium text-xs text-ink"
                dangerouslySetInnerHTML={{ __html: subHtml }}
              />
            </div>
          )}

          {dist && (
            <div className="rounded-md border border-line bg-surface p-2 space-y-1.5">
              <div className="flex items-center justify-between text-[9px] font-bold uppercase tracking-wider">
                <span className="text-ink-muted">Cross-Sectional Cohort Distribution</span>
                {data.cohort_percentile != null && (
                  <span className="text-accent font-semibold font-mono">
                    P{data.cohort_percentile.toFixed(1)} percentile
                  </span>
                )}
              </div>
              <div className="relative h-6 w-full rounded bg-surface-sunk/80 px-2 flex items-center">
                <div
                  className="absolute h-3 rounded bg-accent/15 border border-accent/25"
                  style={{
                    left: `${p25Pos}%`,
                    width: `${Math.max(2, p75Pos - p25Pos)}%`,
                  }}
                  title={`IQR (P25-P75): ${dist.p25.toFixed(1)} to ${dist.p75.toFixed(1)}`}
                />
                <div
                  className="absolute h-4 w-0.5 bg-ink-muted/60"
                  style={{ left: `${medPos}%` }}
                  title={`Median: ${dist.median.toFixed(1)}`}
                />
                <div
                  className="absolute -top-1 flex flex-col items-center -translate-x-1/2 transition-all duration-300"
                  style={{ left: `${pctPosition}%` }}
                >
                  <div className="h-3.5 w-3.5 rounded-full bg-accent text-white shadow flex items-center justify-center text-[7.5px] font-bold border-2 border-surface">
                    o
                  </div>
                </div>
              </div>
              <div className="flex justify-between text-[8.5px] font-mono text-ink-muted/80 pt-0.5">
                <span>Min: {dist.min.toFixed(1)}</span>
                <span>P25: {dist.p25.toFixed(1)}</span>
                <span className="font-semibold text-ink">Med: {dist.median.toFixed(1)}</span>
                <span>P75: {dist.p75.toFixed(1)}</span>
                <span>Max: {dist.max.toFixed(1)}</span>
              </div>
            </div>
          )}

          {data.steps && data.steps.length > 0 && (
            <div className="space-y-1">
              <label className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                Calculation Walkthrough
              </label>
              <div className="space-y-1 rounded border border-line bg-surface p-2 font-mono text-[9.5px]">
                {data.steps.map((step, idx) => (
                  <div key={idx} className="leading-relaxed text-ink-muted">
                    <span className="text-accent font-semibold">{step}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default FieldEvaluatorDrawer;
