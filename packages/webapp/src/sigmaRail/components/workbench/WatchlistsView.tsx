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
import { PageHeadline } from "@sb/webapp-core/components/pageHeadline";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@sb/webapp-core/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

interface WatchlistsViewProps {
  onSelectTicker?: (ticker: string) => void;
  className?: string;
}

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

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

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
  const [showImportModal, setShowImportModal] = useState(false);
  const [importText, setImportText] = useState("");
  const [renameListId, setRenameListId] = useState<string | null>(null);
  const [renameName, setRenameName] = useState("");
  const [deleteListId, setDeleteListId] = useState<string | null>(null);
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
            <Button
            type="button"
            title={FLAG_COLORS[r.symbol.flag ?? "none"].label}
            onClick={(e) => {
              e.stopPropagation();
              const flags: WatchlistFlagColor[] = ["red", "green", "yellow", "blue", "purple", "none"];
              const cur = r.symbol.flag ?? "none";
              const idx = flags.indexOf(cur);
              setSymbolFlag(activeWatchlistId, r.symbol.ticker, flags[(idx + 1) % flags.length]);
            }}
            className="h-9 w-9 p-0 transition-all hover:ring-2 hover:ring-offset-1"
            variant="ghost"
            size="icon"
            aria-label={`Change ${r.symbol.ticker} flag`}
          >
            <span className={cn("h-2.5 w-2.5 rounded-full", FLAG_COLORS[r.symbol.flag ?? "none"].dot)} />
          </Button>
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
          <Button
            type="button"
            title="Remove from watchlist"
            onClick={(e) => {
              e.stopPropagation();
              removeSymbol(activeWatchlistId, r.symbol.ticker);
            }}
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            aria-label={`Remove ${r.symbol.ticker} from watchlist`}
          >
            ✕
          </Button>
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
    setDeleteListId(id);
  };

  const handleStartRename = (id: string, currentName: string) => {
    setRenameListId(id);
    setRenameName(currentName);
  };

  const handleSaveRename = (id: string) => {
    if (renameName.trim()) {
      renameWatchlist(id, renameName);
    }
    setRenameListId(null);
    setRenameName("");
  };

  const handleCycleFlag = (row: WatchlistRow) => {
    const flags: WatchlistFlagColor[] = ["red", "green", "yellow", "blue", "purple", "none"];
    const current = row.symbol.flag ?? "none";
    setSymbolFlag(activeWatchlistId, row.symbol.ticker, flags[(flags.indexOf(current) + 1) % flags.length]);
  };

  const activeDeleteList = watchlists.find((list) => list.id === deleteListId);

  return (
    <div className={cn("flex h-full min-h-0 w-full flex-col overflow-hidden bg-background", className)}>
      <header className="flex flex-wrap items-end justify-between gap-3 border-b bg-background px-3 py-3 sm:px-4">
        <PageHeadline
          header="Watchlists"
          subheader="Keep a focused list of symbols and review their latest market context."
          className="space-y-1"
        />

        <div className="flex items-center gap-2">
          <Badge variant="muted">{watchlists.length} {watchlists.length === 1 ? "list" : "lists"}</Badge>
          <Button
            type="button"
            onClick={() => setShowNewListModal(true)}
            size="sm"
            title="Create a new watchlist"
          >
            New list
          </Button>
          <Button
            type="button"
            onClick={() => setShowImportModal(true)}
            disabled={!activeWatchlistId}
            variant="outline"
            size="sm"
            title="Import tickers into active list"
          >
            Import symbols
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        {/* Left Panel: List Manager */}
        <div className="hidden flex-shrink-0 overflow-y-auto border-r border-line bg-surface lg:block lg:w-72 lg:p-3">
          <div className="space-y-2">
            {watchlists.length === 0 ? (
              <div className="min-w-56 rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground lg:min-w-0">
                No watchlists yet. Create one to begin.
              </div>
            ) : (
              watchlists.map((list) => (
                <Card key={list.id} className={cn(
                  "min-w-0 p-2 shadow-none",
                  activeWatchlistId === list.id && "border-primary/60 bg-accent/5",
                )}>
                  <div className="flex min-w-0 items-center gap-1">
                    <Button
                      type="button"
                      onClick={() => setActiveWatchlistId(list.id)}
                      variant={activeWatchlistId === list.id ? "secondary" : "ghost"}
                      className="h-auto min-h-10 min-w-0 flex-1 justify-start px-2 py-1.5 text-left"
                      aria-current={activeWatchlistId === list.id ? "page" : undefined}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{list.name}</span>
                        <span className="block text-xs font-normal text-muted-foreground">{list.symbols.length} symbols</span>
                      </span>
                    </Button>
                    <WatchlistActions
                      name={list.name}
                      onRename={() => handleStartRename(list.id, list.name)}
                      onDelete={() => handleDeleteList(list.id)}
                    />
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>

        {/* Right Panel: List Contents & Details */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {!activeWatchlist ? (
            <div className="flex h-full items-center justify-center text-ink-muted text-sm">
              Select or create a watchlist to get started
            </div>
          ) : (
            <>
              <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 border-b border-line bg-surface p-3 lg:hidden">
                <Select value={activeWatchlistId} onValueChange={setActiveWatchlistId}>
                  <SelectTrigger aria-label="Active watchlist" className="h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {watchlists.map((list) => (
                      <SelectItem key={list.id} value={list.id}>{list.name} · {list.symbols.length}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {activeWatchlist && (
                  <WatchlistActions
                    name={activeWatchlist.name}
                    onRename={() => handleStartRename(activeWatchlist.id, activeWatchlist.name)}
                    onDelete={() => handleDeleteList(activeWatchlist.id)}
                  />
                )}
              </div>

              {/* Toolbar */}
              <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-raised px-3 py-2.5 text-xs sm:justify-between sm:px-4">
                <div className="flex min-w-0 flex-1 items-center gap-2 sm:max-w-xs">
                  <Input
                    type="text"
                    placeholder="Search symbols"
                    aria-label="Search watchlist symbols"
                    value={searchTicker}
                    onChange={(e) => setSearchTicker(e.target.value)}
                    className="h-9"
                  />
                </div>

                <div className="hidden max-w-full flex-wrap items-center gap-1.5 lg:flex" role="group" aria-label="Filter symbols by flag">
                  {/* Flag Filter Buttons */}
                  <Button
                    type="button"
                    onClick={() => setFilterFlag("all")}
                    variant={filterFlag === "all" ? "secondary" : "ghost"}
                    size="sm"
                    className="h-8 px-2.5 text-xs"
                  >
                    All
                  </Button>
                  {(["green", "yellow", "red", "blue", "purple", "none"] as WatchlistFlagColor[]).map((flag) => (
                    <Button
                      type="button"
                      key={flag}
                      onClick={() => setFilterFlag(flag)}
                      variant={filterFlag === flag ? "secondary" : "ghost"}
                      size="sm"
                      className="h-8 px-2 text-xs"
                      aria-pressed={filterFlag === flag}
                    >
                      <span className={cn("inline-block h-2 w-2 rounded-full", FLAG_COLORS[flag].dot)} />
                      {FLAG_COLORS[flag].label.split(" / ")[0]}
                    </Button>
                  ))}
                </div>

                <Select value={filterFlag} onValueChange={(value) => setFilterFlag(value as WatchlistFlagColor | "all")}>
                  <SelectTrigger aria-label="Filter symbols by flag" className="h-9 w-36 lg:hidden">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All flags</SelectItem>
                    {(["green", "yellow", "red", "blue", "purple", "none"] as WatchlistFlagColor[]).map((flag) => (
                      <SelectItem key={flag} value={flag}>{FLAG_COLORS[flag].label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="text-[10px] text-ink-muted">
                  {rows.length} / {symbols.length}
                </div>
              </div>

              {/* Symbols Table (reusable DataTable) */}
              <div className="hidden min-h-0 flex-1 overflow-hidden lg:flex">
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
              </div>

              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3 lg:hidden">
                {kpiQuery.isLoading && <p className="text-xs text-muted-foreground">Loading latest metrics…</p>}
                {rows.length === 0 ? (
                  <Card className="p-5 text-center text-sm text-muted-foreground shadow-none">No symbols match these filters.</Card>
                ) : rows.map((row) => {
                  const flag = row.symbol.flag ?? "none";
                  const price = finiteNumber(row.kpis.close);
                  const change = finiteNumber(row.kpis.forward_1d_pct ?? row.kpis.change_pct);
                  const rs = finiteNumber(row.kpis.rs_rating);
                  const volume = finiteNumber(row.kpis.volume);
                  const avgVolume = finiteNumber(row.kpis.avg_vol_50d);
                  const atr = finiteNumber(row.kpis.atr_14_pct);
                  const volumeRatio = volume !== null && avgVolume !== null && avgVolume > 0 ? volume / avgVolume * 100 : null;
                  return (
                    <Card key={row.symbol.ticker} data-testid={`watchlist-card-${row.symbol.ticker}`} className="p-3 shadow-none">
                      <div className="flex min-w-0 items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <Button
                            type="button"
                            variant="link"
                            className="h-auto justify-start p-0 text-base font-semibold"
                            aria-label={`Open chart for ${row.symbol.ticker}`}
                            onClick={() => handleSelectSymbol(row.symbol.ticker)}
                          >
                            {row.symbol.ticker}
                          </Button>
                          <p className="truncate text-xs text-muted-foreground">{row.company || "Company details unavailable"}</p>
                        </div>
                        <Button type="button" variant="ghost" size="icon" className="h-9 w-9" aria-label={`Change ${row.symbol.ticker} flag`} title={FLAG_COLORS[flag].label} onClick={() => handleCycleFlag(row)}>
                          <span className={cn("h-3 w-3 rounded-full", FLAG_COLORS[flag].dot)} />
                        </Button>
                        <Button type="button" variant="ghost" size="icon" className="h-9 w-9 text-muted-foreground hover:text-destructive" aria-label={`Remove ${row.symbol.ticker} from watchlist`} onClick={() => removeSymbol(activeWatchlistId, row.symbol.ticker)}>×</Button>
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-2 border-y py-2">
                        <WatchlistMetric label="Price" value={price !== null ? `$${price.toFixed(2)}` : "—"} />
                        <WatchlistMetric label="Change" value={change !== null ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}%` : "—"} valueClass={change !== null ? change >= 0 ? "text-emerald-600" : "text-rose-600" : undefined} />
                        <WatchlistMetric label="RS" value={rs !== null ? rs.toFixed(0) : "—"} />
                      </div>
                      <details className="group pt-2">
                        <summary className="min-h-9 cursor-pointer list-none py-2 text-xs font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">More details <span className="float-right group-open:rotate-180">⌄</span></summary>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 border-t pt-2">
                          <WatchlistMetric label="Trend template" value={row.trend ? `${row.trend.passed_count}/8` : "—"} />
                          <WatchlistMetric label="Stage" value={typeof row.kpis.stage_code === "string" ? row.kpis.stage_code : "—"} />
                          <WatchlistMetric label="Volume vs 50d" value={volumeRatio === null ? "—" : `${volumeRatio.toFixed(0)}%`} />
                          <WatchlistMetric label="ATR" value={atr !== null ? `${atr.toFixed(1)}%` : "—"} />
                          <WatchlistMetric label="Added" value={row.symbol.added_at} />
                          <WatchlistMetric label="Note" value={row.symbol.note || "—"} />
                        </div>
                      </details>
                    </Card>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>

      <Dialog open={showNewListModal} onOpenChange={setShowNewListModal}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Create watchlist</DialogTitle>
            <DialogDescription>Give this list a name. You can add symbols after it is created.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label htmlFor="watchlist-name" className="text-sm font-medium">Name</label>
            <Input
              id="watchlist-name"
              autoFocus
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              placeholder="e.g. Growth candidates"
              onKeyDown={(e) => { if (e.key === "Enter") handleCreateList(); }}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowNewListModal(false)}>Cancel</Button>
            <Button type="button" onClick={handleCreateList} disabled={!newListName.trim()}>Create list</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameListId !== null} onOpenChange={(open) => !open && setRenameListId(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Rename watchlist</DialogTitle>
            <DialogDescription>Choose a short name that describes the symbols in this list.</DialogDescription>
          </DialogHeader>
          <label htmlFor="watchlist-rename" className="text-sm font-medium">Name</label>
          <Input id="watchlist-rename" autoFocus value={renameName} onChange={(event) => setRenameName(event.target.value)} onKeyDown={(event) => event.key === "Enter" && renameListId && handleSaveRename(renameListId)} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setRenameListId(null)}>Cancel</Button>
            <Button type="button" onClick={() => renameListId && handleSaveRename(renameListId)} disabled={!renameName.trim()}>Save name</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteListId !== null} onOpenChange={(open) => !open && setDeleteListId(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Delete watchlist?</DialogTitle>
            <DialogDescription>{activeDeleteList ? `“${activeDeleteList.name}” and its list of symbols will be removed.` : "This watchlist will be removed."}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteListId(null)}>Cancel</Button>
            <Button type="button" variant="destructive" onClick={() => { if (deleteListId) deleteWatchlist(deleteListId); setDeleteListId(null); }}>Delete watchlist</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showImportModal} onOpenChange={setShowImportModal}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Import symbols</DialogTitle>
            <DialogDescription>Paste ticker symbols separated by spaces, commas, or new lines.</DialogDescription>
          </DialogHeader>
          <Textarea
            autoFocus
            aria-label="Symbols to import"
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="NVDA, UBER, LYFT"
            className="min-h-32 w-full resize-y"
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowImportModal(false)}>Cancel</Button>
            <Button type="button" onClick={handleImportTickers} disabled={!importText.trim()}>Import symbols</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function WatchlistActions({ name, onRename, onDelete }: { name: string; onRename: () => void; onDelete: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="h-9 w-9 shrink-0" aria-label={`Actions for ${name}`} title="Watchlist actions">•••</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onRename}>Rename</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDelete} className="text-destructive focus:text-destructive">Delete</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function WatchlistMetric({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn("truncate text-xs font-medium", valueClass)}>{value}</div>
    </div>
  );
}
