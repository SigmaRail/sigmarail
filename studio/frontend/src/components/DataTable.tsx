import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
} from "@tanstack/react-table";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "../lib/utils";
import type { ScreenField, IrOperand } from "../types";
import { FieldInfoPopover } from "./studio/FieldInfoPopover";

/**
 * GridColumn<T> — a single configurable column definition for the shared
 * DataTable. All columns are toggleable unless `always` is true.
 */
export interface GridColumn<T> {
  /** Stable key (also used for localStorage persistence + column visibility) */
  id: string;
  /** Header label */
  label: string;
  /** Optional header hint/tooltip */
  hint?: string;
  /** Optional field catalog metadata → renders a shared field-info ℹ popover in the Columns menu & header */
  info?: { label: string; description?: string; category?: string; name: string; sql_expr?: string } | null;
  /** Optional element icon in header */
  icon?: ReactNode;
  /** Accessor — a function of the row (returns raw value) */
  accessor?: (row: T) => unknown;
  /** Shorthand accessorKey when the row is a plain Record */
  accessorKey?: string;
  /** Cell renderer — receives the row + formatted raw value */
  cell?: (row: T, value: unknown) => ReactNode;
  /** Built-in formatters keyed by column.id (see FORMATTERS) */
  format?: "num" | "price" | "vol" | "pct" | "bool" | "int";
  align?: "left" | "right" | "center";
  sortable?: boolean;
  /** DB/datasource field for server-side sort (defaults to `id`). For client sort, the accessor is used. */
  sortField?: string;
  /** Always-on (cannot be toggled off, e.g. Ticker) */
  always?: boolean;
  /** Removable via the Columns ▾ menu minus glyph (dynamic/added columns) */
  removable?: boolean;
  /** Sticky position: "left" pins the column */
  sticky?: "left" | "right";
  /** Extra offset class for sticky positioning (e.g. "left-[40px]") when multiple columns are pinned on the same side */
  stickyOffset?: string;
  /** Width hint class for the header/cells */
  widthClass?: string;
  headerClass?: string;
  cellClass?: string;
}

/** A single server-side sort term — mirrors UniverseQueryV1.order_by items. */
export interface SortSpec {
  /** Allowlisted catalog field (must appear in select). Mutually exclusive with expr. */
  field?: string;
  /** Computed sort operand (ColRef / LitVal / FormulaExpr). Mutually exclusive with field. */
  expr?: IrOperand;
  /** Human label used for sort chips / pill (field label or expression text). */
  label?: string;
  direction: "asc" | "desc";
}

export interface DataTableProps<T> {
  /** Rows to render */
  rows: T[];
  /** Column config */
  columns: GridColumn<T>[];
  /** Unique persistence id (used for localStorage column visibility + order) */
  viewId: string;
  /** Optional row key accessor (defaults to index) */
  getRowId?: (row: T) => string;
  /** Optional click handler for rows */
  onRowClick?: (row: T) => void;
  /** Optional row class fn */
  rowClassName?: (row: T) => string | undefined;
  /** Optional row highlight (adds bg-highlight-soft to row + sticky cells) */
  rowHighlight?: (row: T) => boolean;
  /** Show a Columns ▾ dropdown (default true) */
  showColumnToggle?: boolean;
  /** Show a density toggle (default true) */
  showDensityToggle?: boolean;
  /** Sort mode: "client" reorders locally; "server" fires onSortByChange and does NOT reorder locally (parent re-queries). */
  sortMode?: "client" | "server";
  /** Controlled server-side sort terms (order matters). Only used when sortMode === "server". */
  sortBy?: SortSpec[];
  /** Called when the user changes server-side sort (adds/flips field, or removes a term). */
  onSortByChange?: (sortBy: SortSpec[]) => void;
  /** Enable client-side sorting (default true) */
  enableSorting?: boolean;
  /** Whether column visibility persists to localStorage (default true) */
  persistColumns?: boolean;
  /** Selection mode */
  selectionMode?: "none" | "single" | "multi";
  /** Multi-selection bound value */
  selectedRows?: RowSelectionState;
  onSelectedRowsChange?: (sel: RowSelectionState) => void;
  /** Loading overlay */
  loading?: boolean;
  /** Empty-state label */
  emptyLabel?: string;
  /** Compact (dense) by default */
  density?: "compact" | "comfortable";
  /** Initial client-side sort state (client mode only) */
  initialSorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  /** Custom toolbar slot rendered next to column/density toggles */
  toolbar?: ReactNode;
  /** Height constraint: "natural" or "fill" (flex-1 scroll) */
  height?: "natural" | "fill";
  /** Optional external control of hidden/visible columns (map id -> visible) */
  visibilityOverride?: Record<string, boolean>;
  onVisibilityChange?: (vis: Record<string, boolean>) => void;
  /** Full catalog of ScreenFields used to power the field-info browser from the Columns menu */
  fieldCatalog?: ScreenField[];
  /** When provided, a "+ Column" button appears in the toolbar; click should open the shared picker (parent). */
  onAddColumn?: () => void;
  /** Called when a user removes a non-`always` column from the Columns menu (minus glyph). */
  onRemoveColumn?: (columnId: string) => void;
}

