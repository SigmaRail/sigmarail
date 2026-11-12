import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useWatchlists,
  WatchlistFlagColor,
  addRecentlyViewed,
} from "../../lib/watchlistStore";
import { fetchStockIntrospection } from "../../api/screens";
import { cn } from "../../lib/utils";

interface WatchlistSidebarProps {
  activeTicker: string;
  onSelectTicker: (ticker: string) => void;
  asOfDate: string;
  isOpen: boolean;
  onToggleOpen: () => void;
  className?: string;
  variant?: "sidebar" | "strip";
  quotesEnabled?: boolean;
}

const FLAG_COLORS: Record<WatchlistFlagColor, { dot: string; label: string; bg: string; text: string }> = {
  red: { dot: "bg-rose-500", label: "Priority Short/Alert", bg: "bg-rose-500/15", text: "text-rose-400" },
  green: { dot: "bg-emerald-500", label: "Ready Setup / Long", bg: "bg-emerald-500/15", text: "text-emerald-400" },
  yellow: { dot: "bg-amber-500", label: "Watching / Base", bg: "bg-amber-500/15", text: "text-amber-400" },
  blue: { dot: "bg-sky-500", label: "Moat / Blue Chip", bg: "bg-sky-500/15", text: "text-sky-400" },
  purple: { dot: "bg-purple-500", label: "Earnings / Event", bg: "bg-purple-500/15", text: "text-purple-400" },
  none: { dot: "bg-line hover:bg-ink-muted", label: "No Flag", bg: "bg-surface-sunk", text: "text-ink-muted" },
};

