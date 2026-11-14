import { useState, useRef, useEffect, useMemo } from "react";
import { cn } from "../../lib/utils";

interface DateNavigatorProps {
  currentDate: string;
  availableDates: string[]; // Descending order (newest first)
  onChangeDate: (date: string) => void;
  className?: string;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

export function DateNavigator({
  currentDate,
  availableDates,
  onChangeDate,
  className,
}: DateNavigatorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Set of available trading dates for fast lookup
  const dateSet = useMemo(() => new Set(availableDates), [availableDates]);

  // Current index in sorted descending dates list (0 = latest)
  const currentIndex = useMemo(() => {
    const idx = availableDates.indexOf(currentDate);
    return idx >= 0 ? idx : 0;
  }, [availableDates, currentDate]);

  const isLatest = currentIndex === 0;
  const isOldest = currentIndex === availableDates.length - 1;

  // Distinct available years in dataset (newest first)
  const availableYears = useMemo(() => {
    const years = new Set<number>();
    availableDates.forEach((d) => {
      const y = parseInt(d.slice(0, 4), 10);
      if (!isNaN(y)) years.add(y);
    });
    if (years.size === 0) years.add(new Date().getFullYear());
    return Array.from(years).sort((a, b) => b - a);
  }, [availableDates]);

  // Calendar display state (year and month for the calendar grid)
  const [calYear, setCalYear] = useState(() => {
    if (currentDate) {
      const y = parseInt(currentDate.slice(0, 4), 10);
      if (!isNaN(y)) return y;
    }
    return availableYears[0] || new Date().getFullYear();
  });

  const [calMonth, setCalMonth] = useState(() => {
    if (currentDate) {
      const m = parseInt(currentDate.slice(5, 7), 10) - 1;
      if (!isNaN(m) && m >= 0 && m <= 11) return m;
    }
    return new Date().getMonth();
  });

  // Sync calendar view when currentDate changes externally
  useEffect(() => {
    if (currentDate) {
      const y = parseInt(currentDate.slice(0, 4), 10);
      const m = parseInt(currentDate.slice(5, 7), 10) - 1;
      if (!isNaN(y) && !isNaN(m)) {
        setCalYear(y);
        setCalMonth(m);
      }
    }
  }, [currentDate]);

  // Click outside listener
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        isOpen &&
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen]);

  // Step helper
  const stepByTradingDays = (daysOffset: number) => {
    const newIdx = currentIndex + daysOffset;
    if (newIdx >= 0 && newIdx < availableDates.length) {
      onChangeDate(availableDates[newIdx]);
    }
  };

  // Calendar month days calculation
  const calendarDays = useMemo(() => {
    const firstDayOfMonth = new Date(calYear, calMonth, 1);
    const lastDayOfMonth = new Date(calYear, calMonth + 1, 0);

    // Day of week: 0 is Sunday, 1 is Monday... convert to Monday=0..Sunday=6
    let startDayOfWeek = firstDayOfMonth.getDay() - 1;
    if (startDayOfWeek === -1) startDayOfWeek = 6;

    const days: { dateStr: string; dayNum: number; isCurrentMonth: boolean; isTradingDay: boolean }[] = [];

    // Previous month filler days
    const prevMonthLastDay = new Date(calYear, calMonth, 0).getDate();
    for (let i = startDayOfWeek - 1; i >= 0; i--) {
      const d = prevMonthLastDay - i;
      const prevMonth = calMonth === 0 ? 11 : calMonth - 1;
      const prevYear = calMonth === 0 ? calYear - 1 : calYear;
      const dateStr = `${prevYear}-${String(prevMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      days.push({
        dateStr,
        dayNum: d,
        isCurrentMonth: false,
        isTradingDay: dateSet.has(dateStr),
      });
    }

    // Current month days
    for (let d = 1; d <= lastDayOfMonth.getDate(); d++) {
      const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      days.push({
        dateStr,
        dayNum: d,
        isCurrentMonth: true,
        isTradingDay: dateSet.has(dateStr),
      });
    }

    // Next month filler days to complete grid (up to 42 cells = 6 weeks)
    const remaining = 42 - days.length;
    for (let d = 1; d <= remaining; d++) {
      const nextMonth = calMonth === 11 ? 0 : calMonth + 1;
      const nextYear = calMonth === 11 ? calYear + 1 : calYear;
      const dateStr = `${nextYear}-${String(nextMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      days.push({
        dateStr,
        dayNum: d,
        isCurrentMonth: false,
        isTradingDay: dateSet.has(dateStr),
      });
    }

    return days;
  }, [calYear, calMonth, dateSet]);

  // Formatted day of week name (e.g. "Fri")
  const dayOfWeekName = useMemo(() => {
    if (!currentDate) return "";
    try {
      const parts = currentDate.split("-").map(Number);
      const dt = new Date(parts[0], parts[1] - 1, parts[2]);
      return dt.toLocaleDateString("en-US", { weekday: "short" });
    } catch {
      return "";
    }
  }, [currentDate]);

  // Jump to nearest trading date if clicking a weekend or unindexed date
  const handleSelectDay = (dateStr: string) => {
    if (dateSet.has(dateStr)) {
      onChangeDate(dateStr);
      setIsOpen(false);
      return;
    }
    // Find nearest earlier available date
    const nearest = availableDates.find((d) => d <= dateStr);
    if (nearest) {
      onChangeDate(nearest);
      setIsOpen(false);
    }
  };

  const handlePrevMonth = () => {
    if (calMonth === 0) {
      setCalMonth(11);
      setCalYear((y) => y - 1);
    } else {
      setCalMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (calMonth === 11) {
      setCalMonth(0);
      setCalYear((y) => y + 1);
    } else {
      setCalMonth((m) => m + 1);
    }
  };

  // Quick period preset helpers
  const handleJumpPreset = (
    preset: "latest" | "1d" | "1w" | "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "5y" | "ytd"
  ) => {
    if (availableDates.length === 0) return;

    if (preset === "latest") {
      onChangeDate(availableDates[0]);
    } else if (preset === "1d") {
      stepByTradingDays(1);
    } else if (preset === "1w") {
      stepByTradingDays(5);
    } else if (preset === "1m") {
      stepByTradingDays(21);
    } else if (preset === "3m") {
      stepByTradingDays(63);
    } else if (preset === "6m") {
      stepByTradingDays(126);
    } else if (preset === "1y") {
      stepByTradingDays(252);
    } else if (preset === "2y") {
      stepByTradingDays(504);
    } else if (preset === "3y") {
      stepByTradingDays(756);
    } else if (preset === "5y") {
      stepByTradingDays(1260);
    } else if (preset === "ytd") {
      const curYear = currentDate.slice(0, 4);
      const ytdDates = availableDates.filter((d) => d.startsWith(curYear));
      if (ytdDates.length > 0) {
        onChangeDate(ytdDates[ytdDates.length - 1]); // Earliest trading day of year
      }
    }
    setIsOpen(false);
  };

  return (
    <div className={cn("relative inline-flex items-center gap-1", className)}>
      {/* Quick Step Buttons */}
      <div className="inline-flex items-center rounded-md border border-line bg-surface p-0.5 shadow-xs">
        <button
          type="button"
          onClick={() => stepByTradingDays(5)}
          disabled={isOldest}
          title="Step back 1 week (-5 trading days)"
          className="rounded px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:bg-surface-sunk hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
        >
          ◀◀
        </button>
        <button
          type="button"
          onClick={() => stepByTradingDays(1)}
          disabled={isOldest}
          title="Step back 1 day (-1 trading day)"
          className="rounded px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:bg-surface-sunk hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
        >
          ◀
        </button>

        {/* Date Display & Popover Trigger */}
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setIsOpen((p) => !p)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[11px] font-semibold transition-all",
            isOpen
              ? "bg-accent/15 text-accent ring-1 ring-accent/30"
              : "hover:bg-surface-sunk text-ink"
          )}
          title="Click to open calendar & period navigation"
        >
          <span>📅</span>
          <span>{currentDate || "Select date"}</span>
          {dayOfWeekName && (
            <span className="text-[10px] text-ink-muted font-sans font-normal">
              ({dayOfWeekName})
            </span>
          )}
          <span className="text-[9px] text-ink-muted">▾</span>
        </button>

        <button
          type="button"
          onClick={() => stepByTradingDays(-1)}
          disabled={isLatest}
          title="Step forward 1 day (+1 trading day)"
          className="rounded px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:bg-surface-sunk hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
        >
          ▶
        </button>
        <button
          type="button"
          onClick={() => stepByTradingDays(-5)}
          disabled={isLatest}
          title="Step forward 1 week (+5 trading days)"
          className="rounded px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:bg-surface-sunk hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
        >
          ▶▶
        </button>
      </div>

      {/* Quick Jump to Latest Button (if not on latest) */}
      {!isLatest && (
        <button
          type="button"
          onClick={() => handleJumpPreset("latest")}
          className="rounded border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-[10px] font-bold text-accent hover:bg-accent/20 transition-all"
          title="Jump to latest available trading date"
        >
          ⚡ Latest
        </button>
      )}

      {/* Calendar & Period Navigation Popover */}
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute right-0 top-full z-50 mt-1.5 flex flex-col gap-3 rounded-xl border border-accent/40 bg-surface p-3.5 shadow-2xl ring-1 ring-black/10 animate-in fade-in zoom-in-95 duration-100 min-w-[340px]"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-line pb-2">
            <div>
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-accent">
                As-Of Date Navigation
              </h4>
              <span className="text-[10px] text-ink-muted">
                {availableDates.length} trading sessions in ClickHouse ({availableDates[availableDates.length - 1]} → {availableDates[0]})
              </span>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded p-1 text-xs text-ink-muted hover:bg-surface-sunk hover:text-ink"
            >
              ✕
            </button>
          </div>

          {/* Quick Period Presets */}
          <div>
            <div className="text-[9.5px] font-bold uppercase tracking-wider text-ink-muted mb-1">
              Quick Period Jumps:
            </div>
            <div className="grid grid-cols-5 gap-1 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => handleJumpPreset("latest")}
                className="rounded border border-line bg-surface-sunk px-1 py-1 text-center font-bold text-accent hover:border-accent hover:bg-accent/10 transition-colors"
              >
                ⚡ Latest
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("1w")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -1 Week
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("1m")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -1 Month
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("3m")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -3 Months
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("6m")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -6 Months
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("1y")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -1 Year
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("2y")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -2 Years
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("3y")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -3 Years
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("5y")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                -5 Years
              </button>
              <button
                type="button"
                onClick={() => handleJumpPreset("ytd")}
                className="rounded border border-line bg-surface px-1 py-1 text-center text-ink-muted hover:border-accent hover:text-ink transition-colors"
              >
                YTD Start
              </button>
            </div>
          </div>

          {/* Month & Year Jump Selector */}
          <div className="flex items-center justify-between border-t border-line pt-2">
            <button
              type="button"
              onClick={handlePrevMonth}
              className="rounded p-1 text-xs text-ink-muted hover:bg-surface-sunk hover:text-ink transition-colors"
              title="Previous Month"
            >
              ◀
            </button>
            <div className="flex items-center gap-1.5">
              <select
                value={calMonth}
                onChange={(e) => setCalMonth(Number(e.target.value))}
                className="rounded border border-line bg-surface px-2 py-0.5 font-sans text-[11px] font-bold text-ink focus:border-accent focus:outline-none cursor-pointer"
              >
                {MONTH_NAMES.map((m, idx) => (
                  <option key={m} value={idx}>{m}</option>
                ))}
              </select>

              <select
                value={calYear}
                onChange={(e) => setCalYear(Number(e.target.value))}
                className="rounded border border-line bg-surface px-2 py-0.5 font-mono text-[11px] font-bold text-accent focus:border-accent focus:outline-none cursor-pointer"
              >
                {availableYears.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={handleNextMonth}
              className="rounded p-1 text-xs text-ink-muted hover:bg-surface-sunk hover:text-ink transition-colors"
              title="Next Month"
            >
              ▶
            </button>
          </div>

          {/* Mini Calendar Grid */}
          <div>
            <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-bold text-ink-muted mb-1">
              {DAY_LABELS.map((d) => (
                <div key={d} className="py-0.5">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {calendarDays.map((cell, idx) => {
                const isSelected = cell.dateStr === currentDate;
                const isAvailable = cell.isTradingDay;

                return (
                  <button
                    key={`${cell.dateStr}-${idx}`}
                    type="button"
                    onClick={() => handleSelectDay(cell.dateStr)}
                    disabled={!isAvailable && !cell.isCurrentMonth}
                    className={cn(
                      "flex h-6 w-full items-center justify-center rounded text-[11px] font-mono transition-all",
                      isSelected
                        ? "bg-accent font-bold text-accent-ink shadow-xs"
                        : isAvailable
                        ? cell.isCurrentMonth
                          ? "bg-surface-sunk font-semibold text-ink hover:bg-accent/20 hover:text-accent cursor-pointer"
                          : "text-ink-muted/50 hover:bg-surface-sunk cursor-pointer"
                        : "text-ink-muted/20 cursor-not-allowed"
                    )}
                    title={
                      isSelected
                        ? `Selected Date: ${cell.dateStr}`
                        : isAvailable
                        ? `Available Trading Date: ${cell.dateStr}`
                        : `No Market Data: ${cell.dateStr}`
                    }
                  >
                    {cell.dayNum}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Footer Direct Input */}
          <div className="flex items-center justify-between border-t border-line pt-2 text-[10px] text-ink-muted">
            <span className="font-mono">Direct Input:</span>
            <input
              type="date"
              value={currentDate}
              onChange={(e) => {
                if (e.target.value) handleSelectDay(e.target.value);
              }}
              className="rounded border border-line bg-surface-sunk px-2 py-0.5 font-mono text-[10.5px] text-ink focus:border-accent focus:outline-none cursor-pointer"
            />
          </div>
        </div>
      )}
    </div>
  );
}
