import type { FormEvent, ReactNode } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";

interface QuoteHeaderProps {
  ticker: string;
  asOfDate: string;
  onAsOfDateChange?: (date: string) => void;
  showSearch?: boolean;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  onSearchSubmit?: (ticker: string) => void;
  trailing?: ReactNode;
}

export function QuoteHeader({
  ticker,
  asOfDate,
  onAsOfDateChange,
  showSearch = false,
  searchValue,
  onSearchChange,
  onSearchSubmit,
  trailing,
}: QuoteHeaderProps) {
  const handleSearchSubmit = (e: FormEvent) => {
    e.preventDefault();
    const next = (searchValue ?? ticker).trim().toUpperCase();
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
    <header
      data-testid="charts-quote-header"
      className="flex min-w-0 items-center gap-2 border-b border-border bg-background px-2 py-1.5 text-xs sm:px-3 sm:py-2"
    >
      <div className="flex min-w-0 items-center gap-2">
        {showSearch ? (
          <form onSubmit={handleSearchSubmit} className="flex min-w-0 items-center gap-1">
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
        ) : (
          <h1 className="truncate text-sm font-semibold text-foreground sm:text-base">{ticker}</h1>
        )}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <label className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground sm:gap-2 sm:text-xs">
          {dateControl}
        </label>
        {trailing}
      </div>
    </header>
  );
}
