import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "../../lib/utils";
import { FilterChipBar } from "./FilterChipBar";
import { StockIntrospectionDialog } from "./StockIntrospectionDialog";
import { FieldInspectorRail } from "./FieldInspectorRail";
import { DateNavigator } from "./DateNavigator";
import {
  previewScreen,
  previewIr,
  fetchSavedScreens,
  fetchFields,
  fetchAsOfRange,
} from "../../api/screens";
import type {
  AppliedFilterRow,
  ScreenField,
  UniverseQueryV1,
  RankedRow,
  OrderDirection,
  IrWhereNode,
  IrGroupNode,
} from "../../types";

export type ScreenerTabId = "overview" | "momentum" | "technicals" | "fundamentals";

interface ColumnDef {
  key: string;
  label: string;
  align?: "left" | "right" | "center";
}

const TAB_COLUMNS: Record<ScreenerTabId, ColumnDef[]> = {
  overview: [
    { key: "ticker", label: "Ticker", align: "left" },
    { key: "close", label: "Price", align: "right" },
    { key: "rs_rating", label: "RS", align: "right" },
    { key: "technical_rating", label: "TA", align: "right" },
    { key: "setup_quality_rating", label: "Setup", align: "right" },
    { key: "atr_14_pct", label: "ATR%", align: "right" },
    { key: "industry_group_rank", label: "Industry Rank", align: "right" },
    { key: "sector", label: "Sector", align: "left" },
  ],
  momentum: [
    { key: "ticker", label: "Ticker", align: "left" },
    { key: "close", label: "Price", align: "right" },
    { key: "rs_rating", label: "RS Rating", align: "right" },
    { key: "high_growth_momentum_rating", label: "Growth Mom", align: "right" },
    { key: "is_stage_2_advancing", label: "Stage 2", align: "center" },
    { key: "has_vcp_setup", label: "VCP Setup", align: "center" },
    { key: "sma200d_rising_30d", label: "200 SMA Rising", align: "center" },
    { key: "sector", label: "Sector", align: "left" },
  ],
  technicals: [
    { key: "ticker", label: "Ticker", align: "left" },
    { key: "close", label: "Price", align: "right" },
    { key: "sma21d", label: "21 EMA", align: "right" },
    { key: "sma50d", label: "50 SMA", align: "right" },
    { key: "sma150d", label: "150 SMA", align: "right" },
    { key: "sma200d", label: "200 SMA", align: "right" },
    { key: "atr_14_pct", label: "ATR %", align: "right" },
    { key: "breakout_signal", label: "Breakout", align: "center" },
  ],
  fundamentals: [
    { key: "ticker", label: "Ticker", align: "left" },
    { key: "close", label: "Price", align: "right" },
    { key: "valuation_rating", label: "Valuation", align: "right" },
    { key: "overall_score", label: "Overall Score", align: "right" },
    { key: "industry_group_rank", label: "Industry Rank", align: "right" },
    { key: "sector", label: "Sector", align: "left" },
  ],
};

