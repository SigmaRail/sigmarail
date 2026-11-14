import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { UniverseTreeEditor, asGroup } from "./UniverseTreeEditor";
import { MembershipOverTime } from "./MembershipOverTime";
import { ScreenPickerDialog } from "./ScreenPickerDialog";
import { DateNavigator } from "./DateNavigator";
import { MiniSparklineCard } from "./MiniSparklineCard";
import { useFieldPicker } from "./FieldPickerProvider";
import type { FieldPick } from "../../lib/fieldPick";
import { DataTable, type GridColumn, type SortSpec } from "../../components/DataTable";
import { cn } from "../../lib/utils";
import { previewScreen, previewIr, fetchAsOfRange } from "../../api/screens";
import { nextFilterId } from "../../lib/irFilters";
import {
  emptyGroup,
  stripIds,
  whereToAst,
  withIds,
  type UiGroup,
  type UiNode,
} from "../../lib/screenAst";
import type {
  ScreenField,
  UniverseQueryV1,
  RankedRow,
  ScreenPreset,
  SavedScreen,
  IrOperand,
  IrWhereNode,
  OrderByItemV1,
} from "../../types";

const DEFAULT_LIMIT = 50;

/** The editor's tree for a spec's `where`; always a group, so groups can be added to it. */
function treeFrom(where: unknown): UiGroup {
  return asGroup(withIds(whereToAst(where) ?? emptyGroup("all", "membership"), nextFilterId));
}

/**
 * Build a complete UniverseQueryV1 spec from the screen tree, sort terms, and limit.
 *
 * Takes the tree itself (the same node the API compiles) rather than the editor's chip
 * model, so nothing is converted on the way through and `not` / arithmetic / nesting all
 * survive an edit.
 */
function buildSpec(
  base: UniverseQueryV1 | null,
  where: IrWhereNode,
  sortBy: SortSpec[],
  limit: number
): UniverseQueryV1 {
  const existingSelect = Array.isArray(base?.select) ? [...base.select] : [
    "ticker",
    "close",
    "rs_rating",
    "technical_rating",
    "setup_quality_rating",
    "atr_14_pct",
    "industry_group_rank",
    "sector",
  ];

  // The query contract requires a deterministic order (it drives backtest chunking), so an
  // empty sort still has to name one. Default to the screener's own ranking column.
  const effectiveSort: SortSpec[] =
    sortBy.length > 0 ? sortBy : [{ field: "overall_score", direction: "desc" }];

  // Field terms must be projected so ORDER BY can reference the output alias;
  // expr terms are raw expressions (columns need not be selected).
  for (const s of effectiveSort) {
    if (s.field && !existingSelect.includes(s.field)) {
      existingSelect.push(s.field);
    }
  }

  return {
    version: 1,
    from: base?.from || "daily_screener",
    select: existingSelect,
    where,
    order_by: effectiveSort.map((s): OrderByItemV1 =>
      s.field
        ? { field: s.field, direction: s.direction }
        : { expr: s.expr as IrOperand, direction: s.direction },
    ),
    limit_per_day: limit,
  };
}

function rankRows(rows: RankedRow[] | undefined): RankedRow[] {
  if (!rows) return [];
  return rows.map((r, i) => ({ ...r, rank: i + 1, priorRank: null, delta: null, deltaRank: null }));
}

interface InlineScreenerPanelProps {
  /** Initial spec (from selected preset/saved screen or inline) */
  spec: UniverseQueryV1 | null;
  /** Preset id currently active (for preset-based query path) */
  activePresetId: string | null;
  /** Active as-of date (YYYY-MM-DD) */
  asOf?: string;
  /** Available presets for the picker */
  presets: ScreenPreset[];
  /** Available saved screens for the picker */
  savedScreens: SavedScreen[];
  /** Available fields for the filter builder */
  fields: ScreenField[];
  /** Called whenever the spec changes (filters edited, sort changed, preset loaded) */
  onSpecChange: (spec: UniverseQueryV1) => void;
  /** Called when user selects a preset */
  onSelectPreset: (id: string) => void;
  /** Called when user selects a saved screen (system template or custom) */
  onSelectSaved: (screen: SavedScreen) => void;
  /** Called when asOf changes in date navigator */
  onAsOfChange?: (date: string) => void;
  /** Called when user wants to save current spec; receives the exact live spec */
  onSaveTemplate?: (spec: UniverseQueryV1) => void;
  /** Called when user wants to send current screen AST into strategy pipeline */
  onSendToStrategy?: (spec: UniverseQueryV1) => void;
  /** Open a result row's ticker in the dedicated chart view (/stock/:ticker/chart). */
  onOpenTicker?: (ticker: string) => void;
  /** Initial results layout, from the URL (`?view=`). */
  initialViewMode?: "list" | "grid" | null;
  /** Report layout changes so the address can carry them. */
  onViewModeChange?: (mode: "list" | "grid") => void;
  /** Applied filter chips from the address (`?filters=`) — authoritative when present. */
  /** The tree carried by the address (deep link). No conversion on the way in. */
  initialWhere?: IrWhereNode | null;
}

