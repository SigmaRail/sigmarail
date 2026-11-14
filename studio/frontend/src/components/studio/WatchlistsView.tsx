import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useWatchlists,
  type WatchlistFlagColor,
  addRecentlyViewed,
} from "../../lib/watchlistStore";
import { fetchStockIntrospection } from "../../api/screens";
import { DataTable, type GridColumn } from "../../components/DataTable";
import { cn } from "../../lib/utils";
import type { StockIntrospectionData } from "../../types";

interface WatchlistsViewProps {
  onSelectTicker?: (ticker: string) => void;
  className?: string;
}

type WatchlistSourceType = "manual" | "screener" | "tradingview" | "deepvue" | "marketsmith" | "finviz";

interface WatchlistSourceMeta {
  type: WatchlistSourceType;
  label: string;
  icon: string;
  color: string;
  description: string;
}

const SOURCE_TYPES: Record<WatchlistSourceType, WatchlistSourceMeta> = {
  manual: {
    type: "manual",
    label: "Manual",
    icon: "✏️",
    color: "sky",
    description: "Manually maintained list",
  },
  screener: {
    type: "screener",
    label: "Screener",
    icon: "🔍",
    color: "emerald",
    description: "Auto-populated from screener results",
  },
  tradingview: {
    type: "tradingview",
    label: "TradingView",
    icon: "📊",
    color: "purple",
    description: "Synced from TradingView watchlist",
  },
  deepvue: {
    type: "deepvue",
    label: "Deepvue",
    icon: "🔬",
    color: "amber",
    description: "Imported from Deepvue screener",
  },
  marketsmith: {
    type: "marketsmith",
    label: "MarketSmith",
    icon: "🎯",
    color: "rose",
    description: "Imported from MarketSmith",
  },
  finviz: {
    type: "finviz",
    label: "FinViz",
    icon: "📈",
    color: "indigo",
    description: "Imported from FinViz",
  },
};