function formatCellValue(key: string, val: unknown): string {
  if (val == null) return "—";
  if (key === "close" || key.startsWith("sma")) {
    const n = Number(val);
    return isNaN(n) ? String(val) : `$${n.toFixed(2)}`;
  }
  if (key.includes("atr_pct")) {
    const n = Number(val);
    return isNaN(n) ? String(val) : `${n.toFixed(1)}%`;
  }
  if (key === "marketcap" || key === "market_cap") {
    const n = Number(val);
    if (isNaN(n)) return String(val);
    return n >= 1e12 ? `$${(n / 1e12).toFixed(2)}T` : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(0)}M` : `$${n}`;
  }
  if (typeof val === "boolean") {
    return val ? "✓" : "—";
  }
  if (["is_stage_2_advancing", "has_vcp_setup", "sma200d_rising_30d", "breakout_signal", "is_bull_market"].includes(key)) {
    return Number(val) === 1 || val === true ? "✓" : "—";
  }
  if (["rs_rating", "technical_rating", "setup_quality_rating", "high_growth_momentum_rating", "valuation_rating", "overall_score", "industry_group_rank"].includes(key)) {
    const n = Number(val);
    return isNaN(n) ? String(val) : String(Math.round(n));
  }
  return String(val);
}

function specToFilters(spec: UniverseQueryV1 | null): AppliedFilterRow[] {
  if (!spec) return [];
  const where = spec.where as IrGroupNode | undefined;
  if (!where) return [];

  if (where.type !== "all" && ["gt", "gte", "lt", "lte", "eq"].includes((where as any).type)) {
    return [
      {
        id: `f-0-${Date.now()}`,
        op: (where as any).type,
        left: (where as any).left,
        right: (where as any).right,
      },
    ];
  }

  return (where.items ?? []).map((node, i) => {
    const n = node as Record<string, unknown>;
    const op = (n.type as string) ?? "eq";
    const isComparison = ["gt", "gte", "lt", "lte", "eq"].includes(op);
    if (isComparison && n.left && n.right) {
      return {
        id: `f-${i}-${Date.now()}`,
        op: op as AppliedFilterRow["op"],
        left: n.left as AppliedFilterRow["left"],
        right: n.right as AppliedFilterRow["right"],
      };
    }
    return {
      id: `f-${i}-${Date.now()}`,
      op: "eq" as const,
      left: { type: "col", name: "?" } as const,
      right: { type: "lit", value: "?" } as const,
      readOnly: true,
      raw: node,
    };
  });
}

function buildScreenerSpec(
  filters: AppliedFilterRow[],
  sortField: string,
  sortDir: OrderDirection,
  limit: number,
  searchQuery?: string
): UniverseQueryV1 {
  const comparisons = filters
    .filter((r) => !r.readOnly)
    .map((r) => ({ type: r.op, left: r.left, right: r.right }));
  const readOnlyRaw = filters.filter((r) => r.readOnly && r.raw).map((r) => r.raw!);
  const allItems: IrWhereNode[] = [...readOnlyRaw, ...comparisons];

  if (searchQuery && searchQuery.trim()) {
    const q = searchQuery.trim().toUpperCase();
    allItems.push({
      type: "eq",
      left: { type: "field", name: "ticker" },
      right: { type: "literal", value: q },
    });
  }

  const where: IrGroupNode = { type: "all", items: allItems };

  const selectCols = [
    "ticker",
    "close",
    "rs_rating",
    "technical_rating",
    "setup_quality_rating",
    "high_growth_momentum_rating",
    "valuation_rating",
    "overall_score",
    "sector",
    "industry_group_rank",
    "is_stage_2_advancing",
    "has_vcp_setup",
    "sma21d",
    "sma50d",
    "sma150d",
    "sma200d",
    "sma200d_rising_30d",
    "atr_14_pct",
    "breakout_signal",
  ];
  if (!selectCols.includes(sortField)) {
    selectCols.push(sortField);
  }

  return {
    version: 1,
    from: "daily_screener",
    select: selectCols,
    where,
    order_by: [{ field: sortField, direction: sortDir }],
    limit_per_day: limit,
  };
}

export interface StockScreenerDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  /** Initial selected ticker symbols */
  initialSelected?: string[];
  /** Mode: "select" returns chosen symbols; "apply-spec" can also pass back UniverseQueryV1 */
  mode?: "select" | "explore";
  /** Callback with selected symbols when user clicks Apply */
  onApplySelection?: (selectedSymbols: string[]) => void;
  /** Optional callback to apply the full screen spec */
  onApplySpec?: (spec: UniverseQueryV1) => void;
}

export function StockScreenerDialog({
  isOpen,
  onClose,
  title = "Stock Screener & Universe Selector",
  subtitle = "Search, filter by technical & fundamental metrics, and select universe candidate stocks",
  initialSelected = [],
  onApplySelection,
  onApplySpec,
}: StockScreenerDialogProps) {
  const [activeTab, setActiveTab] = useState<ScreenerTabId>("overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(
    () => new Set(initialSelected.map((s) => s.trim().toUpperCase()).filter(Boolean))
  );
  const [filterRows, setFilterRows] = useState<AppliedFilterRow[]>([
    {
      id: "init-rs",
      op: "gte",
      left: { type: "col", name: "rs_rating" },
      right: { type: "lit", value: 70 },
    },
    {
      id: "init-price",
      op: "gte",
      left: { type: "col", name: "close" },
      right: { type: "lit", value: 10 },
    },
  ]);
  const [activeSortField, setActiveSortField] = useState("rs_rating");
  const [activeSortDir, setActiveSortDir] = useState<OrderDirection>("desc");
  const [activeLimit, setActiveLimit] = useState(100);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  const [selectedScreenKey, setSelectedScreenKey] = useState<string>("");
  const [asOf, setAsOf] = useState("");
  const [chartRow, setChartRow] = useState<RankedRow | null>(null);

  // Field Inspector State
  const [inspectedField, setInspectedField] = useState<ScreenField | null>(null);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);

  // Sync initialSelected when dialog opens
  useEffect(() => {
    if (isOpen) {
      setSelectedSymbols(new Set((initialSelected || []).map((s) => s.trim().toUpperCase()).filter(Boolean)));
    }
  }, [isOpen]);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);


  const savedQuery = useQuery({
    queryKey: ["saved-screens-dialog"],
    queryFn: fetchSavedScreens,
    enabled: isOpen,
    staleTime: 60_000,
  });
  const fieldsQuery = useQuery({
    queryKey: ["screen-fields-dialog"],
    queryFn: fetchFields,
    enabled: isOpen,
    staleTime: 5 * 60_000,
  });
  const datesQuery = useQuery({
    queryKey: ["as-of-range-dialog"],
    queryFn: () => fetchAsOfRange(10000),
    enabled: isOpen,
    staleTime: 5 * 60_000,
  });

  const datesDesc = datesQuery.data ?? [];
  useEffect(() => {
    if (!asOf && datesDesc.length > 0) setAsOf(datesDesc[0]);
  }, [asOf, datesDesc]);

  // Grouped catalog fields for dropdowns & inspector
  const groupedFields = useMemo(() => {
    const groups: Record<string, ScreenField[]> = {};
    (fieldsQuery.data ?? []).forEach((f) => {
      const cat = f.category || "other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(f);
    });
    return groups;
  }, [fieldsQuery.data]);

  // Set default inspected field
  useEffect(() => {
    if (!inspectedField && fieldsQuery.data && fieldsQuery.data.length > 0) {
      const f = fieldsQuery.data.find((x) => x.name === activeSortField) || fieldsQuery.data[0];
      setInspectedField(f);
    }
  }, [fieldsQuery.data, activeSortField, inspectedField]);

  // Derived current query spec
  const currentSpec = useMemo(() => {
    return buildScreenerSpec(filterRows, activeSortField, activeSortDir, activeLimit, searchQuery);
  }, [filterRows, activeSortField, activeSortDir, activeLimit, searchQuery]);

  // Screen Query execution
  const screenQuery = useQuery({
    queryKey: ["dialog-screener-results", activePresetId, asOf, currentSpec],
    queryFn: () => {
      if (!asOf) return null;
      if (activePresetId && !filterRows.some((r) => !r.readOnly)) {
        return previewScreen({ as_of: asOf, preset: activePresetId, limit: activeLimit });
      }
      return previewIr({ as_of: asOf, spec: currentSpec });
    },
    enabled: isOpen && Boolean(asOf),
    staleTime: 30_000,
  });

  const rawRows: RankedRow[] = useMemo(() => {
    const rows = screenQuery.data?.rows as RankedRow[] | undefined;
    if (!rows) return [];
    return rows.map((r, i) => ({ ...r, rank: i + 1, priorRank: null, delta: null, deltaRank: null }));
  }, [screenQuery.data?.rows]);

  // Filtered by Search input
  const displayRows = useMemo(() => {
    if (!searchQuery.trim()) return rawRows;
    const q = searchQuery.trim().toLowerCase();
    return rawRows.filter((r) => {
      const tickerMatch = r.ticker.toLowerCase().includes(q);
      const sectorMatch = String(r.sector ?? "").toLowerCase().includes(q);
      return tickerMatch || sectorMatch;
    });
  }, [rawRows, searchQuery]);

  // Selection handlers
  function toggleSelectSymbol(sym: string) {
    setSelectedSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  }

  function selectTop(count: number) {
    const top = displayRows.slice(0, count).map((r) => r.ticker.toUpperCase());
    setSelectedSymbols((prev) => {
      const next = new Set(prev);
      top.forEach((s) => next.add(s));
      return next;
    });
  }

  function selectAllVisible() {
    const visible = displayRows.map((r) => r.ticker.toUpperCase());
    setSelectedSymbols((prev) => {
      const next = new Set(prev);
      visible.forEach((s) => next.add(s));
      return next;
    });
  }

  function clearSelection() {
    setSelectedSymbols(new Set());
  }

  function handleApply() {
    const arr = Array.from(selectedSymbols);
    onApplySelection?.(arr);
    if (onApplySpec) onApplySpec(currentSpec);
    onClose();
  }

  async function handleScreenSelectionChange(val: string) {
    setSelectedScreenKey(val);
    if (!val) {
      setActivePresetId(null);
      return;
    }

    const sId = val.startsWith("screen:") ? val.replace("screen:", "") : val;
    const s = savedQuery.data?.find((x) => String(x.id) === sId);
    if (s && s.spec) {
      setSelectedScreenKey(val);
      const parsedFilters = specToFilters(s.spec);
      if (parsedFilters.length > 0) {
        setFilterRows(parsedFilters);
      }
      if (s.spec.limit_per_day) setActiveLimit(s.spec.limit_per_day);
      if (s.spec.order_by?.[0]?.field) {
        setActiveSortField(s.spec.order_by[0].field);
        setActiveSortDir(s.spec.order_by[0].direction === "asc" ? "asc" : "desc");
      }
    }
  }

  function handleColumnHeaderClick(colKey: string) {
    if (activeSortField === colKey) {
      setActiveSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setActiveSortField(colKey);
      setActiveSortDir(colKey === "ticker" ? "asc" : "desc");
    }
  }

  if (!isOpen) return null;

  const currentColumns = TAB_COLUMNS[activeTab];
  const allVisibleSelected = displayRows.length > 0 && displayRows.every((r) => selectedSymbols.has(r.ticker.toUpperCase()));
  const someVisibleSelected = displayRows.some((r) => selectedSymbols.has(r.ticker.toUpperCase()));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 sm:p-6 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex h-[90vh] w-full max-w-6xl flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Dialog Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-raised px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10 text-accent font-bold text-base">
              🔍
            </span>
            <div>
              <h3 className="text-sm font-bold text-ink leading-none">{title}</h3>
              <p className="mt-0.5 text-[11px] text-ink-muted leading-none">{subtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Presets & Saved Screens dropdown */}
            <select
              value={selectedScreenKey}
              onChange={(e) => handleScreenSelectionChange(e.target.value)}
              className="rounded-md border border-line bg-surface px-2.5 py-1 text-[11px] font-semibold text-ink focus:border-accent focus:outline-none"
            >
              <option value="">Load Screen / Template…</option>
              {savedQuery.data && savedQuery.data.filter((s) => s.is_system).length > 0 && (
                <optgroup label="⭐ System Built-In Screens">
                  {savedQuery.data.filter((s) => s.is_system).map((s) => (
                    <option key={String(s.id)} value={`screen:${s.id}`}>{s.name}</option>
                  ))}
                </optgroup>
              )}
              {savedQuery.data && savedQuery.data.filter((s) => !s.is_system).length > 0 && (
                <optgroup label="💾 My Custom Screens">
                  {savedQuery.data.filter((s) => !s.is_system).map((s) => (
                    <option key={String(s.id)} value={`screen:${s.id}`}>{s.name}</option>
                  ))}
                </optgroup>
              )}
            </select>

            {/* Top N limit */}
            <select
              value={activeLimit}
              onChange={(e) => setActiveLimit(Number(e.target.value))}
              className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-[11px] text-ink focus:border-accent focus:outline-none"
              title="Max candidates limit"
            >
              <option value={25}>Top 25</option>
              <option value={50}>Top 50</option>
              <option value={100}>Top 100</option>
              <option value={250}>Top 250</option>
            </select>

            {/* As-of Date Period Navigator */}
            {datesDesc.length > 0 && (
              <DateNavigator
                currentDate={asOf}
                availableDates={datesDesc}
                onChangeDate={(d) => setAsOf(d)}
              />
            )}

            {/* Field Inspector Toggle */}
            <button
              type="button"
              onClick={() => setIsInspectorOpen((p) => !p)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-bold transition-all",
                isInspectorOpen
                  ? "border-accent bg-accent/15 text-accent shadow-xs"
                  : "border-line bg-surface text-ink-muted hover:border-accent hover:text-ink"
              )}
              title="Toggle Field Inspector Rail"
            >
              <span>ℹ️</span>
              <span className="hidden sm:inline">Inspector</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink-muted hover:text-ink hover:bg-surface-sunk transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Filter Chip Bar */}
        <div className="border-b border-line bg-surface px-4 py-1.5">
          <FilterChipBar
            filterRows={filterRows}
            fields={fieldsQuery.data ?? []}
            onFilterRowsChange={(rows) => {
              setActivePresetId(null);
              setSelectedScreenKey("");
              setFilterRows(rows);
            }}
            onFocusField={(field) => {
              if (field) {
                setInspectedField(field);
                setIsInspectorOpen(true);
              }
            }}
          />
        </div>

        {/* View Category Tabs & Search Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-raised px-4 py-2">
          {/* Tabs */}
          <div className="inline-flex rounded-lg border border-line bg-surface-sunk p-0.5">
            {(
              [
                { id: "overview", label: "Overview" },
                { id: "momentum", label: "Momentum / Trend" },
                { id: "technicals", label: "Technicals" },
                { id: "fundamentals", label: "Fundamentals" },
              ] as const
            ).map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTab(t.id)}
                className={cn(
                  "rounded-md px-3 py-1 text-[11px] font-semibold transition-all",
                  activeTab === t.id
                    ? "bg-accent text-accent-ink shadow-xs"
                    : "text-ink-muted hover:text-ink"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Quick Search & Sort Info */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint text-xs">🔍</span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter results (ticker, sector)…"
                className="w-56 rounded-md border border-line bg-surface pl-7 pr-2.5 py-1 text-[11.5px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink text-[10px]"
                >
                  ✕
                </button>
              )}
            </div>
            {/* Sort Field & Direction */}
            <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              <span>Sort:</span>
              <select
                value={activeSortField}
                onChange={(e) => {
                  const val = e.target.value;
                  setActiveSortField(val);
                  const f = fieldsQuery.data?.find((x) => x.name === val);
                  if (f) {
                    setInspectedField(f);
                    setIsInspectorOpen(true);
                  }
                }}
                className="rounded border border-line bg-surface px-2 py-0.5 font-semibold text-accent focus:border-accent focus:outline-none text-[11px]"
              >
                {Object.entries(groupedFields).map(([cat, fList]) => (
                  <optgroup key={cat} label={fList[0]?.category_label || cat}>
                    {fList.map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.label || f.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setActiveSortDir((d) => (d === "desc" ? "asc" : "desc"))}
                className="rounded border border-line bg-surface px-1.5 py-0.5 text-xs font-bold text-ink hover:border-accent hover:text-accent transition-colors"
                title="Toggle Sort Direction"
              >
                {activeSortDir === "desc" ? "▼ DESC" : "▲ ASC"}
              </button>
            </div>

            <span className="font-mono text-[11px] text-ink-muted">
              {screenQuery.isLoading ? "Querying…" : `${displayRows.length} matches`}
            </span>
          </div>
        </div>

        {/* Main Content Area: Screener Table + Field Inspector Rail */}
        <div className="flex flex-1 min-h-0 overflow-hidden bg-surface">
          {/* Table Container */}
          <div className="flex-1 overflow-auto">
            {screenQuery.isError && (
              <div className="p-8 text-center text-xs text-danger">
                Screener query failed: {(screenQuery.error as Error)?.message || "Verify ClickHouse connection."}
              </div>
            )}

            {!screenQuery.isError && displayRows.length === 0 && !screenQuery.isLoading && (
              <div className="p-12 text-center text-xs text-ink-muted">
                No universe stocks matched the criteria on {asOf}. Try relaxing filter thresholds.
              </div>
            )}

            {displayRows.length > 0 && (
              <table className="w-full text-left text-[11.5px] border-collapse">
                <thead className="sticky top-0 z-10 bg-surface-raised text-[10px] font-bold uppercase tracking-wider text-ink-faint border-b border-line shadow-xs">
                  <tr>
                    <th className="w-10 px-3 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={allVisibleSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = someVisibleSelected && !allVisibleSelected;
                        }}
                        onChange={(e) => {
                          if (e.target.checked) selectAllVisible();
                          else clearSelection();
                        }}
                        className="rounded border-line text-accent focus:ring-accent cursor-pointer"
                        title="Select all visible"
                      />
                    </th>
                    <th className="w-8 px-2 py-2 text-center font-mono">#</th>
                    {currentColumns.map((col) => {
                      const isSorted = activeSortField === col.key;
                      const colFieldObj = fieldsQuery.data?.find((x) => x.name === col.key);
                      return (
                        <th
                          key={col.key}
                          className={cn(
                            "px-2.5 py-2 cursor-pointer select-none transition-colors whitespace-nowrap",
                            col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left",
                            isSorted ? "text-accent font-extrabold bg-accent/5" : "hover:text-ink"
                          )}
                          onMouseEnter={() => {
                            if (colFieldObj) setInspectedField(colFieldObj);
                          }}
                          onClick={() => {
                            handleColumnHeaderClick(col.key);
                            if (colFieldObj) {
                              setInspectedField(colFieldObj);
                              setIsInspectorOpen(true);
                            }
                          }}
                          title={colFieldObj?.description ? `${col.label}: ${colFieldObj.description}` : `Sort by ${col.label}`}
                        >
                          <span>{col.label}</span>
                          {isSorted && (
                            <span className="ml-1 text-accent">
                              {activeSortDir === "desc" ? "▼" : "▲"}
                            </span>
                          )}
                        </th>
                      );
                    })}
                    <th className="w-20 px-3 py-2 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40">
                  {displayRows.map((row) => {
                    const isSelected = selectedSymbols.has(row.ticker.toUpperCase());
                    return (
                      <tr
                        key={row.ticker}
                        className={cn(
                          "transition-colors hover:bg-surface-sunk/60",
                          isSelected && "bg-accent/5"
                        )}
                      >
                        <td className="px-3 py-1.5 text-center">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectSymbol(row.ticker)}
                            className="rounded border-line text-accent focus:ring-accent cursor-pointer"
                          />
                        </td>
                        <td className="px-2 py-1.5 text-center font-mono text-ink-muted text-[11px]">
                          {row.rank}
                        </td>
                        {currentColumns.map((col) => {
                          const val = (row as Record<string, unknown>)[col.key];
                          return (
                            <td
                              key={col.key}
                              className={cn(
                                "px-2.5 py-1.5 whitespace-nowrap text-[11.5px]",
                                col.align === "right" ? "text-right font-mono" : col.align === "center" ? "text-center font-mono" : "text-left",
                                col.key === "ticker" && "font-bold text-ink",
                                col.key === "rs_rating" && "font-bold text-emerald-500 font-mono",
                                col.key === "technical_rating" && "font-semibold text-accent font-mono"
                              )}
                            >
                              {col.key === "ticker" ? (
                                <button
                                  type="button"
                                  onClick={() => setChartRow(row)}
                                  className="font-mono font-bold text-accent hover:underline text-left cursor-pointer inline-flex items-center gap-1"
                                  title={`Introspect ${row.ticker} on ${asOf}`}
                                >
                                  <span>{row.ticker}</span>
                                  <span className="text-[9px] opacity-60">🔍</span>
                                </button>
                              ) : (
                                formatCellValue(col.key, val)
                              )}
                            </td>
                          );
                        })}
                        <td className="px-3 py-1.5 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <button
                              type="button"
                              onClick={() => setChartRow(row)}
                              className="rounded border border-line bg-surface px-1.5 py-0.5 text-xs text-ink-muted hover:border-accent hover:text-accent transition-colors"
                              title={`View ${row.ticker} candlestick chart`}
                            >
                              📈
                            </button>
                            <a
                              href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(row.ticker)}`}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-accent hover:text-accent transition-colors"
                              title={`Open ${row.ticker} on TradingView`}
                            >
                              TV
                            </a>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Right-Side Field Inspector Rail */}
          <FieldInspectorRail
            field={inspectedField}
            isOpen={isInspectorOpen}
            onClose={() => setIsInspectorOpen(false)}
            currentSortField={activeSortField}
            onAddFilter={(field) => {
              const pName = field.prefixed_name || `${field.prefix || "px"}.${field.name}`;
              setFilterRows((prev) => [
                ...prev,
                {
                  id: `f-${Date.now()}`,
                  op: "gte",
                  left: { type: "col", name: pName },
                  right: { type: "lit", value: 50 },
                },
              ]);
            }}
            onSetSort={(field) => {
              const pName = field.prefixed_name || `${field.prefix || "px"}.${field.name}`;
              setActiveSortField(pName);
              setActiveSortDir("desc");
            }}
          />
        </div>

        {/* Footer Selection Controls & Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-raised px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-ink">
              Selected ({selectedSymbols.size}):
            </span>
            {selectedSymbols.size === 0 ? (
              <span className="text-ink-muted italic">Click rows or checkboxes to select stocks</span>
            ) : (
              <div className="flex flex-wrap items-center gap-1 max-w-lg overflow-hidden text-ellipsis">
                {Array.from(selectedSymbols).slice(0, 8).map((s) => (
                  <span
                    key={s}
                    className="inline-flex items-center gap-1 rounded bg-accent/15 px-2 py-0.5 font-mono text-[10.5px] font-bold text-accent-ink"
                  >
                    {s}
                    <button
                      type="button"
                      onClick={() => toggleSelectSymbol(s)}
                      className="text-accent-ink hover:text-danger ml-0.5"
                    >
                      ✕
                    </button>
                  </span>
                ))}
                {selectedSymbols.size > 8 && (
                  <span className="font-mono text-[10.5px] text-ink-muted">
                    +{selectedSymbols.size - 8} more
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 border-r border-line pr-2 mr-1">
              <button
                type="button"
                onClick={() => selectTop(10)}
                className="rounded border border-line bg-surface px-2 py-1 text-[11px] font-medium text-ink hover:border-accent transition-colors"
              >
                + Top 10
              </button>
              <button
                type="button"
                onClick={() => selectTop(25)}
                className="rounded border border-line bg-surface px-2 py-1 text-[11px] font-medium text-ink hover:border-accent transition-colors"
              >
                + Top 25
              </button>
              {selectedSymbols.size > 0 && (
                <button
                  type="button"
                  onClick={clearSelection}
                  className="rounded border border-line bg-surface px-2 py-1 text-[11px] font-medium text-danger hover:bg-danger/10 transition-colors"
                >
                  Clear
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink-muted hover:text-ink transition-colors"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={handleApply}
              disabled={selectedSymbols.size === 0}
              className="rounded-lg bg-accent px-4 py-1.5 text-xs font-bold text-accent-ink shadow-sm hover:opacity-90 disabled:opacity-40 transition-all"
            >
              Apply Selection ({selectedSymbols.size} Tickers)
            </button>
          </div>
        </div>

        {/* Native Stock Introspection Dossier & Chart Modal */}
        {chartRow && (
          <StockIntrospectionDialog
            isOpen={!!chartRow}
            ticker={chartRow.ticker}
            asOfDate={asOf}
            onClose={() => setChartRow(null)}
          />
        )}
      </div>
    </div>
  );
}