export function InlineScreenerPanel({
  spec,
  activePresetId,
  asOf: propAsOf,
  presets: _presets,
  savedScreens,
  fields,
  onSpecChange,
  onSelectPreset: _onSelectPreset,
  onSelectSaved,
  onAsOfChange,
  onSaveTemplate,
  onSendToStrategy,
  onOpenTicker,
  initialViewMode,
  onViewModeChange,
  initialWhere,
}: InlineScreenerPanelProps) {
  // The tree is the source of truth for the screen's conditions — the address carries the
  // same tree, so nothing is converted on the way in.
  const [whereRoot, setWhereRoot] = useState<UiGroup>(() => treeFrom(initialWhere ?? spec?.where));
  /** True once the user edits here, so the preset fast-path is not taken for edited screens. */
  const editedRef = useRef(false);
  /**
   * True while the address itself is carrying the tree (a shared link, or an edited screen).
   * When it is, the address is the source of truth — not the preview response, whose spec
   * can legitimately differ from what the user sees (a group with no conditions yet has no
   * SQL behind it), and adopting it would silently drop a group the user just added.
   */
  const addressCarriesTree = useRef(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "grid">(initialViewMode ?? "list");
  useEffect(() => {
    if (initialViewMode && initialViewMode !== viewMode) setViewMode(initialViewMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialViewMode]);
  const [asOf, setAsOf] = useState(propAsOf || "");
  /** The membership chart is opt-in: a 29-year range summary should not fire on load. */
  const [membershipOpen, setMembershipOpen] = useState(false);

  useEffect(() => {
    if (propAsOf && propAsOf !== asOf) {
      setAsOf(propAsOf);
    }
  }, [propAsOf]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { openPicker: openSharedPicker } = useFieldPicker();

  // Spec-level Sort & Limit — multi-term sort (field or expression)
  const specKey = JSON.stringify(spec || {});
  const [sortBy, setSortBy] = useState<SortSpec[]>(() =>
    (spec?.order_by ?? []).map((ob) =>
      ob.field
        ? { field: ob.field, direction: (ob.direction === "asc" ? "asc" : "desc") as "asc" | "desc" }
        : { expr: ob.expr, direction: (ob.direction === "asc" ? "asc" : "desc") as "asc" | "desc" },
    ),
  );
  const activeSortDir = sortBy[0]?.direction === "asc" ? "asc" : "desc";
  const activeLimit = spec?.limit_per_day || DEFAULT_LIMIT;
  useEffect(() => {
    const next = (spec?.order_by ?? []).map((ob) =>
      ob.field
        ? { field: ob.field, direction: (ob.direction === "asc" ? "asc" : "desc") as "asc" | "desc" }
        : { expr: ob.expr, direction: (ob.direction === "asc" ? "asc" : "desc") as "asc" | "desc" },
    );
    setSortBy(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey]);

  // Re-sync the tree when the spec changes externally (template or saved screen loaded).
  // Our own edits echo back up through `spec`, so the content we applied is remembered and
  // an echo must not reset the tree: fresh ids would remount every input and steal focus
  // mid-typing.
  const incomingWhere = useMemo(() => JSON.stringify(spec?.where ?? null), [specKey]);
  const appliedWhereRef = useRef(incomingWhere);
  useEffect(() => {
    if (incomingWhere === appliedWhereRef.current) return;
    appliedWhereRef.current = incomingWhere;
    if (addressCarriesTree.current) return; // the address wins; do not adopt the echo
    editedRef.current = false;
    setWhereRoot(treeFrom(spec?.where));
  }, [incomingWhere]);

  // Fetch available dates for the as-of picker
  const datesQuery = useQuery({
    queryKey: ["backtest-as-of-range"],
    queryFn: () => fetchAsOfRange(10000),
  });
  const datesDesc: string[] = datesQuery.data ?? [];
  useEffect(() => {
    if (!asOf && datesDesc.length > 0) setAsOf(datesDesc[0]);
  }, [asOf, datesDesc]);

  // Current query spec derived from the screen tree, sort terms, and limit
  const querySpec = buildSpec(spec, stripIds(whereRoot), sortBy, activeLimit);

  // The address wins when it changes (deep link, back/forward): it carries the screen.
  // Report the composed spec up so the address keeps carrying it.
  const incomingWhereProp = initialWhere ? JSON.stringify(initialWhere) : "";
  useEffect(() => {
    addressCarriesTree.current = Boolean(initialWhere);
    if (!initialWhere) return;
    appliedWhereRef.current = incomingWhereProp;
    editedRef.current = false;
    setWhereRoot(treeFrom(initialWhere));
    onSpecChange(buildSpec(spec, initialWhere, sortBy, activeLimit));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomingWhereProp]);

  // Propagate spec changes up with debounce
  const updateSpecAndNotify = useCallback(
    (where: IrWhereNode, sorts: SortSpec[], limit: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const nextSpec = buildSpec(spec, where, sorts, limit);
        onSpecChange(nextSpec);
      }, 350);
    },
    [spec, onSpecChange]
  );

  const handleWhereChange = useCallback(
    (node: UiNode | null) => {
      // The editor hands back nodes that keep their ids, so untouched inputs stay mounted.
      const next = asGroup(node ?? withIds(emptyGroup("all", "membership"), nextFilterId));
      setWhereRoot(next);
      appliedWhereRef.current = JSON.stringify(stripIds(next));
      editedRef.current = true;
      updateSpecAndNotify(stripIds(next), sortBy, activeLimit);
    },
    [updateSpecAndNotify, sortBy, activeLimit]
  );

  const handleSortByChange = useCallback(
    (sorts: SortSpec[]) => {
      setSortBy(sorts);
      updateSpecAndNotify(stripIds(whereRoot), sorts, activeLimit);
    },
    [updateSpecAndNotify, whereRoot, activeLimit]
  );

  const handleSortDirToggle = () => {
    if (sortBy.length === 0) return;
    const nextDir = sortBy[0].direction === "desc" ? "asc" : "desc";
    handleSortByChange([{ ...sortBy[0], direction: nextDir }, ...sortBy.slice(1)]);
  };

  const handleLimitChange = (newLimit: number) => {
    updateSpecAndNotify(stripIds(whereRoot), sortBy, newLimit);
  };

  // Dynamically added display columns (from catalog via the shared picker).
  const [extraColumns, setExtraColumns] = useState<GridColumn<RankedRow>[]>([]);
  const handleOpenAddColumn = useCallback(() => {
    openSharedPicker({
      use: "column",
      fields,
      title: "Add Column",
      actionLabel: "Add Column",
      mode: "fields",
      onPick: (pick) => {
        if (pick.kind !== "field") return;
        const f = pick.field;
        setExtraColumns((prev) => {
          if (prev.some((c) => c.id === f.name)) return prev;
          const fmt: GridColumn<RankedRow>["format"] = /_pct$|pct_|rate|growth/.test(f.name)
            ? "pct"
            : /price|close|sma|atr|_pe$|_price|target/.test(f.name)
              ? "price"
              : ["rs_rating", "technical_rating", "setup_quality_rating", "high_growth_momentum_rating", "industry_group_rank", "stage_duration"].includes(f.name)
                ? "int"
                : undefined;
          return [
            ...prev,
            {
              id: f.name,
              label: f.label || f.name,
              sortable: true,
              sortField: f.name,
              removable: true,
              format: fmt,
              accessor: (r) => (r as Record<string, unknown>)[f.name] ?? null,
              cell: undefined,
              info: { name: f.name, label: f.label || f.name, description: f.description, category: f.category },
            },
          ];
        });
      },
    });
  }, [openSharedPicker, fields]);
  const handleRemoveColumn = useCallback((columnId: string) => {
    setExtraColumns((prev) => prev.filter((c) => c.id !== columnId));
  }, []);


  // Map a pick into a sort term and apply it (replace primary).
  const handleSortPick = useCallback(
    (pick: FieldPick) => {
      let term: SortSpec | null = null;
      if (pick.kind === "field") {
        term = { field: pick.field.name, direction: "desc", label: pick.field.label };
      } else if (pick.kind === "expr" && pick.operand) {
        term = { expr: pick.operand, direction: "desc", label: pick.text };
      } else if (pick.kind === "predicate") {
        // Full predicates (with comparisons) can't be an ORDER BY key — ignore.
        return;
      }
      if (term) {
        handleSortByChange([term]);
      }
    },
    [handleSortByChange],
  );

  // Open the shared Field/Expression browser for ORDER BY.
  const handleOpenSortPicker = useCallback(() => {
    openSharedPicker({
      use: "sort",
      fields,
      title: "Choose Sort Key (Field or Expression)",
      actionLabel: "Sort by this",
      initialFieldName: sortBy[0]?.field ?? null,
      onPick: handleSortPick,
    });
  }, [openSharedPicker, fields, sortBy, handleSortPick]);

  // Screener query — auto-runs when asOf or querySpec changes
  const previewQuery = useQuery({
    queryKey: ["inline-screener-preview", activePresetId, asOf, querySpec],
    queryFn: () => {
      if (!asOf) return null;
      if (activePresetId && !editedRef.current) {
        // Fast preset path while the screen is still exactly what the preset provided
        return previewScreen({ as_of: asOf, preset: activePresetId, limit: activeLimit });
      }
      if (querySpec) {
        return previewIr({ as_of: asOf, spec: querySpec });
      }
      return null;
    },
    enabled: Boolean(asOf) && (Boolean(activePresetId) || Boolean(querySpec)),
    staleTime: 30_000,
  });

  // Rows as returned directly from the ClickHouse screen spec query
  const rows: RankedRow[] = rankRows(previewQuery.data?.rows as RankedRow[] | undefined);
  const count = rows.length;

  useEffect(() => {
    if (typeof window !== "undefined" && window.__STUDIO_AGENT_BRIDGE__) {
      window.__STUDIO_AGENT_BRIDGE__.updateState({
        rankedRowCount: rows.length,
        asOf,
        liveSpec: querySpec,
        preset: activePresetId || "",
        templateId: typeof spec?.name === "string" ? spec.name : null,
      });
    }
  }, [rows.length, asOf, querySpec, activePresetId, spec?.name]);

  // Columns for the reusable DataTable
  const panelColumns: GridColumn<RankedRow>[] = useMemo(() => {
    // Lookup catalog metadata per field name (feeds shared ℹ popovers)
    const fieldMeta = (name: string): GridColumn<RankedRow>["info"] => {
      const f = fields.find((x) => x.name === name || x.prefixed_name === name);
      return f
        ? {
            name: f.name,
            label: f.label,
            description: f.description,
            category: f.category_label || f.category,
            sql_expr: f.sql_expr,
          }
        : null;
    };
    return [
      {
        id: "ticker",
        label: "Ticker",
        align: "left",
        always: true,
        sortable: true,
        sticky: "left",
        sortField: "ticker",
        info: fieldMeta("ticker"),
        accessor: (r) => r.ticker,
        cell: (r) => (
          <button
            type="button"
            onClick={() => onOpenTicker?.(r.ticker)}
            className="font-mono font-bold text-accent hover:underline text-left cursor-pointer inline-flex items-center gap-1"
            title={`Open ${r.ticker} chart for ${asOf}`}
          >
            <span>{r.ticker}</span>
          </button>
        ),
      },
      {
        id: "close",
        label: "Price",
        align: "right",
        sortable: true,
        sortField: "close",
        info: fieldMeta("close"),
        format: "price",
        accessor: (r) => r.close ?? null,
      },
      {
        id: "rs_rating",
        label: "RS",
        align: "right",
        sortable: true,
        sortField: "rs_rating",
        info: fieldMeta("rs_rating"),
        format: "int",
        accessor: (r) => r.rs_rating ?? null,
        cell: (_r, v) => {
          const n = Number(v);
          return <span className="font-bold text-emerald-400">{Number.isFinite(n) ? Math.round(n) : "—"}</span>;
        },
      },
      {
        id: "technical_rating",
        label: "TA",
        align: "right",
        sortable: true,
        sortField: "technical_rating",
        info: fieldMeta("technical_rating"),
        format: "int",
        accessor: (r) => (r as Record<string, unknown>).technical_rating ?? null,
      },
      {
        id: "setup_quality_rating",
        label: "Setup",
        align: "right",
        sortable: true,
        sortField: "setup_quality_rating",
        info: fieldMeta("setup_quality_rating"),
        format: "int",
        accessor: (r) => (r as Record<string, unknown>).setup_quality_rating ?? null,
      },
      {
        id: "atr_14_pct",
        label: "ATR %",
        align: "right",
        sortable: true,
        sortField: "atr_14_pct",
        info: fieldMeta("atr_14_pct"),
        format: "pct",
        accessor: (r) => (r as Record<string, unknown>).atr_14_pct ?? null,
      },
      {
        id: "industry_group_rank",
        label: "Ind Rank",
        align: "right",
        sortable: true,
        sortField: "industry_group_rank",
        info: fieldMeta("industry_group_rank"),
        format: "int",
        accessor: (r) => (r as Record<string, unknown>).industry_group_rank ?? null,
      },
      {
        id: "sector",
        label: "Sector",
        align: "left",
        sortable: false,
        info: fieldMeta("sector"),
        accessor: (r) => (r as Record<string, unknown>).sector ?? null,
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asOf, fields]);

  return (
    <div className="relative rounded-lg border border-accent/30 bg-surface shadow-sm">
      {/* Screen Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-lg border-b border-accent/20 bg-accent/5 px-2.5 py-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[9.5px] font-bold uppercase tracking-wider text-accent">Selected Universe Screen</span>
          <span className="rounded bg-surface px-1.5 py-0.5 font-mono text-[9px] font-semibold text-accent border border-accent/30">
            ClickHouse AST
          </span>
          {previewQuery.isFetching && (
            <span className="font-mono text-[9px] text-ink-faint animate-pulse">querying…</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {datesDesc.length > 0 && (
            <DateNavigator
              currentDate={asOf}
              availableDates={datesDesc}
              onChangeDate={(d) => {
                setAsOf(d);
                onAsOfChange?.(d);
              }}
            />
          )}
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="inline-flex items-center gap-1 rounded border border-line bg-surface px-2 py-0.5 text-[10px] font-semibold text-ink-muted hover:text-ink hover:border-accent transition-colors"
          >
            📂 Load
          </button>
          {onSaveTemplate && (
            <button
              type="button"
              onClick={() => onSaveTemplate(buildSpec(spec, stripIds(whereRoot), sortBy, activeLimit))}
              className="inline-flex items-center gap-1 rounded border border-line bg-surface px-2 py-0.5 text-[10px] font-semibold text-ink-muted hover:text-ink hover:border-accent transition-colors"
              title="Save current screen as a reusable template"
            >
              💾 Save
            </button>
          )}
          {onSendToStrategy && (
            <button
              type="button"
              onClick={() => onSendToStrategy(buildSpec(spec, stripIds(whereRoot), sortBy, activeLimit))}
              className="inline-flex items-center gap-1 rounded border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-[10px] font-semibold text-accent hover:bg-accent/20 transition-colors"
              title="Send screen conditions into Strategy Pipeline as a filter stage"
            >
              ⚡ Send to Strategy
            </button>
          )}
        </div>
      </div>

      {/* Filter Groups (Deepvue-style ALL / ANY) */}
      <div className="border-b border-line px-2.5 py-1">
        <UniverseTreeEditor
          node={whereRoot}
          isRoot
          fields={fields.length > 0 ? fields : [
            { name: "rs_rating", label: "RS Rating", category: "momentum" },
            { name: "technical_rating", label: "Technical Rating", category: "momentum" },
            { name: "close", label: "Price", category: "price" },
            { name: "market_cap", label: "Market Cap", category: "fundamental" },
            { name: "setup_quality_rating", label: "Setup Quality", category: "momentum" },
            { name: "atr_pct", label: "ATR %", category: "volatility" },
          ]}
          onChange={handleWhereChange}
        />
      </div>

      {/* Spec Controls Toolbar: Sort by, Direction, Limit */}
      <div className="flex flex-wrap items-center justify-between gap-1.5 border-b border-line bg-surface-raised/40 px-2.5 py-1 text-[10px]">
        {/* Left: Spec Order By & Limit Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Sort:</span>
            <button
              type="button"
              onClick={handleOpenSortPicker}
              className="inline-flex max-w-[300px] items-center gap-1 rounded border border-line bg-surface px-2 py-0.5 font-semibold text-accent hover:border-accent/60 transition-colors text-[10.5px]"
              title="Open the shared field/expression browser to set ORDER BY"
            >
              {sortBy.length === 0 ? (
                <span className="text-ink-muted italic">— pick field or expression —</span>
              ) : (
                <span className="truncate">{sortBy[0].label ?? sortBy[0].field ?? "expression"}</span>
              )}
              <span className="shrink-0 text-[9px]">⚙</span>
            </button>
          </div>

          <button
            type="button"
            onClick={handleSortDirToggle}
            disabled={sortBy.length === 0}
            className="inline-flex items-center gap-1 rounded border border-line bg-surface px-2 py-0.5 font-mono text-[10.5px] font-semibold text-ink hover:border-accent transition-colors disabled:opacity-40"
            title="Toggle Spec sort direction"
          >
            <span>{activeSortDir === "desc" ? "DESC" : "ASC"}</span>
            <span className="text-accent">{activeSortDir === "desc" ? "▼" : "▲"}</span>
          </button>

          <div className="flex items-center gap-1 ml-1 pl-2 border-l border-line">
            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Top:</span>
            <select
              value={activeLimit}
              onChange={(e) => handleLimitChange(Number(e.target.value))}
              className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10.5px] text-ink focus:border-accent focus:outline-none"
              title="ClickHouse Spec limit_per_day"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>

        {/* Right: Results Count + View Mode Toggle */}
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-ink-muted">
            {previewQuery.isLoading ? "Loading…" : `${count} matching`}
          </span>
          <div className="flex items-center rounded border border-line bg-surface-sunk overflow-hidden text-[10px] font-bold">
            <button
              type="button"
              onClick={() => {
                setViewMode("list");
                onViewModeChange?.("list");
              }}
              className={cn(
                "px-1.5 py-0.5 transition-colors",
                viewMode === "list" ? "bg-accent/20 text-accent" : "text-ink-muted hover:text-ink"
              )}
              title="List view"
            >
              ☰
            </button>
            <div className="w-px h-3 bg-line" />
            <button
              type="button"
              onClick={() => {
                setViewMode("grid");
                onViewModeChange?.("grid");
              }}
              className={cn(
                "px-1.5 py-0.5 transition-colors",
                viewMode === "grid" ? "bg-accent/20 text-accent" : "text-ink-muted hover:text-ink"
              )}
              title="Chart grid view"
            >
              ⊞
            </button>
          </div>
        </div>
      </div>

      {/* Membership over time — the same chart the strategy card shows, for this screen. */}
      <div className="border-b border-line">
        <button
          type="button"
          onClick={() => setMembershipOpen((v) => !v)}
          className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-[10.5px] font-semibold uppercase tracking-wide text-ink-muted hover:bg-surface-raised/50"
        >
          <span>Membership over time</span>
          <span className="font-mono text-[10px]">{membershipOpen ? "▼" : "▶"}</span>
        </button>
        {membershipOpen && (
          <div className="border-t border-line px-2.5 py-2">
            <MembershipOverTime
              spec={querySpec}
              asOf={asOf}
              onPickDate={(date) => {
                setAsOf(date);
                onAsOfChange?.(date);
              }}
            />
          </div>
        )}
      </div>

      {/* Candidates Results */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {previewQuery.isError && (
          <div className="p-4 text-center text-[12px] text-danger">
            Query failed: {(previewQuery.error as Error)?.message || "Check ClickHouse connection"}
          </div>
        )}
        {!previewQuery.isError && rows.length === 0 && !previewQuery.isLoading && (
          <div className="p-6 text-center text-[12px] text-ink-muted">
            {asOf ? "No universe candidates matched the screen criteria." : "Select a date to run the screen."}
          </div>
        )}

        {viewMode === "list" ? (
          <DataTable<RankedRow>
            rows={rows}
            columns={[...panelColumns, ...extraColumns]}
            viewId={`inline-screener.${activePresetId || "custom"}`}
            getRowId={(r) => `${r.ticker}-${r.rank}`}
            loading={previewQuery.isLoading}
            emptyLabel="No candidates matched the screen criteria."
            sortMode="server"
            sortBy={sortBy}
            fieldCatalog={fields}
            onAddColumn={handleOpenAddColumn}
            onRemoveColumn={handleRemoveColumn}
            onSortByChange={handleSortByChange}
            density="compact"
            height="fill"
          />
        ) : (
          rows.length > 0 && (
            <div
              className="grid gap-2 p-2"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}
            >
              {rows.map((r, idx) => (
                <MiniSparklineCard
                  key={`${r.ticker}-${idx}`}
                  row={r}
                  asOfDate={asOf}
                  rank={idx + 1}
                  onClick={() => onOpenTicker?.(r.ticker)}
                />
              ))}
            </div>
          )
        )}
      </div>

      {/* Unified Screen Picker Dialog */}
      <ScreenPickerDialog
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        screens={savedScreens}
        onSelectScreen={(s) => {
          onSelectSaved(s);
          setPickerOpen(false);
        }}
      />
    </div>
  );
}
