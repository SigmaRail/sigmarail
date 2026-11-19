import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useWatchlists,
  WatchlistFlagColor,
  addRecentlyViewed,
} from "../../lib/watchlistStore";
import { fetchStockIntrospection } from "../../api/screens";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";

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

function WatchlistPicker({
  watchlists,
  value,
  onChange,
  compact = false,
}: {
  watchlists: ReturnType<typeof useWatchlists>["watchlists"];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={cn("min-w-0 font-mono text-xs font-bold", compact && "h-7 px-2 text-[10px]")}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent align="start">
        {watchlists.map((watchlist) => (
          <SelectItem key={watchlist.id} value={watchlist.id}>
            {watchlist.name} ({watchlist.symbols.length})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

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
        <Button
          type="button"
          onClick={onToggleOpen}
          variant="ghost"
          size="sm"
          className={cn(
            "flex h-7 w-full flex-shrink-0 items-center justify-center gap-1.5 border-t border-line bg-surface-raised font-mono text-[10px] font-bold text-accent hover:bg-surface-sunk",
            className,
          )}
          title="Open watchlist strip"
          aria-label="Open watchlist strip"
        >
          <span>📑 Watchlist</span>
          <span className="rounded bg-accent/20 px-1 text-[9.5px]">{symbols.length}</span>
        </Button>
      );
    }
    return (
      <Button
        type="button"
        onClick={onToggleOpen}
        variant="outline"
        size="sm"
        className="fixed right-0 top-16 z-30 flex items-center gap-1 rounded-l-lg border-y border-l border-line bg-surface-raised px-2 py-1.5 font-mono text-[11px] font-bold text-accent shadow-lg hover:bg-surface-sunk transition-all"
        title="Open Watchlist Dock ([)"
      >
        <span>📑</span>
        <span className="hidden sm:inline">Watchlist</span>
        <span className="rounded bg-accent/20 px-1 py-0.2 text-[9.5px] text-accent">
          {symbols.length}
        </span>
      </Button>
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
          <WatchlistPicker watchlists={watchlists} value={activeWatchlistId} onChange={setActiveWatchlistId} compact />
          <Button
            type="button"
            onClick={() => setShowImportModal(true)}
            variant="outline"
            size="sm"
            className="h-7 px-1.5 text-[10px]"
          >
            Paste
          </Button>
          <span className="ml-auto font-mono text-[9.5px] text-ink-muted">Space / ↓ cycle</span>
          <Button
            type="button"
            onClick={onToggleOpen}
            variant="ghost"
            size="sm"
            className="h-7 px-1.5 text-[10px]"
          >
            Hide
          </Button>
        </div>
        <div className="flex flex-1 overflow-x-auto divide-x divide-line/60">
          {filteredSymbols.length === 0 ? (
            <Button
              type="button"
              onClick={() => setShowImportModal(true)}
              variant="link"
              size="sm"
              className="h-auto px-3 py-2 text-[10.5px]"
            >
              Paste tickers
            </Button>
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
          <Dialog open={showImportModal} onOpenChange={setShowImportModal}>
            <DialogContent size="md" className="max-h-[85dvh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Bulk add symbols</DialogTitle>
                <DialogDescription>
                  Add tickers to “{activeWatchlist?.name}”. Separate them with commas, spaces, or new lines.
                </DialogDescription>
              </DialogHeader>
              <Textarea
                rows={5}
                placeholder="UBER, LYFT, DASH, NVDA, AAPL..."
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                autoFocus
                className="w-full font-mono text-xs"
              />
              <DialogFooter>
                <Button type="button" onClick={() => setShowImportModal(false)} variant="outline">
                  Cancel
                </Button>
                <Button type="button" onClick={handleImport} disabled={!importText.trim()}>
                  Add symbols
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
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
          <div className="min-w-0 flex-1">
            <WatchlistPicker watchlists={watchlists} value={activeWatchlistId} onChange={setActiveWatchlistId} />
          </div>

          {/* New List Button */}
          <Button
            type="button"
            onClick={() => setShowNewListModal(true)}
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="Create New Watchlist"
            aria-label="Create new watchlist"
          >
            ➕
          </Button>

          {/* Bulk Import Button */}
          <Button
            type="button"
            onClick={() => setShowImportModal(true)}
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="Paste Comma-Separated Symbols"
            aria-label="Import symbols"
          >
            📋
          </Button>

          {/* Export Button */}
          <Button
            type="button"
            onClick={handleCopyExport}
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="Copy Tickers to Clipboard"
            aria-label="Copy tickers to clipboard"
          >
            {copiedExport ? "✓" : "⬇"}
          </Button>

          {/* Close Dock */}
          <Button
            type="button"
            onClick={onToggleOpen}
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="Hide Watchlist Dock"
            aria-label="Hide watchlist dock"
          >
            ✕
          </Button>
        </div>

        {/* Flag Quick-Filter Strip */}
        <div className="flex items-center justify-between gap-1 pt-1 border-t border-line/60">
          <Button
            type="button"
            onClick={() => setFilterFlag("all")}
            variant={filterFlag === "all" ? "default" : "ghost"}
            size="sm"
            className={cn(
              "h-7 px-1.5 font-mono text-[10px]",
              filterFlag === "all" && "font-bold"
            )}
            aria-pressed={filterFlag === "all"}
          >
            All ({symbols.length})
          </Button>

          {(["red", "green", "yellow", "blue", "purple"] as WatchlistFlagColor[]).map((col) => {
            const count = symbols.filter((s) => s.flag === col).length;
            if (count === 0 && filterFlag !== col) return null;
            return (
              <Button
                key={col}
                type="button"
                onClick={() => setFilterFlag(filterFlag === col ? "all" : col)}
                variant={filterFlag === col ? "secondary" : "ghost"}
                size="sm"
                className={cn(
                  "h-7 gap-1 px-1.5 font-mono text-[10px]",
                  filterFlag === col && "font-bold"
                )}
                aria-pressed={filterFlag === col}
                aria-label={`Filter ${FLAG_COLORS[col].label} (${count})`}
              >
                <span className={cn("inline-block h-2 w-2 rounded-full", FLAG_COLORS[col].dot)} />
                <span>{count}</span>
              </Button>
            );
          })}

          {watchlists.length > 1 && (
            <Button
              type="button"
              onClick={() => {
                if (confirm(`Delete watchlist "${activeWatchlist?.name}"?`)) {
                  deleteWatchlist(activeWatchlistId);
                }
              }}
              variant="ghost"
              size="sm"
              className="ml-auto h-7 px-1.5 text-[10px] text-destructive"
              title="Delete Active Watchlist"
            >
              Delete
            </Button>
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
            <Button
              type="button"
              onClick={() => setShowImportModal(true)}
              variant="link"
              size="sm"
              className="h-auto px-2 text-[10.5px]"
            >
              Paste tickers (e.g. UBER, LYFT)
            </Button>
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
        <Dialog open={showNewListModal} onOpenChange={setShowNewListModal}>
          <DialogContent size="sm" className="max-h-[85dvh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Create watchlist</DialogTitle>
              <DialogDescription>Name this list so you can organize and revisit symbols.</DialogDescription>
            </DialogHeader>
            <Input
              type="text"
              placeholder="e.g. Breakout Compounders"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateList()}
              autoFocus
              className="w-full text-xs"
            />
            <DialogFooter>
              <Button
                type="button"
                onClick={() => setShowNewListModal(false)}
                variant="ghost"
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handleCreateList}
                disabled={!newListName.trim()}
              >
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <Dialog open={showImportModal} onOpenChange={setShowImportModal}>
          <DialogContent size="md" className="max-h-[85dvh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Bulk add symbols</DialogTitle>
              <DialogDescription>
                Add tickers to “{activeWatchlist?.name}”. Separate them with commas, spaces, or new lines.
              </DialogDescription>
            </DialogHeader>
            <Textarea
              rows={5}
              placeholder="UBER, LYFT, DASH, NVDA, AAPL..."
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              autoFocus
              className="w-full font-mono text-xs"
            />
            <DialogFooter>
              <Button
                type="button"
                onClick={() => setShowImportModal(false)}
                variant="ghost"
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handleImport}
                disabled={!importText.trim()}
              >
                Add symbols
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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
        <Button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onCycleFlag();
          }}
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 p-0.5"
          title={`Tag: ${flagInfo.label} (Click to cycle)`}
          aria-label={`Tag ${item.ticker}: ${flagInfo.label}`}
        >
          <span className={cn("block h-2.5 w-2.5 rounded-full transition-transform group-hover:scale-110", flagInfo.dot)} />
        </Button>

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
        <Button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
          title="Remove from Watchlist"
          aria-label={`Remove ${item.ticker} from watchlist`}
        >
          ✕
        </Button>
      </div>
    </div>
  );
}
