import type { FormEvent, ReactNode } from "react";
import type { StockIntrospectionData } from "../../types";
import { BookmarkButton } from "./BookmarkButton";
import { cn } from "../../lib/utils";

interface QuoteHeaderProps {
  ticker: string;
  data?: StockIntrospectionData | null;
  asOfDate: string;
  onAsOfDateChange?: (date: string) => void;
  showSearch?: boolean;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  onSearchSubmit?: (ticker: string) => void;
  trailing?: ReactNode;
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

function formatSignedPct(value: number | null, digits = 1): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function formatVol(value: unknown): string {
  const n = num(value);
  if (n === null) return "—";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(Math.round(n));
}

function formatMarketCap(value: unknown): string {
  const n = num(value);
  if (n === null || n === 0) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

function pctClass(value: number | null): string {
  if (value === null) return "text-ink";
  if (value > 0) return "text-emerald-500";
  if (value < 0) return "text-rose-500";
  return "text-ink";
}

export function QuoteHeader({
  ticker,
  data,
  asOfDate,
  onAsOfDateChange,
  showSearch = false,
  searchValue,
  onSearchChange,
  onSearchSubmit,
  trailing,
}: QuoteHeaderProps) {
  const kpis = data?.as_of_kpis ?? {};
  const close = num(kpis.close);
  const perf5d = asPct(kpis.perf_5d);
  const avgVol = kpis.avg_vol_50d;
  const marketcap = kpis.marketcap;
  const high52w = num(kpis.high_52w);
  const atrPct = asPct(kpis.atr_14_pct);
  const off52w =
    close !== null && high52w !== null && high52w > 0
      ? (1 - close / high52w) * 100
      : null;
  const industry = data?.industry || data?.sector || "";

  const handleSearchSubmit = (e: FormEvent) => {
    e.preventDefault();
    const next = (searchValue ?? "").trim().toUpperCase();
    if (next) onSearchSubmit?.(next);
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-3 py-1.5 text-[11px] font-mono">
      <div className="flex min-w-0 flex-wrap items-center gap-2.5">
        {showSearch && (
          <form onSubmit={handleSearchSubmit} className="flex items-center gap-1">
            <input
              type="text"
              value={searchValue ?? ticker}
              onChange={(e) => onSearchChange?.(e.target.value.toUpperCase())}
              placeholder="Ticker"
              className="w-24 rounded border border-line bg-surface-sunk px-2 py-0.5 font-bold text-ink focus:border-accent focus:outline-none"
            />
            <button
              type="submit"
              className="rounded bg-accent px-2 py-0.5 font-bold text-white hover:bg-accent/90"
            >
              Go
            </button>
          </form>
        )}

        <div className="flex min-w-0 items-baseline gap-1.5">
          <span className="text-base font-bold text-accent">{ticker}</span>
          {data?.company_name && data.company_name !== ticker && (
            <span className="max-w-[220px] truncate text-[11px] font-semibold text-ink">
              {data.company_name}
            </span>
          )}
          {industry && (
            <span className="hidden max-w-[180px] truncate text-[10px] text-ink-muted sm:inline">
              {industry}
            </span>
          )}
          <BookmarkButton ticker={ticker} />
        </div>

        <div className="flex flex-wrap items-center gap-2.5 text-[11px]">
          <span className="font-bold text-ink">
            {close !== null ? `$${close.toFixed(2)}` : "—"}
            <span className={cn("ml-1 font-bold", pctClass(perf5d))}>
              {formatSignedPct(perf5d)}
            </span>
          </span>
          <span className="text-ink-muted">
            Vol <span className="font-bold text-ink">{formatVol(avgVol)}</span>
          </span>
          <span className="text-ink-muted">
            Mkt <span className="font-bold text-ink">{formatMarketCap(marketcap)}</span>
          </span>
          <span className="text-ink-muted">
            52w{" "}
            <span className={cn("font-bold", pctClass(off52w !== null ? -off52w : null))}>
              {off52w !== null ? `-${off52w.toFixed(1)}%` : "—"}
            </span>
          </span>
          <span className="text-ink-muted">
            ATR <span className="font-bold text-ink">{formatSignedPct(atrPct).replace("+", "")}</span>
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 font-bold text-amber-500">
          <span>As-Of</span>
          {onAsOfDateChange ? (
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => onAsOfDateChange(e.target.value)}
              className="bg-transparent text-amber-400 focus:outline-none"
            />
          ) : (
            <span>{asOfDate}</span>
          )}
        </label>
        {trailing}
      </div>
    </div>
  );
}
