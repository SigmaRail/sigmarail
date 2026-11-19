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
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  useTableViewPreferences,
  saveStoredTableViewPreferences,
} from "../lib/tablePreferences";
import { cn } from "../lib/utils";
import type { ScreenField, IrOperand } from "../types";
import { FieldInfoPopover } from "./studio/FieldInfoPopover";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Button } from "@sb/webapp-core/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@sb/webapp-core/components/ui/dropdown-menu";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

/**
 * GridColumn<T> — a single configurable column definition for the shared
 * DataTable. All columns are toggleable unless `always` is true.
 */
export interface GridColumn<T> {
  /** Stable key used to persist this view's column and density preferences. */
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
  /** Unique persistence id used for this table's user preferences. */
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
  /** Whether column visibility persists to the signed-in profile (default true) */
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
  const tablePreferences = useTableViewPreferences(viewId);
  const columnsSignature = columns.map((column) => `${column.id}:${column.always ? 1 : 0}`).join("|");
  const [hydratedViewId, setHydratedViewId] = useState<string | null>(null);
  const userChangedColumns = useRef(false);
  const userChangedDensity = useRef(false);
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");

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
    return defaultColsVisible;
  });

  // Sync external override
  useEffect(() => {
    userChangedColumns.current = false;
    userChangedDensity.current = false;
    setHydratedViewId(null);
  }, [viewId]);

  useEffect(() => {
    if (!tablePreferences.loaded) return;
    if (persistColumns && !visibilityOverride && !userChangedColumns.current) {
      const persisted = tablePreferences.preference?.columns;
      if (persisted) {
        const merged: Record<string, boolean> = {};
        columns.forEach((column) => {
          merged[column.id] = column.always ? true : persisted[column.id] !== false;
        });
        setColumnVisibilityState(merged);
      }
    }
    if (!userChangedDensity.current) {
      const densityPreference = tablePreferences.preference?.density;
      setDensity(densityPreference ?? "compact");
    }
    if (tablePreferences.preference) {
      saveStoredTableViewPreferences(viewId, tablePreferences.preference, tablePreferences.userId);
    }
    setHydratedViewId(viewId);
  }, [tablePreferences.loaded, tablePreferences.preference, viewId, visibilityOverride, persistColumns, columnsSignature]);

  useEffect(() => {
    if (visibilityOverride) {
      setColumnVisibilityState({ ...defaultColsVisible, ...visibilityOverride });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibilityOverride]);

  // Persist on change
  useEffect(() => {
    if (persistColumns && !visibilityOverride && hydratedViewId === viewId && userChangedColumns.current) {
      tablePreferences.save({ columns: columnVisibility });
      userChangedColumns.current = false;
    }
    onVisibilityChange?.(columnVisibility);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columnVisibility, hydratedViewId, viewId, persistColumns, visibilityOverride, tablePreferences.save]);

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
    onColumnVisibilityChange: (updater) => {
      userChangedColumns.current = true;
      setColumnVisibilityState(updater);
    },
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
              <Button
                type="button"
                onClick={() => {
                  const next = compact ? "comfortable" : "compact";
                  userChangedDensity.current = true;
                  setDensity(next);
                  tablePreferences.save({ density: next });
                }}
                variant="outline"
                size="sm"
                className="h-8 px-2 font-mono text-[10px] font-bold text-muted-foreground"
                title="Toggle row density"
              >
                {compact ? "▤" : "▦"} Density
              </Button>
            )}
            {showColumnToggle && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button type="button" variant="outline" size="sm" className="h-8 px-2 font-mono text-[10px] font-bold text-muted-foreground">
                    Columns
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="max-h-[min(70dvh,28rem)] min-w-56 overflow-y-auto">
                    {columns.map((col) => {
                      const isOn = columnVisibility[col.id] !== false;
                      const fullField = fieldCatalog
                        ? (fieldCatalog.find((f) => f.name === col.id || f.name === col.info?.name) ?? null)
                        : null;
                      return (
                        <Fragment key={col.id}>
                          <DropdownMenuCheckboxItem
                            checked={isOn}
                            disabled={col.always}
                            onCheckedChange={() => table.getColumn(col.id)?.toggleVisibility()}
                            onSelect={(event) => event.preventDefault()}
                            className="gap-2 pr-2 text-xs"
                            title={col.always ? "Always visible" : col.hint}
                          >
                            {col.icon}
                            <span className="truncate">{col.label}</span>
                            {(col.info || fullField) && (
                              <FieldInfoPopover
                                field={(fullField ?? col.info) as unknown as ScreenField}
                                fields={fieldCatalog}
                                className="ml-auto"
                              />
                            )}
                          </DropdownMenuCheckboxItem>
                          {col.removable && onRemoveColumn && (
                            <DropdownMenuItem
                              onSelect={(event) => {
                                event.preventDefault();
                                onRemoveColumn(col.id);
                              }}
                              className="pl-8 text-xs text-destructive"
                            >
                              Remove {col.label}
                            </DropdownMenuItem>
                          )}
                        </Fragment>
                      );
                    })}
                    {onAddColumn && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onSelect={onAddColumn} className="text-xs font-medium">
                          + Add column
                        </DropdownMenuItem>
                      </>
                    )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      )}

      {/* Table body */}
      <div
        ref={scrollRef}
        className={cn(
          "relative overflow-hidden",
          height === "fill" && "flex-1 min-h-0",
        )}
      >
        {loading && (
          <div className="absolute inset-0 z-10 flex items-start justify-center bg-surface-raised/60 pt-16 text-xs text-ink-muted">
            Loading…
          </div>
        )}
        <WorkspaceTable
          containerClassName={height === "fill" ? "h-full min-h-0" : undefined}
          className="border-collapse text-left text-[11px] leading-tight"
        >
          <WorkspaceTableHeader className="sticky top-0 z-[5]">
            {table.getHeaderGroups().map((hg) => (
              <WorkspaceTableRow key={hg.id} className="border-b border-line bg-muted/70 hover:bg-muted/70">
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
                      <WorkspaceTableHead
                        key={header.id}
                        className="h-auto w-9 px-2 py-1.5 text-center"
                      >
                        <Checkbox
                          label=""
                          checked={some && !all ? "indeterminate" : all}
                          onCheckedChange={(checked) => table.toggleAllRowsSelected(checked === true)}
                          aria-label="Select all visible"
                          title="Select all visible"
                          className="justify-center"
                        />
                      </WorkspaceTableHead>
                    );
                  }
                  return (
                    <WorkspaceTableHead
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
                    </WorkspaceTableHead>
                  );
                })}
              </WorkspaceTableRow>
            ))}
          </WorkspaceTableHeader>
          <WorkspaceTableBody className="divide-y divide-border/60">
            {table.getRowModel().rows.length === 0 && !loading ? (
              <WorkspaceTableRow>
                <WorkspaceTableCell
                  colSpan={table.getVisibleLeafColumns().length}
                  className="px-3 py-10 text-center text-ink-muted"
                >
                  {emptyLabel}
                </WorkspaceTableCell>
              </WorkspaceTableRow>
            ) : null}
            {table.getRowModel().rows.map((row) => {
              const rowCfgClass = rowClassName?.(row.original);
              const highlighted = rowHighlight?.(row.original) ?? false;
              return (
                <WorkspaceTableRow
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
                      <WorkspaceTableCell key={cell.id} className="px-2 py-1 text-center">
                        <Checkbox
                          label=""
                          checked={row.getIsSelected()}
                          onCheckedChange={(checked) => row.toggleSelected(checked === true)}
                          onClick={(event) => event.stopPropagation()}
                          aria-label="Select row"
                          className="justify-center"
                        />
                      </WorkspaceTableCell>
                      );
                    }
                    return (
                      <WorkspaceTableCell
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
                      </WorkspaceTableCell>
                    );
                  })}
                </WorkspaceTableRow>
              );
            })}
          </WorkspaceTableBody>
        </WorkspaceTable>
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

export { toColumnDefs, formatCell };