/* ---- Built-in formatters ---------------------------------------------- */

function formatCell(
  format: GridColumn<unknown>["format"],
  value: unknown,
): string {
  if (value == null || value === "" ) return "—";
  switch (format) {
    case "num":
      return formatNum(value, 1);
    case "int":
      return formatNum(value, 0);
    case "price":
      return `$${formatNum(value, 2)}`;
    case "vol": {
      const n = Number(value);
      if (!Number.isFinite(n)) return "—";
      if (Math.abs(n) >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
      if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
      if (Math.abs(n) >= 1_000) return `${Math.round(n / 1_000)}k`;
      return String(Math.round(n));
    }
    case "pct": {
      const n = Number(value);
      if (!Number.isFinite(n)) return "—";
      return `${n.toFixed(1)}%`;
    }
    case "bool":
      return value === true || Number(value) === 1 ? "✓" : "—";
    default:
      return String(value);
  }
}

function formatNum(value: unknown, digits: number): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

/* ---- Storage helpers -------------------------------------------------- */

const toggledKey = (viewId: string) => `sigmarail-studio.table-cols.${viewId}`;
const densityKey = (viewId: string) => `sigmarail-studio.table-density.${viewId}`;

function loadToggled(viewId: string): Record<string, boolean> | null {
  try {
    const raw = localStorage.getItem(toggledKey(viewId));
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : null;
  } catch {
    return null;
  }
}

function saveToggled(viewId: string, vis: Record<string, boolean>) {
  try {
    localStorage.setItem(toggledKey(viewId), JSON.stringify(vis));
  } catch {
    /* ignore */
  }
}

function loadDensity(viewId: string): "compact" | "comfortable" {
  try {
    const raw = localStorage.getItem(densityKey(viewId));
    return raw === "comfortable" ? "comfortable" : "compact";
  } catch {
    return "compact";
  }
}

function saveDensity(viewId: string, d: "compact" | "comfortable") {
  try {
    localStorage.setItem(densityKey(viewId), d);
  } catch {
    /* ignore */
  }
}

/* ---- Component --------------------------------------------------------- */

export function DataTable<T>({
  rows,
  columns,
  viewId,
  getRowId,
  onRowClick,
  rowClassName,
  showColumnToggle = true,
  showDensityToggle = true,
  sortMode = "client",
  sortBy,
  onSortByChange,
  enableSorting = true,
  persistColumns = true,
  selectionMode = "none",
  selectedRows,
  onSelectedRowsChange,
  loading = false,
  emptyLabel = "No rows to display",
  initialSorting,
  onSortingChange,
  toolbar,
  height = "fill",
  visibilityOverride,
  onVisibilityChange,
  rowHighlight,
  fieldCatalog,
  onAddColumn,
  onRemoveColumn,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting ?? []);
  const serverSort = sortMode === "server";
  const selectionEnabled = selectionMode !== "none";
  const [density, setDensity] = useState<"compact" | "comfortable">(
    () => loadDensity(viewId),
  );

  // Column visibility state
  const defaultColsVisible = useMemo(
    () =>
      Object.fromEntries(columns.map((c) => [c.id, true])) as Record<string, boolean>,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const [columnVisibility, setColumnVisibilityState] = useState<
    Record<string, boolean>
  >(() => {
    if (visibilityOverride) return { ...defaultColsVisible, ...visibilityOverride };
    const persisted = loadToggled(viewId);
    if (persisted) {
      // merge: only include our known column ids, keep always-on true
      const merged: Record<string, boolean> = {};
      columns.forEach((c) => {
        merged[c.id] = c.always ? true : persisted[c.id] !== false;
      });
      return merged;
    }
    return defaultColsVisible;
  });

  // Sync external override
  useEffect(() => {
    if (visibilityOverride) {
      setColumnVisibilityState({ ...defaultColsVisible, ...visibilityOverride });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibilityOverride]);

  // Persist on change
  useEffect(() => {
    if (persistColumns && !visibilityOverride) saveToggled(viewId, columnVisibility);
    onVisibilityChange?.(columnVisibility);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columnVisibility]);

  const table = useReactTable<T>({
    data: rows,
    columns: useMemo(
      () => toColumnDefs(columns, selectionMode),
      [columns, selectionMode],
    ),
    state: {
      sorting,
      columnVisibility,
      ...(selectionEnabled ? { rowSelection: selectedRows ?? {} } : {}),
    },
    onSortingChange: (updater) => {
      const next =
        typeof updater === "function" ? updater(sorting) : updater;
      setSorting(next);
      onSortingChange?.(next);
    },
    onColumnVisibilityChange: setColumnVisibilityState,
    onRowSelectionChange: (updater) => {
      if (!onSelectedRowsChange) return;
      const next =
        typeof updater === "function"
          ? (updater as (prev: RowSelectionState) => RowSelectionState)(
              selectedRows ?? {},
            )
          : (updater as RowSelectionState);
      onSelectedRowsChange(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: !serverSort && enableSorting ? getSortedRowModel() : undefined,
    enableSorting: !serverSort && enableSorting,
    enableRowSelection:
      selectionMode === "multi" || selectionMode === "single",
    enableMultiRowSelection: selectionMode === "multi",
    getRowId,
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close columns menu on outside click
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menuOpen]);

  const compact = density === "compact";

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col",
        height === "fill" && "flex-1",
      )}
    >
      {/* Toolbar */}
      {(showColumnToggle || showDensityToggle || toolbar) && (
        <div className="flex items-center justify-end gap-1.5 border-b border-line bg-surface px-2 py-1.5">
          {toolbar}
          <div className="ml-auto flex items-center gap-1.5">
            {showDensityToggle && (
              <button
                type="button"
                onClick={() => {
                  const next = compact ? "comfortable" : "compact";
                  setDensity(next);
                  saveDensity(viewId, next);
                }}
                className="rounded border border-line bg-surface px-2 py-1 font-mono text-[10px] font-bold text-ink-muted hover:bg-surface-sunk"
                title="Toggle row density"
              >
                {compact ? "▤" : "▦"} Density
              </button>
            )}
            {showColumnToggle && (
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setMenuOpen((o) => !o)}
                  className="rounded border border-line bg-surface px-2 py-1 font-mono text-[10px] font-bold text-ink-muted hover:bg-surface-sunk"
                  title="Choose displayed columns"
                >
                  Columns ▾
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-full z-30 mt-1 max-h-72 min-w-56 overflow-auto rounded-lg border border-line bg-surface-raised py-1 shadow-lg">
                    {columns.map((col) => {
                      const isOn = columnVisibility[col.id] !== false;
                      const fullField = fieldCatalog
                        ? (fieldCatalog.find((f) => f.name === col.id || f.name === col.info?.name) ?? null)
                        : null;
                      return (
                        <label
                          key={col.id}
                          className={cn(
                            "flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs text-ink hover:bg-surface-sunk",
                            col.always && "opacity-50",
                          )}
                          title={col.always ? "Always visible" : col.hint}
                        >
                          <input
                            type="checkbox"
                            checked={isOn}
                            disabled={col.always}
                            onChange={() =>
                              table.getColumn(col.id)?.toggleVisibility()
                            }
                            className="rounded border-line text-accent focus:ring-accent"
                          />
                          {col.icon}
                          <span className="truncate">{col.label}</span>
                          {(col.info || fullField) && (
                            <FieldInfoPopover
                              field={(fullField ?? col.info) as unknown as ScreenField}
                              fields={fieldCatalog}
                              className="ml-auto"
                            />
                          )}
                          {col.removable && onRemoveColumn && (
                            <button
                              type="button"
                              title={`Remove ${col.label} column`}
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                onRemoveColumn(col.id);
                              }}
                              className="ml-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-surface-sunk text-[9px] text-ink-muted hover:bg-rose-500/15 hover:text-rose-500"
                            >
                              −
                            </button>
                          )}
                        </label>
                      );
                    })}
                    {onAddColumn && (
                      <div className="border-t border-line px-1 py-1">
                        <button
                          type="button"
                          onClick={onAddColumn}
                          className="w-full rounded px-2 py-1 text-left text-[11px] font-semibold text-accent hover:bg-accent/10"
                        >
                          + Add Column
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Table body */}
      <div
        ref={scrollRef}
        className={cn(
          "relative overflow-auto",
          height === "fill" && "flex-1 min-h-0",
        )}
      >
        {loading && (
          <div className="absolute inset-0 z-10 flex items-start justify-center bg-surface-raised/60 pt-16 text-xs text-ink-muted">
            Loading…
          </div>
        )}
        <table className="w-full border-collapse text-left text-[11px] leading-tight">
          <thead className="sticky top-0 z-[5]">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-line bg-surface-sunk">
                {hg.headers.map((header) => {
                  const col = header.column;
                  const cfg = columns.find((c) => c.id === col.id);
                  const sortFieldName = cfg?.sortField ?? col.id;
                  const canSort = enableSorting && (cfg?.sortable ?? true);
                  // Client-mode sort indicator comes from TanStack; server-mode from sortBy
                  const clientSorted = col.getIsSorted();
                  const serverIdx = serverSort
                    ? (sortBy ?? []).findIndex((s) => s.field === sortFieldName)
                    : -1;
                  const serverSorted = serverIdx >= 0;
                  const isDesc =
                    serverSort && serverIdx >= 0
                      ? sortBy?.[serverIdx]?.direction === "desc"
                      : false;
                  const sorted = serverSort
                    ? serverSorted
                      ? isDesc
                        ? ("desc" as const)
                        : ("asc" as const)
                      : ""
                    : clientSorted;

                  // Server-mode sort click: plain click replaces primary; shift-click adds a sort term.
                  const handleHeaderClick = (
                    ev: React.MouseEvent<HTMLTableHeaderCellElement>,
                  ) => {
                    if (serverSort) {
                      if (!canSort || !onSortByChange) return;
                      const shift = ev.shiftKey;
                      const current = sortBy ?? [];
                      const idx = current.findIndex(
                        (s) => s.field === sortFieldName,
                      );
                      if (shift) {
                        // Add / flip a secondary term
                        if (idx >= 0) {
                          const next = current
                            .slice(0, idx)
                            .concat(current.slice(idx + 1));
                          onSortByChange(next);
                        } else {
                          onSortByChange([
                            ...current,
                            { field: sortFieldName, direction: "asc" },
                          ]);
                        }
                      } else {
                        // Replace primary
                        if (idx === 0) {
                          const flip = current[0].direction === "asc"
                            ? "desc"
                            : "asc";
                          onSortByChange([
                            { field: sortFieldName, direction: flip },
                          ]);
                        } else {
                          onSortByChange([
                            { field: sortFieldName, direction: "asc" },
                          ]);
                        }
                      }
                      return;
                    }
                    if (canSort) col.getToggleSortingHandler();
                  };
                  // Selection column header (checkbox)
                  if (col.id === "__select") {
                    const some = table.getIsSomeRowsSelected();
                    const all = table.getIsAllRowsSelected();
                    return (
                      <th
                        key={header.id}
                        className="w-9 px-2 py-1.5 text-center"
                      >
                        <input
                          type="checkbox"
                          checked={all}
                          ref={(el) => {
                            if (el) el.indeterminate = some && !all;
                          }}
                          onChange={(e) =>
                            table.toggleAllRowsSelected(e.target.checked)
                          }
                          className="rounded border-line text-accent focus:ring-accent cursor-pointer"
                          title="Select all visible"
                        />
                      </th>
                    );
                  }
                  return (
                    <th
                      key={header.id}
                      onClick={handleHeaderClick}
                      title={serverSort && canSort ? `${cfg?.hint ?? col.id} (Shift-click to add as secondary sort)` : cfg?.hint}
                      className={cn(
                        "whitespace-nowrap px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-faint select-none",
                        cfg?.align === "right" && "text-right",
                        cfg?.align === "center" && "text-center",
                        canSort && "cursor-pointer hover:text-ink",
                        sorted && "text-accent font-extrabold bg-accent/5",
                        cfg?.sticky === "left" &&
                          cn(
                            "sticky bg-surface-sunk z-[6]",
                            cfg?.stickyOffset ?? "left-0",
                          ),
                        cfg?.sticky === "right" &&
                          "sticky right-0 bg-surface-sunk z-[6]",
                        cfg?.widthClass,
                        cfg?.headerClass,
                      )}
                    >
                      <span className="inline-flex items-center gap-1">
                        {cfg?.icon}
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {canSort &&
                          (serverSort && serverIdx >= 0 ? (
                            <>
                              <span className="text-[8px] text-accent font-bold ml-0.5">
                                {serverIdx + 1}
                              </span>
                              {isDesc ? (
                                <span className="text-[9px]">▼</span>
                              ) : (
                                <span className="text-[9px]">▲</span>
                              )}
                            </>
                          ) : (
                            sorted === "asc" ? (
                              <span className="text-[9px]">▲</span>
                            ) : sorted === "desc" ? (
                              <span className="text-[9px]">▼</span>
                            ) : (
                              <span className="text-[9px] text-ink-faint opacity-60">
                                ↕
                              </span>
                            )
                          ))}
                      </span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-line/40">
            {table.getRowModel().rows.length === 0 && !loading ? (
              <tr>
                <td
                  colSpan={table.getVisibleLeafColumns().length}
                  className="px-3 py-10 text-center text-ink-muted"
                >
                  {emptyLabel}
                </td>
              </tr>
            ) : null}
            {table.getRowModel().rows.map((row) => {
              const rowCfgClass = rowClassName?.(row.original);
              const highlighted = rowHighlight?.(row.original) ?? false;
              return (
                <tr
                  key={row.id}
                  onClick={() => onRowClick?.(row.original)}
                  className={cn(
                    "border-b border-line/70 transition-colors",
                    onRowClick && "cursor-pointer",
                    selectionEnabled && row.getIsSelected()
                      ? "bg-highlight-soft"
                      : "hover:bg-surface-sunk/80",
                    highlighted && "bg-highlight-soft",
                    highlighted && "hover:bg-highlight-soft",
                    rowCfgClass,
                  )}
                >
                  {row.getVisibleCells().map((cell) => {
                    const cfg = columns.find(
                      (c) => c.id === cell.column.id,
                    );
                    // Selection cell (checkbox)
                    if (cell.column.id === "__select") {
                      return (
                        <td key={cell.id} className="px-2 py-1 text-center">
                          <input
                            type="checkbox"
                            checked={row.getIsSelected()}
                            onChange={(e) =>
                              row.toggleSelected(e.target.checked)
                            }
                            onClick={(e) => e.stopPropagation()}
                            className="rounded border-line text-accent focus:ring-accent cursor-pointer"
                          />
                        </td>
                      );
                    }
                    return (
                      <td
                        key={cell.id}
                        className={cn(
                          "px-2.5 font-mono tabular-nums text-ink",
                          compact ? "py-1" : "py-2",
                          cfg?.align === "right" && "text-right",
                          cfg?.align === "center" && "text-center",
                          cfg?.sticky === "left" &&
                            (highlighted
                              ? cn(
                                  "sticky bg-highlight-soft z-[2]",
                                  cfg?.stickyOffset ?? "left-0",
                                )
                              : cn(
                                  "sticky bg-surface z-[2]",
                                  cfg?.stickyOffset ?? "left-0",
                                )),
                          cfg?.sticky === "right" &&
                            (highlighted
                              ? "sticky right-0 bg-highlight-soft z-[2]"
                              : "sticky right-0 bg-surface z-[2]"),
                          cfg?.widthClass,
                          cfg?.cellClass,
                        )}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---- Convert GridColumn<T> to ColumnDef<T> ----------------------------- */

function toColumnDefs<T>(
  columns: GridColumn<T>[],
  selectionMode: DataTableProps<T>["selectionMode"] = "none",
): ColumnDef<T, unknown>[] {
  const defs: ColumnDef<T, unknown>[] = columns.map((c) => {
    const always = c.always;
    return {
      id: c.id,
      header: c.label,
      accessorFn: c.accessor
        ? c.accessor
        : c.accessorKey
          ? (row) => (row as Record<string, unknown>)?.[c.accessorKey as string]
          : undefined,
      cell: (ctx) => {
        const row = ctx.row.original;
        const value = ctx.getValue();
        const rendered = c.cell
          ? c.cell(row, value)
          : c.format
            ? formatCell(c.format, value)
            : String(value ?? "—");
        return <>{rendered}</>;
      },
      enableSorting: c.sortable ?? true,
      enableHiding: !always,
    };
  });
  if (selectionMode !== "none") {
    defs.unshift({
      id: "__select",
      header: "",
      enableSorting: false,
      enableHiding: false,
      cell: () => null,
    });
  }
  return defs;
}

export { toColumnDefs, formatCell, loadToggled, saveToggled };
