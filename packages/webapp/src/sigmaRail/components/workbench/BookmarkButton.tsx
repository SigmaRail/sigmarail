import { useState, useRef, useEffect } from "react";
import { useWatchlists } from "../../lib/watchlistStore";
import { cn } from "../../lib/utils";

interface BookmarkButtonProps {
  ticker: string;
  className?: string;
}

export function BookmarkButton({ ticker, className }: BookmarkButtonProps) {
  const { watchlists, activeWatchlistId, addSymbol, removeSymbol } = useWatchlists();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const clean = ticker.trim().toUpperCase();
  const isBookmarkedInActive = watchlists
    .find((w) => w.id === activeWatchlistId)
    ?.symbols.some((s) => s.ticker === clean);

  const isBookmarkedAnywhere = watchlists.some((w) => w.symbols.some((s) => s.ticker === clean));

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen]);

  const handleQuickToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isBookmarkedInActive) {
      removeSymbol(activeWatchlistId, clean);
    } else {
      addSymbol(activeWatchlistId, clean, "green");
    }
  };

  return (
    <div className={cn("relative inline-block", className)} ref={menuRef}>
      <div className="flex items-center">
        {/* Star Button */}
        <button
          type="button"
          onClick={handleQuickToggle}
          className={cn(
            "rounded p-1 transition-colors",
            isBookmarkedInActive
              ? "text-amber-400 hover:text-amber-300"
              : isBookmarkedAnywhere
              ? "text-amber-400/60 hover:text-amber-400"
              : "text-ink-muted hover:text-amber-400"
          )}
          title={isBookmarkedInActive ? `Remove ${clean} from active watchlist` : `Add ${clean} to active watchlist`}
        >
          {isBookmarkedInActive || isBookmarkedAnywhere ? "★" : "☆"}
        </button>

        {/* Dropdown Caret for multi-watchlist selection */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          className="p-0.5 text-[8px] text-ink-muted hover:text-ink transition-colors"
          title="Add to specific watchlist"
        >
          ▾
        </button>
      </div>

      {/* Multi-Watchlist Dropdown Menu */}
      {isOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute left-0 top-full mt-1 z-50 w-52 rounded-lg border border-line bg-surface p-1.5 shadow-xl font-mono text-[11px] space-y-1 animate-in fade-in zoom-in-95 duration-100"
        >
          <div className="px-2 py-1 text-[9.5px] uppercase font-bold text-ink-muted border-b border-line">
            Add {clean} to Watchlist:
          </div>

          <div className="max-h-48 overflow-y-auto space-y-0.5">
            {watchlists.map((w) => {
              const inList = w.symbols.some((s) => s.ticker === clean);
              return (
                <button
                  key={w.id}
                  type="button"
                  onClick={() => {
                    if (inList) {
                      removeSymbol(w.id, clean);
                    } else {
                      addSymbol(w.id, clean, "green");
                    }
                  }}
                  className="flex w-full items-center justify-between rounded px-2 py-1 text-left hover:bg-surface-sunk transition-colors"
                >
                  <span className="truncate">{w.name}</span>
                  <span className={cn("text-xs font-bold", inList ? "text-emerald-400" : "text-ink-muted")}>
                    {inList ? "✓" : "+"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