const FLAG_COLORS: Record<WatchlistFlagColor, { dot: string; label: string; bg: string; text: string }> = {
  red: { dot: "bg-rose-500", label: "Priority Short/Alert", bg: "bg-rose-500/15", text: "text-rose-400" },
  green: { dot: "bg-emerald-500", label: "Ready Setup / Long", bg: "bg-emerald-500/15", text: "text-emerald-400" },
  yellow: { dot: "bg-amber-500", label: "Watching / Base", bg: "bg-amber-500/15", text: "text-amber-400" },
  blue: { dot: "bg-sky-500", label: "Moat / Blue Chip", bg: "bg-sky-500/15", text: "text-sky-400" },
  purple: { dot: "bg-purple-500", label: "Earnings / Event", bg: "bg-purple-500/15", text: "text-purple-400" },
  none: { dot: "bg-line hover:bg-ink-muted", label: "No Flag", bg: "bg-surface-sunk", text: "text-ink-muted" },
};

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function WatchlistsView({
  onSelectTicker,
  className,
}: WatchlistsViewProps) {
  const {
    watchlists,
    activeWatchlistId,
    activeWatchlist,
    setActiveWatchlistId,
    createWatchlist,
    deleteWatchlist,
    renameWatchlist,
    addSymbol,
    removeSymbol,
    setSymbolFlag,
  } = useWatchlists();

  const [showNewListModal, setShowNewListModal] = useState(false);
  const [newListName, setNewListName] = useState("");
  const [selectedSourceType, setSelectedSourceType] = useState<WatchlistSourceType>("manual");
  const [showImportModal, setShowImportModal] = useState(false);
  const [importText, setImportText] = useState("");
  const [editingListId, setEditingListId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [filterFlag, setFilterFlag] = useState<WatchlistFlagColor | "all">("all");
  const [searchTicker, setSearchTicker] = useState("");

  // Fetch KPIs for all symbols in active watchlist
  const symbols = activeWatchlist?.symbols || [];
  const kpiQuery = useQuery({
    queryKey: ["watchlist-introspection", activeWatchlistId, symbols.map((s) => s.ticker).join(",")],
    queryFn: async () => {
      const results = await Promise.all(
        symbols.map(async (s) => {
          try {
            const data = await fetchStockIntrospection(s.ticker, todayIso(), 1000, 100);
            return { ticker: s.ticker, data };
          } catch {
            return { ticker: s.ticker, data: null };
          }
        }),
      );
      return results;
    },
    enabled: symbols.length > 0,
    staleTime: 300_000,
  });

  const kpiMap = useMemo(() => {
    const m = new Map<string, StockIntrospectionData>();
    (kpiQuery.data ?? []).forEach((r) => {
      if (r.data) m.set(r.ticker, r.data);
    });
    return m;
  }, [kpiQuery.data]);

  interface WatchlistRow {
    symbol: { ticker: string; flag?: WatchlistFlagColor; note?: string; added_at: string };
    kpis: StockIntrospectionData["as_of_kpis"];
    trend: StockIntrospectionData["trend_template"] | null;
    company: string;
  }

  // Rows for DataTable (respects flag + search filters)
  const rows: WatchlistRow[] = useMemo(() => {
    return symbols
      .filter((s) => {
        const matchesFlag = filterFlag === "all" || s.flag === filterFlag;
        const matchesSearch = !searchTicker || s.ticker.includes(searchTicker.toUpperCase());
        return matchesFlag && matchesSearch;
      })
      .map((s) => {
        const intro = kpiMap.get(s.ticker);
        return {
          symbol: s,
          kpis: intro?.as_of_kpis ?? {},
          trend: intro?.trend_template ?? null,
          company: intro?.company_name ?? "",
        };
      });
  }, [symbols, kpiMap, filterFlag, searchTicker]);

  const watchlistColumns: GridColumn<WatchlistRow>[] = useMemo(
    () => [
      {
        id: "ticker",
        label: "Ticker",
        align: "left",
        always: true,
        sortable: true,
        sticky: "left",
        widthClass: "min-w-[90px]",
        accessor: (r) => r.symbol.ticker,
        cell: (r) => <span className="font-bold text-accent tracking-wide">{r.symbol.ticker}</span>,
      },
      {
        id: "company",
        label: "Company",
        align: "left",
        accessor: (r) => r.company,
        cell: (r) => (
          <span className="font-sans text-ink">{r.company || "—"}</span>
        ),
      },
      {
        id: "flag",
        label: "Flag",
        align: "center",
        sortable: false,
        accessor: (r) => r.symbol.flag ?? "none",
        cell: (r) => (
          <button
            type="button"
            title={FLAG_COLORS[r.symbol.flag ?? "none"].label}
            onClick={(e) => {
              e.stopPropagation();
              const flags: WatchlistFlagColor[] = ["red", "green", "yellow", "blue", "purple", "none"];
              const cur = r.symbol.flag ?? "none";
              const idx = flags.indexOf(cur);
              setSymbolFlag(activeWatchlistId, r.symbol.ticker, flags[(idx + 1) % flags.length]);
            }}
            className={cn(
              "inline-block h-3 w-3 rounded-full transition-all hover:ring-2 hover:ring-offset-1 cursor-pointer",
              FLAG_COLORS[r.symbol.flag ?? "none"].dot,
            )}
          />
        ),
      },
      {
        id: "price",
        label: "Price",
        align: "right",
        format: "price",
        sortable: true,
        accessor: (r) => r.kpis.close ?? null,
      },
      {
        id: "chg",
        label: "% Chg",
        align: "right",
        sortable: false,
        accessor: (r) => {
          const fwd = r.kpis.forward_1d_pct ?? r.kpis.change_pct;
          return fwd ?? null;
        },
        cell: (_r, v) => {
          const n = Number(v);
          if (!Number.isFinite(n)) return <span className="text-ink-faint">—</span>;
          return (
            <span className={cn("font-bold", n >= 0 ? "text-emerald-500" : "text-rose-500")}>
              {n >= 0 ? "+" : ""}{n.toFixed(2)}%
            </span>
          );
        },
      },
      {
        id: "rs",
        label: "RS",
        align: "right",
        format: "int",
        sortable: true,
        accessor: (r) => r.kpis.rs_rating ?? null,
        cell: (_r, v) => {
          const n = Number(v);
          if (!Number.isFinite(n)) return <span className="text-ink-faint">—</span>;
          return (
            <span className={cn("font-bold", n >= 80 ? "text-emerald-500" : n >= 60 ? "text-sky-500" : "text-rose-400")}>
              {n.toFixed(0)}
            </span>
          );
        },
      },
      {
        id: "trend",
        label: "Trend",
        align: "center",
        sortable: false,
        accessor: (r) => (r.trend?.all_passed ? r.trend.passed_count : 0),
        cell: (r) => {
          if (!r.trend) return <span className="text-ink-faint">—</span>;
          return (
            <span
              className={cn(
                "rounded px-1.5 py-0.5 font-mono text-[10px] font-bold",
                r.trend.all_passed ? "bg-emerald-500/15 text-emerald-600" : "bg-surface-sunk text-ink-muted",
              )}
              title={r.trend.all_passed ? "Trend Template passed" : "Trend Template not met"}
            >
              {r.trend.passed_count}/8{r.trend.all_passed ? " ✓" : ""}
            </span>
          );
        },
      },
      {
        id: "stage",
        label: "Stage",
        align: "center",
        sortable: true,
        accessor: (r) => r.kpis.stage_code ?? null,
        cell: (_r, v) => {
          const code = typeof v === "string" ? v : "";
          if (!/^[1-4][AB]$/.test(code)) return <span className="text-ink-faint">—</span>;
          const stage = Number(code[0]);
          return (
            <span
              className={cn(
                "font-mono font-bold",
                stage === 2 ? "text-emerald-500" : stage === 4 ? "text-rose-500" : "text-amber-500",
              )}
            >
              {code}
            </span>
          );
        },
      },
      {
        id: "vol",
        label: "Vol vs 50d",
        align: "right",
        sortable: true,
        accessor: (r) => {
          const avg = Number(r.kpis.avg_vol_50d);
          const cur = Number(r.kpis.volume);
          if (!Number.isFinite(avg) || !Number.isFinite(cur) || avg === 0) return null;
          return (cur / avg) * 100;
        },
        cell: (_r, v) => {
          const n = Number(v);
          if (!Number.isFinite(n)) return <span className="text-ink-faint">—</span>;
          return (
            <span className={cn("font-bold", n >= 140 ? "text-emerald-500" : n <= 80 ? "text-amber-500" : "text-ink")}>
              {n.toFixed(0)}%
            </span>
          );
        },
      },
      {
        id: "atr",
        label: "ATR %",
        align: "right",
        sortable: true,
        accessor: (r) => r.kpis.atr_14_pct ?? null,
        cell: (_r, v) => {
          const n = Number(v);
          if (!Number.isFinite(n)) return <span className="text-ink-faint">—</span>;
          return <span className="font-mono">{n.toFixed(1)}%</span>;
        },
      },
      {
        id: "note",
        label: "Note",
        align: "left",
        sortable: false,
        accessor: (r) => r.symbol.note ?? null,
        cell: (_r, v) => (
          <span className="font-sans text-ink-muted truncate max-w-[14rem]">
            {v ? String(v) : "—"}
          </span>
        ),
      },
      {
        id: "added",
        label: "Added",
        align: "right",
        sortable: true,
        accessor: (r) => r.symbol.added_at,
        cell: (_r, v) => <span className="text-ink-muted">{v ? String(v) : "—"}</span>,
      },
      {
        id: "del",
        label: "Del",
        align: "center",
        sortable: false,
        always: true,
        sticky: "right",
        widthClass: "w-9",
        accessor: () => "",
        cell: (r) => (
          <button
            type="button"
            title="Remove from watchlist"
            onClick={(e) => {
              e.stopPropagation();
              removeSymbol(activeWatchlistId, r.symbol.ticker);
            }}
            className="rounded px-1.5 py-0.5 text-[10px] text-rose-400 opacity-50 hover:bg-rose-500/15 hover:opacity-100 transition-all cursor-pointer"
          >
            ✕
          </button>
        ),
      },
    ],
    [activeWatchlistId, setSymbolFlag, removeSymbol],
  );

  const handleSelectSymbol = (ticker: string) => {
    onSelectTicker?.(ticker);
    addRecentlyViewed(ticker);
  };

  const handleCreateList = () => {
    if (newListName.trim()) {
      createWatchlist(newListName, []);
      setNewListName("");
      setShowNewListModal(false);
    }
  };

  const handleImportTickers = () => {
    if (!importText.trim() || !activeWatchlistId) return;
    const tickers = importText
      .split(/[\s,\n]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    tickers.forEach((ticker) => addSymbol(activeWatchlistId, ticker));
    setImportText("");
    setShowImportModal(false);
  };

  const handleDeleteList = (id: string) => {
    if (confirm(`Delete watchlist "${watchlists.find((w) => w.id === id)?.name}"?`)) {
      deleteWatchlist(id);
    }
  };

  const handleStartRename = (id: string, currentName: string) => {
    setEditingListId(id);
    setEditingName(currentName);
  };

  const handleSaveRename = (id: string) => {
    if (editingName.trim()) {
      renameWatchlist(id, editingName);
    }
    setEditingListId(null);
    setEditingName("");
  };

  return (
    <div className={cn("flex h-[calc(100vh-3.5rem)] w-full flex-col overflow-hidden bg-canvas", className)}>
      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface px-4 py-2.5 text-xs">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-bold text-accent">📑 Watchlists</h2>
          <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10px] text-ink-muted">
            {watchlists.length} Lists
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNewListModal(true)}
            className="rounded-lg bg-accent px-3 py-1.5 font-mono text-xs font-bold text-white hover:bg-accent/90 transition-colors"
            title="Create a new watchlist"
          >
            ➕ New List
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            disabled={!activeWatchlistId}
            className="rounded-lg border border-line bg-surface px-3 py-1.5 font-mono text-xs font-bold text-ink-muted hover:bg-surface-sunk transition-colors disabled:opacity-50"
            title="Import tickers into active list"
          >
            📥 Import
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel: List Manager */}
        <div className="w-72 flex-shrink-0 border-r border-line bg-surface overflow-y-auto">
          <div className="space-y-1 p-3">
            {watchlists.length === 0 ? (
              <div className="px-3 py-8 text-center text-sm text-ink-muted">
                No watchlists yet. Create one to get started!
              </div>
            ) : (
              watchlists.map((list) => (
                <div
                  key={list.id}
                  onClick={() => setActiveWatchlistId(list.id)}
                  className={cn(
                    "group flex flex-col gap-1 rounded-lg border p-2.5 cursor-pointer transition-all",
                    activeWatchlistId === list.id
                      ? "border-accent bg-accent/10"
                      : "border-line bg-surface-sunk hover:border-accent/50"
                  )}
                >
                  {/* List Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      {editingListId === list.id ? (
                        <input
                          autoFocus
                          type="text"
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          onBlur={() => handleSaveRename(list.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveRename(list.id);
                            if (e.key === "Escape") {
                              setEditingListId(null);
                              setEditingName("");
                            }
                          }}
                          className="flex-1 rounded px-2 py-0.5 bg-surface-sunk border border-line text-xs font-bold text-ink focus:outline-none focus:border-accent"
                        />
                      ) : (
                        <div className="flex-1 min-w-0">
                          <h3 className="font-bold text-sm text-ink truncate">{list.name}</h3>
                          <p className="text-[9px] text-ink-muted truncate">{list.symbols.length} symbols</p>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {editingListId !== list.id && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleStartRename(list.id, list.name);
                            }}
                            className="rounded px-1.5 py-0.5 text-[10px] hover:bg-surface-raised"
                            title="Rename"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteList(list.id);
                            }}
                            className="rounded px-1.5 py-0.5 text-[10px] hover:bg-rose-500/15 text-rose-400"
                            title="Delete"
                          >
                            ✕
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Stats Row */}
                  {activeWatchlistId === list.id && (
                    <div className="grid grid-cols-2 gap-1 pt-1 border-t border-line/50 text-[9px]">
                      <div>
                        <span className="text-ink-muted">Last updated:</span>
                        <p className="text-ink-muted">{list.updated_at}</p>
                      </div>
                      <div>
                        <span className="text-ink-muted">Created:</span>
                        <p className="text-ink-muted">{list.created_at}</p>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Panel: List Contents & Details */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!activeWatchlist ? (
            <div className="flex h-full items-center justify-center text-ink-muted text-sm">
              Select or create a watchlist to get started
            </div>
          ) : (
            <>
              {/* Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-raised px-4 py-2.5 text-xs">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Search symbols..."
                    value={searchTicker}
                    onChange={(e) => setSearchTicker(e.target.value)}
                    className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-mono focus:border-accent focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-1.5">
                  {/* Flag Filter Buttons */}
                  <button
                    onClick={() => setFilterFlag("all")}
                    className={cn(
                      "rounded px-2.5 py-1 font-mono text-[10px] font-bold transition-colors",
                      filterFlag === "all"
                        ? "bg-accent/20 text-accent"
                        : "bg-surface hover:bg-surface-sunk text-ink-muted"
                    )}
                  >
                    All
                  </button>
                  {(["green", "yellow", "red", "blue", "purple", "none"] as WatchlistFlagColor[]).map((flag) => (
                    <button
                      key={flag}
                      onClick={() => setFilterFlag(flag)}
                      className={cn(
                        "rounded px-2 py-1 text-[10px] font-bold transition-colors",
                        filterFlag === flag
                          ? FLAG_COLORS[flag].bg + " " + FLAG_COLORS[flag].text
                          : "bg-surface hover:bg-surface-sunk text-ink-muted"
                      )}
                    >
                      <span className={cn("inline-block w-2 h-2 rounded-full mr-1", FLAG_COLORS[flag].dot)}></span>
                      {FLAG_COLORS[flag].label.split(" / ")[0]}
                    </button>
                  ))}
                </div>

                <div className="text-[10px] text-ink-muted">
                  {rows.length} / {symbols.length}
                </div>
              </div>

              {/* Symbols Table (reusable DataTable) */}
              <DataTable<WatchlistRow>
                rows={rows}
                columns={watchlistColumns}
                viewId={`watchlist.${activeWatchlistId}`}
                getRowId={(r) => r.symbol.ticker}
                onRowClick={(r) => handleSelectSymbol(r.symbol.ticker)}
                loading={kpiQuery.isLoading && rows.length > 0}
                emptyLabel="No symbols match your filters"
                density="compact"
                height="fill"
              />
            </>
          )}
        </div>
      </div>

      {/* New List Modal */}
      {showNewListModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
          <div className="rounded-lg border border-line bg-surface p-6 shadow-xl max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-ink mb-4">Create New Watchlist</h3>

            <div className="space-y-3 mb-6">
              <div>
                <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1.5">List Name</label>
                <input
                  autoFocus
                  type="text"
                  value={newListName}
                  onChange={(e) => setNewListName(e.target.value)}
                  placeholder="e.g., AI Growth Leaders"
                  className="w-full rounded-lg border border-line bg-surface-sunk px-3 py-2 text-sm focus:border-accent focus:outline-none"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreateList();
                  }}
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-ink-muted uppercase mb-1.5">Source Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.values(SOURCE_TYPES).map((source) => (
                    <button
                      key={source.type}
                      onClick={() => setSelectedSourceType(source.type)}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-center text-[10px] font-bold transition-all",
                        selectedSourceType === source.type
                          ? "border-accent bg-accent/15 text-accent"
                          : "border-line bg-surface-sunk text-ink-muted hover:border-line/80"
                      )}
                    >
                      <div>{source.icon}</div>
                      <div>{source.label}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-lg bg-surface-sunk p-3 text-[10px] text-ink-muted">
                <p className="font-bold mb-1">{SOURCE_TYPES[selectedSourceType].label}</p>
                <p>{SOURCE_TYPES[selectedSourceType].description}</p>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setShowNewListModal(false)}
                className="flex-1 rounded-lg border border-line bg-surface px-4 py-2 font-bold text-ink hover:bg-surface-sunk transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateList}
                disabled={!newListName.trim()}
                className="flex-1 rounded-lg bg-accent px-4 py-2 font-bold text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
          <div className="rounded-lg border border-line bg-surface p-6 shadow-xl max-w-md w-full mx-4">
            <h3 className="text-lg font-bold text-ink mb-4">Import Symbols</h3>

            <textarea
              autoFocus
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder="Paste symbols here (space, comma, or line-separated)&#10;NVDA UBER LYFT&#10;or&#10;NVDA, UBER, LYFT&#10;or&#10;NVDA&#10;UBER&#10;LYFT"
              className="w-full rounded-lg border border-line bg-surface-sunk px-3 py-2 text-sm font-mono focus:border-accent focus:outline-none resize-none h-32 mb-4"
            />

            <div className="flex gap-2">
              <button
                onClick={() => setShowImportModal(false)}
                className="flex-1 rounded-lg border border-line bg-surface px-4 py-2 font-bold text-ink hover:bg-surface-sunk transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleImportTickers}
                disabled={!importText.trim()}
                className="flex-1 rounded-lg bg-accent px-4 py-2 font-bold text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
              >
                Import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
