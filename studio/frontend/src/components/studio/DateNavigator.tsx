import { useEffect, useMemo, useState } from "react";
import { Calendar } from "@sb/webapp-core/components/ui/calendar/calendar.component";
import { Popover, PopoverContent, PopoverTrigger } from "@sb/webapp-core/components/ui/popover";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { cn } from "../../lib/utils";

interface DateNavigatorProps {
  currentDate: string;
  availableDates: string[]; // Descending order (newest first)
  onChangeDate: (date: string) => void;
  className?: string;
  /** Keep only the date picker when the surrounding workbench needs a compact toolbar. */
  compact?: boolean;
}

type DatePreset = "latest" | "1w" | "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "5y" | "ytd";

function fromIsoDate(value: string): Date | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return undefined;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function toIsoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function DateNavigator({
  currentDate,
  availableDates,
  onChangeDate,
  className,
  compact = false,
}: DateNavigatorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedDate = useMemo(() => fromIsoDate(currentDate), [currentDate]);
  const [calendarMonth, setCalendarMonth] = useState<Date>(
    () => selectedDate ?? new Date(),
  );

  useEffect(() => {
    if (selectedDate) setCalendarMonth(selectedDate);
  }, [selectedDate]);

  const dateSet = useMemo(() => new Set(availableDates), [availableDates]);
  const currentIndex = useMemo(() => {
    const index = availableDates.indexOf(currentDate);
    return index >= 0 ? index : 0;
  }, [availableDates, currentDate]);
  const isLatest = currentIndex === 0;
  const isOldest = currentIndex === availableDates.length - 1;

  const stepByTradingDays = (daysOffset: number) => {
    const nextIndex = currentIndex + daysOffset;
    if (nextIndex >= 0 && nextIndex < availableDates.length) {
      onChangeDate(availableDates[nextIndex]);
    }
  };

  const handleSelectDay = (date: Date | undefined) => {
    if (!date) return;
    const dateString = toIsoDate(date);
    if (dateSet.has(dateString)) {
      onChangeDate(dateString);
      setIsOpen(false);
      return;
    }
    // Keep the existing behavior for weekends and market holidays: choose the
    // closest earlier session represented in the point-in-time dataset.
    const nearest = availableDates.find((available) => available <= dateString);
    if (nearest) {
      onChangeDate(nearest);
      setIsOpen(false);
    }
  };

  const handleJumpPreset = (preset: DatePreset) => {
    if (availableDates.length === 0) return;
    if (preset === "latest") {
      onChangeDate(availableDates[0]);
    } else if (preset === "ytd") {
      const year = currentDate.slice(0, 4);
      const datesInYear = availableDates.filter((date) => date.startsWith(year));
      if (datesInYear.length > 0) onChangeDate(datesInYear[datesInYear.length - 1]);
    } else {
      const offsets: Record<Exclude<DatePreset, "latest" | "ytd">, number> = {
        "1w": 5,
        "1m": 21,
        "3m": 63,
        "6m": 126,
        "1y": 252,
        "2y": 504,
        "3y": 756,
        "5y": 1260,
      };
      stepByTradingDays(offsets[preset]);
    }
    setIsOpen(false);
  };

  const presets: { key: DatePreset; label: string }[] = [
    { key: "latest", label: "Latest" },
    { key: "1w", label: "−1 week" },
    { key: "1m", label: "−1 month" },
    { key: "3m", label: "−3 months" },
    { key: "6m", label: "−6 months" },
    { key: "1y", label: "−1 year" },
    { key: "2y", label: "−2 years" },
    { key: "3y", label: "−3 years" },
    { key: "5y", label: "−5 years" },
    { key: "ytd", label: "YTD start" },
  ];

  const latestDate = availableDates[0];
  const oldestDate = availableDates[availableDates.length - 1];

  return (
    <div className={cn("inline-flex min-w-0 items-center gap-1", className)}>
      <div className="inline-flex min-w-0 items-center rounded-md border border-border bg-background p-0.5">
        {!compact && (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => stepByTradingDays(5)}
              disabled={isOldest}
              title="Step back one week (five trading sessions)"
              aria-label="Step back one week"
              className="h-8 px-1.5 font-mono text-xs"
            >
              ◀◀
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => stepByTradingDays(1)}
              disabled={isOldest}
              title="Step back one trading session"
              aria-label="Step back one trading session"
              className="h-8 px-1.5 font-mono text-xs"
            >
              ◀
            </Button>
          </>
        )}
        <Popover open={isOpen} onOpenChange={setIsOpen}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              aria-label={`Choose as-of date, currently ${currentDate || "not set"}`}
              className="h-8 min-w-0 gap-1 px-2 font-mono text-[11px]"
            >
              <span aria-hidden="true">📅</span>
              <span className="truncate">{currentDate || "Select date"}</span>
              <span aria-hidden="true">▾</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align="end"
            side="bottom"
            sideOffset={6}
            className="max-h-[min(80dvh,680px)] w-[min(94vw,380px)] overflow-y-auto p-3"
          >
            <div className="mb-3 flex items-start justify-between gap-2 border-b pb-2">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold">As-of date</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {availableDates.length} trading sessions
                  {oldestDate && latestDate ? ` · ${oldestDate} to ${latestDate}` : ""}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Close date picker"
                onClick={() => setIsOpen(false)}
                className="h-8 w-8 shrink-0"
              >
                ×
              </Button>
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Quick jumps</p>
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {presets.map((preset) => (
                  <Button
                    key={preset.key}
                    type="button"
                    variant={preset.key === "latest" ? "secondary" : "outline"}
                    size="sm"
                    disabled={preset.key !== "latest" && preset.key !== "ytd" && availableDates.length === 0}
                    onClick={() => handleJumpPreset(preset.key)}
                    className="h-9 whitespace-normal px-2 text-xs"
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>

            <Calendar
              mode="single"
              selected={selectedDate}
              month={calendarMonth}
              onMonthChange={setCalendarMonth}
              onSelect={handleSelectDay}
              showYearNavigation
              weekStartsOn={1}
              startMonth={oldestDate ? fromIsoDate(oldestDate) : undefined}
              endMonth={latestDate ? fromIsoDate(latestDate) : undefined}
              className="mx-auto w-full p-1"
            />

            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
              <label htmlFor="as-of-date-direct" className="text-xs text-muted-foreground">
                Enter a date
              </label>
              <Input
                id="as-of-date-direct"
                type="date"
                value={currentDate}
                min={oldestDate}
                max={latestDate}
                onChange={(event) => {
                  if (event.target.value) {
                    const chosen = fromIsoDate(event.target.value);
                    if (chosen) handleSelectDay(chosen);
                  }
                }}
                className="h-9 w-auto min-w-[9.5rem]"
              />
            </div>
          </PopoverContent>
        </Popover>
        {!compact && (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => stepByTradingDays(-1)}
              disabled={isLatest}
              title="Step forward one trading session"
              aria-label="Step forward one trading session"
              className="h-8 px-1.5 font-mono text-xs"
            >
              ▶
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => stepByTradingDays(-5)}
              disabled={isLatest}
              title="Step forward one week (five trading sessions)"
              aria-label="Step forward one week"
              className="h-8 px-1.5 font-mono text-xs"
            >
              ▶▶
            </Button>
          </>
        )}
      </div>

      {!compact && !isLatest && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => handleJumpPreset("latest")}
          title="Jump to latest available trading date"
          className="h-8 shrink-0 px-2 text-xs"
        >
          Latest
        </Button>
      )}
    </div>
  );
}
