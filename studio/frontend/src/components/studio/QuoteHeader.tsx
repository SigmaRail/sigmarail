import type { FormEvent, ReactNode } from "react";
import type { StockIntrospectionData } from "../../types";
import { BookmarkButton } from "./BookmarkButton";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";

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

  const dateControl = onAsOfDateChange ? (
    <Input
      aria-label="As of date"
      type="date"
      value={asOfDate}
      onChange={(e) => onAsOfDateChange(e.target.value)}
      className="h-8 w-[8.5rem] px-1.5 py-1 text-[11px] text-foreground sm:h-9 sm:w-[9.5rem] sm:px-2 sm:text-xs"
    />
  ) : <span>{asOfDate}</span>;

  return (
    <header data-testid="charts-quote-header" className="min-w-0 border-b border-border bg-background px-2 py-1.5 text-xs sm:grid sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-x-4 sm:px-3 sm:py-2">
      <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
        <div className="flex min-w-0 items-center justify-between gap-2 sm:contents">
          {showSearch ? (
            <form onSubmit={handleSearchSubmit} className="flex min-w-0 items-center gap-1 sm:w-auto">
              <Input
                aria-label="Ticker"
                type="text"
                value={searchValue ?? ticker}
                onChange={(e) => onSearchChange?.(e.target.value.toUpperCase())}
                placeholder="Ticker"
                className="h-8 w-[6.25rem] px-2 py-1 text-xs font-semibold sm:h-9 sm:w-24"
              />
              <Button type="submit" size="sm" className="h-8 px-2.5 text-xs sm:h-9 sm:px-3">
                View
              </Button>
            </form>
          ) : null}
          <label className="flex shrink-0 items-center gap-1 text-[10px] font-medium text-muted-foreground sm:hidden">
            <span className="sr-only">As of</span>
            {dateControl}
          </label>
        </div>

        <div className="flex min-w-0 items-center gap-1.5 sm:flex-wrap sm:items-baseline sm:gap-x-1.5 sm:gap-y-1">
          <h1 className={cn("text-base font-semibold text-foreground", showSearch && "hidden sm:block")}>{ticker}</h1>
          {data?.company_name && data.company_name !== ticker && (
            <span className="hidden max-w-[min(42vw,220px)] truncate text-xs font-medium text-muted-foreground sm:inline">
              {data.company_name}
            </span>
          )}
          {industry && (
            <span className="hidden max-w-[180px] truncate text-[11px] text-muted-foreground sm:inline">
              {industry}
            </span>
          )}
          <BookmarkButton ticker={ticker} />
          <span className="font-mono text-sm font-semibold text-foreground sm:ml-1">
            {close !== null ? `$${close.toFixed(2)}` : "—"}
            <span className={cn("ml-1 text-xs font-semibold", pctClass(perf5d))}>
              {formatSignedPct(perf5d)}
            </span>
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground min-[420px]:grid-cols-4 sm:flex sm:flex-wrap sm:items-center sm:gap-3 sm:text-[11px]">
          <div className="flex items-baseline gap-1"><dt>Volume</dt><dd className="font-semibold text-foreground">{formatVol(avgVol)}</dd></div>
          <div className="flex items-baseline gap-1"><dt>Market cap</dt><dd className="font-semibold text-foreground">{formatMarketCap(marketcap)}</dd></div>
          <div className="flex items-baseline gap-1"><dt>From 52w high</dt><dd className={cn("font-semibold", pctClass(off52w !== null ? -off52w : null))}>{off52w !== null ? `-${off52w.toFixed(1)}%` : "—"}</dd></div>
          <div className="flex items-baseline gap-1"><dt>ATR</dt><dd className="font-semibold text-foreground">{formatSignedPct(atrPct).replace("+", "")}</dd></div>
        </dl>
      </div>

      <div className="hidden min-w-0 items-center justify-end gap-2 sm:flex">
        <label className="flex min-w-0 items-center gap-2 text-xs font-medium text-muted-foreground">
          <span>As of</span>{dateControl}
        </label>
        {trailing}
      </div>
      {trailing && <div className="flex justify-end sm:hidden">{trailing}</div>}
    </header>
  );
}
