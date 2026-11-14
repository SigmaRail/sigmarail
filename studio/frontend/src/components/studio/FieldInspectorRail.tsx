import type { ScreenField } from "../../types";
import { cn } from "../../lib/utils";

interface FieldInspectorRailProps {
  field: ScreenField | null;
  isOpen: boolean;
  onClose?: () => void;
  onAddFilter?: (field: ScreenField) => void;
  onSetSort?: (field: ScreenField) => void;
  currentSortField?: string;
  isFiltered?: boolean;
}

export function FieldInspectorRail({
  field,
  isOpen,
  onClose,
  onAddFilter,
  onSetSort,
  currentSortField,
}: FieldInspectorRailProps) {
  if (!isOpen || !field) {
    return null;
  }

  const isCurrentSort = currentSortField === field.name;

  return (
    <aside className="flex h-full w-80 flex-shrink-0 flex-col border-l border-line bg-surface-raised shadow-xl animate-in slide-in-from-right-4 duration-150 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5 bg-surface">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded bg-accent/15 text-accent text-xs font-bold">
            ℹ️
          </span>
          <div>
            <h4 className="text-xs font-bold text-ink leading-none">{field.label}</h4>
            <span className="font-mono text-[10px] text-ink-muted leading-none">
              {field.sql_expr || field.name}
            </span>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-ink-muted hover:bg-surface-sunk hover:text-ink transition-colors"
            title="Close Inspector"
          >
            ✕
          </button>
        )}
      </div>

      {/* Body Content */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4 text-xs">
        {/* Category & Type Pills */}
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="rounded-full bg-accent/10 border border-accent/25 px-2 py-0.5 text-[10px] font-semibold text-accent">
            {field.category_label || field.category}
          </span>
          {field.type && (
            <span className="rounded-full bg-surface-sunk border border-line px-2 py-0.5 font-mono text-[10px] text-ink-muted">
              {field.type}
            </span>
          )}
          {field.table && (
            <span className="rounded-full bg-surface-sunk border border-line px-2 py-0.5 font-mono text-[9.5px] text-ink-muted truncate max-w-[150px]" title={field.table}>
              {field.table.replace("screener_", "")}
            </span>
          )}
        </div>

        {/* Description / Definition */}
        <div className="space-y-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
            Metric Definition & AST Meaning
          </label>
          <div className="rounded-lg border border-line bg-surface p-2.5 text-[11.5px] leading-relaxed text-ink shadow-xs">
            {field.description || "Database screener metric available for universe filtering and sorting."}
          </div>
        </div>

        {/* AST Representation / ClickHouse Table Mapping */}
        <div className="space-y-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
            ClickHouse AST Projection
          </label>
          <div className="rounded border border-line bg-surface-sunk p-2 font-mono text-[10.5px] text-ink-muted space-y-1">
            <div className="flex justify-between">
              <span className="text-ink-muted/70">Physical Column:</span>
              <span className="text-ink font-semibold">{field.name}</span>
            </div>
            {field.table && (
              <div className="flex justify-between">
                <span className="text-ink-muted/70">Source Table:</span>
                <span className="text-ink">{field.table}</span>
              </div>
            )}
            {field.sql_expr && (
              <div className="flex justify-between">
                <span className="text-ink-muted/70">Expression:</span>
                <span className="text-accent font-semibold">{field.sql_expr}</span>
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="space-y-2 pt-1 border-t border-line">
          <label className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
            Quick Actions
          </label>
          <div className="grid grid-cols-1 gap-2">
            {onAddFilter && (
              <button
                type="button"
                onClick={() => onAddFilter(field)}
                className="flex items-center justify-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-[11px] font-bold text-accent hover:bg-accent/20 transition-all"
              >
                <span>+</span>
                <span>Add Filter on {field.label}</span>
              </button>
            )}
            {onSetSort && (
              <button
                type="button"
                onClick={() => onSetSort(field)}
                disabled={isCurrentSort}
                className={cn(
                  "flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-[11px] font-bold transition-all",
                  isCurrentSort
                    ? "border-line bg-surface-sunk text-ink-muted cursor-default"
                    : "border-line bg-surface text-ink hover:border-accent hover:text-accent"
                )}
              >
                <span>↕</span>
                <span>{isCurrentSort ? "Active Sort Field" : `Sort by ${field.label}`}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