export function WatchlistSidebar({
  activeTicker,
  onSelectTicker,
  asOfDate,
  isOpen,
  onToggleOpen,
  className,
  variant = "sidebar",
  quotesEnabled = true,
}: WatchlistSidebarProps) {
  const {
    watchlists,
    activeWatchlistId,
    activeWatchlist,
    setActiveWatchlistId,
    createWatchlist,
    deleteWatchlist,
    removeSymbol,
    setSymbolFlag,
    importTickers,
    exportWatchlist,
  } = useWatchlists();

  const [filterFlag, setFilterFlag] = useState<WatchlistFlagColor | "all">("all");
  const [showNewListModal, setShowNewListModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [newListName, setNewListName] = useState("");
  const [importText, setImportText] = useState("");
  const [copiedExport, setCopiedExport] = useState(false);

  // Fetch summary batch telemetry for symbols in active watchlist
  const symbols = activeWatchlist?.symbols || [];
  const filteredSymbols = symbols.filter((s) => filterFlag === "all" || s.flag === filterFlag);

  // Keyboard navigation for symbol cycling
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!isOpen || filteredSymbols.length === 0) return;
      // Don't trigger if typing in an input or textarea
      if (["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName)) return;

      const currentIndex = filteredSymbols.findIndex((s) => s.ticker === activeTicker);

      if (e.code === "Space" || e.key === "ArrowDown") {
        e.preventDefault();
        const nextIndex = (currentIndex + 1) % filteredSymbols.length;
        const nextTicker = filteredSymbols[nextIndex]?.ticker;
        if (nextTicker) {
          onSelectTicker(nextTicker);
          addRecentlyViewed(nextTicker);
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prevIndex = (currentIndex - 1 + filteredSymbols.length) % filteredSymbols.length;
        const prevTicker = filteredSymbols[prevIndex]?.ticker;
        if (prevTicker) {
          onSelectTicker(prevTicker);
          addRecentlyViewed(prevTicker);
        }
      } else if (e.key === "1") {
        if (activeTicker) setSymbolFlag(activeWatchlistId, activeTicker, "red");
      } else if (e.key === "2") {
        if (activeTicker) setSymbolFlag(activeWatchlistId, activeTicker, "green");
      } else if (e.key === "3") {
        if (activeTicker) setSymbolFlag(activeWatchlistId, activeTicker, "yellow");
      } else if (e.key === "4") {
        if (activeTicker) setSymbolFlag(activeWatchlistId, activeTicker, "blue");
      } else if (e.key === "0" || e.key === "`") {
        if (activeTicker) setSymbolFlag(activeWatchlistId, activeTicker, "none");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, filteredSymbols, activeTicker, onSelectTicker, activeWatchlistId, setSymbolFlag]);

  const handleCreateList = () => {
    if (!newListName.trim()) return;
    createWatchlist(newListName.trim());
    setNewListName("");
    setShowNewListModal(false);
  };

  const handleImport = () => {
    if (!importText.trim()) return;
    importTickers(activeWatchlistId, importText);
    setImportText("");
    setShowImportModal(false);
  };

  const handleCopyExport = () => {
    const text = exportWatchlist(activeWatchlistId, "text");
    navigator.clipboard.writeText(text);
    setCopiedExport(true);
    setTimeout(() => setCopiedExport(false), 2000);
  };

  if (!isOpen) {
    if (variant === "strip") {
      return (
        <button
          type="button"
          onClick={onToggleOpen}
          className={cn(
            "flex h-7 w-full flex-shrink-0 items-center justify-center gap-1.5 border-t border-line bg-surface-raised font-mono text-[10px] font-bold text-accent hover:bg-surface-sunk",
            className,
          )}
          title="Open watchlist strip"
        >
          <span>📑 Watchlist</span>
          <span className="rounded bg-accent/20 px-1 text-[9.5px]">{symbols.length}</span>
        </button>
      );
    }
    return (
      <button
        type="button"
        onClick={onToggleOpen}
        className="fixed right-0 top-16 z-30 flex items-center gap-1 rounded-l-lg border-y border-l border-line bg-surface-raised px-2 py-1.5 font-mono text-[11px] font-bold text-accent shadow-lg hover:bg-surface-sunk transition-all"
        title="Open Watchlist Dock ([)"
      >
        <span>📑</span>
        <span className="hidden sm:inline">Watchlist</span>
        <span className="rounded bg-accent/20 px-1 py-0.2 text-[9.5px] text-accent">
          {symbols.length}
        </span>
      </button>
    );
  }

  if (variant === "strip") {
    return (
      <div
        className={cn(
          "flex h-28 w-full flex-shrink-0 flex-col border-t border-line bg-surface text-[11px]",
          className,
        )}
      >
        <div className="flex items-center gap-1.5 border-b border-line bg-surface-raised px-2 py-1">
          <select
            value={activeWatchlistId}
            onChange={(e) => setActiveWatchlistId(e.target.value)}
            className="rounded border border-line bg-surface px-2 py-0.5 font-mono text-[10px] font-bold text-ink focus:border-accent focus:outline-none"
          >
            {watchlists.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} ({w.symbols.length})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setShowImportModal(true)}
            className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:text-accent"
          >
            Paste
          </button>
          <span className="ml-auto font-mono text-[9.5px] text-ink-muted">Space / ↓ cycle</span>
          <button
            type="button"
            onClick={onToggleOpen}
            className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:text-ink"
          >
            Hide
          </button>
        </div>
        <div className="flex flex-1 overflow-x-auto divide-x divide-line/60">
          {filteredSymbols.length === 0 ? (
            <button
              type="button"
              onClick={() => setShowImportModal(true)}
              className="px-3 py-2 text-[10.5px] text-accent underline"
            >
              Paste tickers
            </button>
          ) : (
            filteredSymbols.map((item) => (
              <div key={item.ticker} className="min-w-[168px] max-w-[200px] flex-shrink-0">
                <WatchlistRow
                  item={item}
                  isActive={item.ticker === activeTicker}
                  asOfDate={asOfDate}
                  onSelect={() => {
                    onSelectTicker(item.ticker);
                    addRecentlyViewed(item.ticker);
                  }}
                  onCycleFlag={() => {
                    const order: WatchlistFlagColor[] = ["none", "green", "red", "yellow", "blue", "purple"];
                    const next = order[(order.indexOf(item.flag || "none") + 1) % order.length];
                    setSymbolFlag(activeWatchlistId, item.ticker, next);
                  }}
                  onRemove={() => removeSymbol(activeWatchlistId, item.ticker)}
                  quotesEnabled={quotesEnabled}
                />
              </div>
            ))
          )}
        </div>
        {showImportModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
            <div className="w-full max-w-md space-y-3 rounded-xl border border-line bg-surface p-4 shadow-2xl">
              <h3 className="text-sm font-bold text-ink">Bulk Add Symbols to "{activeWatchlist?.name}"</h3>
              <textarea
                rows={5}
                placeholder="UBER, LYFT, DASH, NVDA, AAPL..."
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                autoFocus
                className="w-full rounded border border-line bg-surface-sunk p-2.5 font-mono text-xs text-ink focus:border-accent focus:outline-none"
              />
              <div className="flex justify-end gap-2 text-xs">
                <button type="button" onClick={() => setShowImportModal(false)} className="rounded px-3 py-1 text-ink-muted hover:bg-surface-sunk">
                  Cancel
                </button>
                <button type="button" onClick={handleImport} className="rounded bg-accent px-3 py-1 font-bold text-white hover:bg-accent/90">
                  Add Symbols
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col w-72 sm:w-80 h-full border-l border-line bg-surface flex-shrink-0 select-none z-20 text-[11px]",
        className
      )}
    >
      {/* Header Controls */}
      <div className="flex flex-col gap-2 border-b border-line bg-surface-raised p-2.5">
        <div className="flex items-center justify-between gap-1.5">
          {/* Watchlist Picker */}
          <select
            value={activeWatchlistId}
            onChange={(e) => setActiveWatchlistId(e.target.value)}
            className="flex-1 rounded border border-line bg-surface px-2 py-1 font-mono text-xs font-bold text-ink focus:border-accent focus:outline-none"
          >
            {watchlists.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} ({w.symbols.length})
              </option>
            ))}
          </select>

          {/* New List Button */}
          <button
            type="button"
            onClick={() => setShowNewListModal(true)}
            className="rounded border border-line bg-surface p-1 text-ink-muted hover:text-accent hover:border-accent transition-colors"
            title="Create New Watchlist"
          >
            ➕
          </button>

          {/* Bulk Import Button */}
          <button
            type="button"
            onClick={() => setShowImportModal(true)}
            className="rounded border border-line bg-surface p-1 text-ink-muted hover:text-accent hover:border-accent transition-colors"
            title="Paste Comma-Separated Symbols"
          >
            📋
          </button>

          {/* Export Button */}
          <button
            type="button"
            onClick={handleCopyExport}
            className="rounded border border-line bg-surface p-1 text-ink-muted hover:text-accent hover:border-accent transition-colors"
            title="Copy Tickers to Clipboard"
          >
            {copiedExport ? "✓" : "⬇"}
          </button>

          {/* Close Dock */}
          <button
            type="button"
            onClick={onToggleOpen}
            className="rounded border border-line bg-surface p-1 text-ink-muted hover:text-ink transition-colors"
            title="Hide Watchlist Dock"
          >
            ✕
          </button>
        </div>

        {/* Flag Quick-Filter Strip */}
        <div className="flex items-center justify-between gap-1 pt-1 border-t border-line/60">
          <button
            type="button"
            onClick={() => setFilterFlag("all")}
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-mono transition-colors",
              filterFlag === "all" ? "bg-accent text-white font-bold" : "text-ink-muted hover:bg-surface-sunk"
            )}
          >
            All ({symbols.length})
          </button>

          {(["red", "green", "yellow", "blue", "purple"] as WatchlistFlagColor[]).map((col) => {
            const count = symbols.filter((s) => s.flag === col).length;
            if (count === 0 && filterFlag !== col) return null;
            return (
              <button
                key={col}
                type="button"
                onClick={() => setFilterFlag(filterFlag === col ? "all" : col)}
                className={cn(
                  "flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono transition-colors",
                  filterFlag === col ? "bg-surface-sunk border border-line font-bold" : "text-ink-muted hover:bg-surface-sunk"
                )}
              >
                <span className={cn("inline-block h-2 w-2 rounded-full", FLAG_COLORS[col].dot)} />
                <span>{count}</span>
              </button>
            );
          })}

          {watchlists.length > 1 && (
            <button
              type="button"
              onClick={() => {
                if (confirm(`Delete watchlist "${activeWatchlist?.name}"?`)) {
                  deleteWatchlist(activeWatchlistId);
                }
              }}
              className="ml-auto text-[10px] text-rose-400 hover:underline"
              title="Delete Active Watchlist"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Hotkey Hint Bar */}
      <div className="flex items-center justify-between px-2.5 py-1 bg-surface-sunk border-b border-line text-[9.5px] text-ink-muted font-mono">
        <span>Cycle: <strong className="text-ink">Space</strong> / <strong className="text-ink">↓</strong></span>
        <span>Flag: <strong className="text-ink">1-4</strong></span>
        <span>Unflag: <strong className="text-ink">0</strong></span>
      </div>

      {/* Symbols List */}
      <div className="flex-1 overflow-y-auto divide-y divide-line/60">
        {filteredSymbols.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-6 text-center text-ink-muted space-y-2">
            <span className="text-2xl">📑</span>
            <span className="text-xs font-semibold">No symbols in this view</span>
            <button
              type="button"
              onClick={() => setShowImportModal(true)}
              className="text-[10.5px] text-accent underline hover:text-white"
            >
              Paste tickers (e.g. UBER, LYFT)
            </button>
          </div>
        ) : (
          filteredSymbols.map((item) => (
            <WatchlistRow
              key={item.ticker}
              item={item}
              isActive={item.ticker === activeTicker}
              asOfDate={asOfDate}
              onSelect={() => {
                onSelectTicker(item.ticker);
                addRecentlyViewed(item.ticker);
              }}
              onCycleFlag={() => {
                const order: WatchlistFlagColor[] = ["none", "green", "red", "yellow", "blue", "purple"];
                const next = order[(order.indexOf(item.flag || "none") + 1) % order.length];
                setSymbolFlag(activeWatchlistId, item.ticker, next);
              }}
              onRemove={() => removeSymbol(activeWatchlistId, item.ticker)}
              quotesEnabled={quotesEnabled}
            />
          ))
        )}
      </div>

      {/* New List Modal */}
      {showNewListModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-sm rounded-xl border border-line bg-surface p-4 shadow-2xl space-y-3">
            <h3 className="font-bold text-sm text-ink">Create New Watchlist</h3>
            <input
              type="text"
              placeholder="e.g. Breakout Compounders"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateList()}
              autoFocus
              className="w-full rounded border border-line bg-surface-sunk px-3 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
            />
            <div className="flex justify-end gap-2 text-xs">
              <button
                type="button"
                onClick={() => setShowNewListModal(false)}
                className="rounded px-3 py-1 text-ink-muted hover:bg-surface-sunk"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreateList}
                className="rounded bg-accent px-3 py-1 font-bold text-white hover:bg-accent/90"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl border border-line bg-surface p-4 shadow-2xl space-y-3">
            <h3 className="font-bold text-sm text-ink">Bulk Add Symbols to "{activeWatchlist?.name}"</h3>
            <p className="text-[11px] text-ink-muted">
              Paste comma, space, or newline-separated tickers (e.g. <code className="text-accent">UBER, LYFT, DASH, CRM, NOW, NVDA</code>):
            </p>
            <textarea
              rows={5}
              placeholder="UBER, LYFT, DASH, NVDA, AAPL..."
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              autoFocus
              className="w-full rounded border border-line bg-surface-sunk p-2.5 font-mono text-xs text-ink focus:border-accent focus:outline-none"
            />
            <div className="flex justify-end gap-2 text-xs">
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className="rounded px-3 py-1 text-ink-muted hover:bg-surface-sunk"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleImport}
                className="rounded bg-accent px-3 py-1 font-bold text-white hover:bg-accent/90"
              >
                Add Symbols
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface WatchlistRowProps {
  item: { ticker: string; flag?: WatchlistFlagColor; note?: string };
  isActive: boolean;
  asOfDate: string;
  onSelect: () => void;
  onCycleFlag: () => void;
  onRemove: () => void;
  quotesEnabled?: boolean;
}

