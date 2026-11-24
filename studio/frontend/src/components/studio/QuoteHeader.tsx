import type { FormEvent, ReactNode } from "react";
import type { StockIntrospectionData } from "../../types";
import { BookmarkButton } from "./BookmarkButton";
import { cn } from "../../lib/utils";
import { Button, TextInput } from "../ui/primitives";

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
    <div className="quote-header">
      <div className="quote-header-main">
        {showSearch && (
          <form onSubmit={handleSearchSubmit} className="quote-search">
            <TextInput
              type="text"
              value={searchValue ?? ticker}
              onChange={(e) => onSearchChange?.(e.target.value.toUpperCase())}
              placeholder="Ticker"
              aria-label="Ticker symbol"
              className="h-9 min-h-9 w-[5.5rem] px-2 font-mono font-bold uppercase"
            />
            <Button
              type="submit"
              variant="secondary"
              className="min-h-9 px-2 text-xs"
            >
              Go
            </Button>
          </form>
        )}

        <div className="quote-instrument">
          <span className="text-base font-bold text-ink">{ticker}</span>
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

        <label className="quote-asof"><span>As of</span>{onAsOfDateChange ? <TextInput type="date" value={asOfDate}
          onChange={(e) => onAsOfDateChange(e.target.value)} className="h-9 min-h-9 w-auto px-2 py-1 font-mono text-xs" /> : <strong>{asOfDate}</strong>}</label>
        {trailing}
      </div>

      <div className="quote-header-metrics" aria-label="Key market metrics">
        <span className="quote-metric quote-price">{close !== null ? `$${close.toFixed(2)}` : "—"}<span className={cn("font-bold", pctClass(perf5d))}>{formatSignedPct(perf5d)}</span></span>
        <span className="quote-metric">Vol <strong>{formatVol(avgVol)}</strong></span>
        <span className="quote-metric">Mkt <strong>{formatMarketCap(marketcap)}</strong></span>
        <span className="quote-metric">52w <strong className={pctClass(off52w !== null ? -off52w : null)}>{off52w !== null ? `-${off52w.toFixed(1)}%` : "—"}</strong></span>
        <span className="quote-metric">ATR <strong>{formatSignedPct(atrPct).replace("+", "")}</strong></span>
      </div>
    </div>
  );
}