function WatchlistRow({
  item,
  isActive,
  asOfDate,
  onSelect,
  onCycleFlag,
  onRemove,
  quotesEnabled = true,
}: WatchlistRowProps) {
  // Lightweight overview query cached across symbols
  const infoQuery = useQuery({
    queryKey: ["stock-introspection-mini", item.ticker, asOfDate],
    queryFn: () => fetchStockIntrospection(item.ticker, asOfDate, 10, 10),
    staleTime: 300_000,
    enabled: quotesEnabled && !!item.ticker && !!asOfDate,
  });

  const data = infoQuery.data;
  const kpis = data?.as_of_kpis || {};
  const close = kpis.close !== undefined ? Number(kpis.close) : null;
  const rs = kpis.rs_rating !== undefined ? Number(kpis.rs_rating) : null;
  const valuation = data?.valuation_forecast;
  const flagInfo = FLAG_COLORS[item.flag || "none"];

  return (
    <div
      onClick={onSelect}
      className={cn(
        "group flex items-center justify-between px-2.5 py-1.5 cursor-pointer font-mono transition-colors",
        isActive
          ? "bg-accent/15 border-l-3 border-accent"
          : "hover:bg-surface-sunk"
      )}
    >
      {/* Left: Flag Dot + Ticker + Company Name */}
      <div className="flex items-center gap-2 min-w-0">
        {/* Clickable Flag Dot */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onCycleFlag();
          }}
          className="p-0.5 rounded hover:bg-surface transition-colors"
          title={`Tag: ${flagInfo.label} (Click to cycle)`}
        >
          <span className={cn("block h-2.5 w-2.5 rounded-full transition-transform group-hover:scale-110", flagInfo.dot)} />
        </button>

        <div className="flex flex-col min-w-0">
          <div className="flex items-baseline gap-1.5">
            <span className={cn("font-bold text-xs", isActive ? "text-accent" : "text-ink")}>
              {item.ticker}
            </span>
            {rs !== null && (
              <span
                className={cn(
                  "px-1 rounded text-[9px] font-bold",
                  rs >= 80 ? "bg-emerald-500/20 text-emerald-400" :
                  rs >= 70 ? "bg-sky-500/20 text-sky-400" :
                  "bg-surface-sunk text-ink-muted"
                )}
                title="RS Rating"
              >
                {rs.toFixed(0)}
              </span>
            )}
          </div>
          {data?.company_name && data.company_name !== item.ticker && (
            <span className="text-[9.5px] text-ink-muted truncate max-w-[110px]">
              {data.company_name}
            </span>
          )}
        </div>
      </div>

      {/* Right: Close Price & CAGR / Status */}
      <div className="flex items-center gap-2 text-right">
        <div className="flex flex-col items-end">
          <span className="text-xs font-bold text-ink">
            {close !== null ? `$${close.toFixed(2)}` : "—"}
          </span>
          {valuation?.fwd_cagr_2y_normal_pe !== undefined && valuation?.fwd_cagr_2y_normal_pe !== null ? (
            <span
              className={cn(
                "text-[9px] font-semibold",
                valuation.fwd_cagr_2y_normal_pe >= 15 ? "text-emerald-400" :
                valuation.fwd_cagr_2y_normal_pe > 0 ? "text-sky-300" : "text-rose-400"
              )}
              title="2Y Expected CAGR %"
            >
              {valuation.fwd_cagr_2y_normal_pe >= 0 ? "+" : ""}{valuation.fwd_cagr_2y_normal_pe.toFixed(0)}% / yr
            </span>
          ) : (
            <span className="text-[9px] text-ink-muted">
              {valuation?.valuation_status ? valuation.valuation_status.replace("Significantly ", "Sig. ").replace("Modestly ", "Mod. ") : "—"}
            </span>
          )}
        </div>

        {/* Delete Row Button */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="opacity-0 group-hover:opacity-100 p-1 text-[10px] text-ink-muted hover:text-rose-400 transition-opacity"
          title="Remove from Watchlist"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
