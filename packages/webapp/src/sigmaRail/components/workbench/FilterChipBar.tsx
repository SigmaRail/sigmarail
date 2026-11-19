import { useMemo } from "react";
import { cn } from "../../lib/utils";
import type { AppliedFilterRow, ScreenField } from "../../types";
import type { FieldPick } from "../../lib/fieldPick";
import { formatFilterRowToExpression, parseExpressionToFilterRows } from "../../lib/formulaParser";
import { useFieldPicker } from "./FieldPickerProvider";
import { Button } from "@sb/webapp-core/components/ui/button";

interface FilterChipBarProps {
  filterRows: AppliedFilterRow[];
  fields: ScreenField[];
  onFilterRowsChange: (rows: AppliedFilterRow[]) => void;
  onFocusField?: (field: ScreenField | null) => void;
}

interface LinterWarningItem {
  id: string;
  message: string;
  quickFix?: {
    label: string;
    action: () => void;
  };
}

export function FilterChipBar({
  filterRows,
  fields,
  onFilterRowsChange,
  onFocusField,
}: FilterChipBarProps) {
  const { openPicker } = useFieldPicker();

  function applyPickToRow(pick: FieldPick, existingId?: string): boolean {
    const text = pick.kind === "predicate" ? pick.text : pick.kind === "expr" ? pick.text : "";
    if (!text.trim()) return false;
    const parsed = parseExpressionToFilterRows(text, existingId ?? `f-${Date.now()}`);
    if (parsed.error || parsed.rows.length === 0) return false;
    if (existingId) {
      const idx = filterRows.findIndex((r) => r.id === existingId);
      const next = [...filterRows];
      if (idx >= 0) next.splice(idx, 1, ...parsed.rows);
      else next.push(...parsed.rows);
      onFilterRowsChange(next);
    } else {
      onFilterRowsChange([...filterRows, ...parsed.rows]);
    }
    return true;
  }

  function openAdd() {
    openPicker({
      use: "filter",
      fields,
      title: "Add Filter",
      actionLabel: "Add Filter",
      initialExpression: "",
      onPick: (pick) => applyPickToRow(pick),
    });
  }

  function openEdit(row: AppliedFilterRow) {
    const text = formatFilterRowToExpression(row);
    openPicker({
      use: "filter",
      fields,
      title: "Edit Filter",
      actionLabel: "Save Filter",
      initialExpression: text,
      onPick: (pick) => applyPickToRow(pick, row.id),
    });
  }

  function removeFilter(id: string) {
    onFilterRowsChange(filterRows.filter((r) => r.id !== id));
  }

  const linterWarnings = useMemo((): LinterWarningItem[] => {
    const warnings: LinterWarningItem[] = [];

    const filterFieldNames = filterRows.map((r) =>
      r.left.type === "col" ? r.left.name.toLowerCase() : ""
    );

    const hasIpoFilter = filterFieldNames.some((n) => n.includes("ipo"));
    const hasHighRsFilter = filterRows.some((r) => {
      const name = r.left.type === "col" ? r.left.name.toLowerCase() : "";
      return name.includes("rs_rating") && r.right.type === "lit" && Number(r.right.value) >= 70;
    });

    const longLookbackRow = filterRows.find((r) => {
      const name = r.left.type === "col" ? r.left.name.toLowerCase() : "";
      return name.includes("sma200") || name.includes("perf_1y") || name.includes("yearly");
    });

    const pennyRow = filterRows.find((r) => {
      const name = r.left.type === "col" ? r.left.name.toLowerCase() : "";
      return (
        (name === "close" || name === "price" || name === "closeadj") &&
        (r.op === "lt" || r.op === "lte") &&
        r.right.type === "lit" &&
        Number(r.right.value) <= 5
      );
    });

    const hasBroadMarketMetric = filterFieldNames.some(
      (n) => n.includes("rs_rating") || n.includes("accumulation_distribution")
    );

    if (hasIpoFilter && (hasHighRsFilter || longLookbackRow)) {
      warnings.push({
        id: "ipo_lookback",
        message:
          "Lookback Conflict: Recent IPOs lack 252 trading days. Metrics like RS Rating and 200 SMA penalize or return NULL for young listings.",
        quickFix: longLookbackRow
          ? {
              label: longLookbackRow.left.type === "col" ? longLookbackRow.left.name : "annual lookback",
              action: () => {
                onFilterRowsChange(filterRows.filter((r) => r.id !== longLookbackRow.id));
              },
            }
          : undefined,
      });
    }

    if (pennyRow && hasBroadMarketMetric) {
      const col = pennyRow.left.type === "col" ? pennyRow.left.name : "price";
      warnings.push({
        id: "penny_rs",
        message:
          "Universe Restriction: RS Rating and technical ratings require broad market constituent membership. Penny stocks under $5 are pruned upstream.",
        quickFix: {
          label: col + " >= $5",
          action: () => {
            onFilterRowsChange(
              filterRows.map((r) =>
                r.id === pennyRow.id
                  ? { ...r, op: "gte" as const, right: { type: "lit" as const, value: 5 } }
                  : r
              )
            );
          },
        },
      });
    }

    const invalidVolRow = filterRows.find((r) => {
      const name = r.left.type === "col" ? r.left.name.toLowerCase() : "";
      return (
        name.includes("vol") &&
        (r.op === "lte" || r.op === "lt") &&
        r.right.type === "lit" &&
        Number(r.right.value) <= 0
      );
    });
    if (invalidVolRow) {
      warnings.push({
        id: "invalid_vol",
        message:
          "Non-positive Volume Threshold: Filtering for non-positive trading volume excludes all active equities.",
        quickFix: {
          label: "Change to volume > 0",
          action: () => {
            onFilterRowsChange(
              filterRows.map((r) =>
                r.id === invalidVolRow.id
                  ? { ...r, op: "gt" as const, right: { type: "lit" as const, value: 0 } }
                  : r
              )
            );
          },
        },
      });
    }

    return warnings;
  }, [filterRows, onFilterRowsChange]);

  return (
    <div className="space-y-1 py-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {filterRows.length === 0 && (
          <span className="text-[10.5px] text-ink-faint italic">
            No filters active -- all universe candidates match
          </span>
        )}

        {filterRows.map((row) => {
          const colName = row.left.type === "col" ? row.left.name : undefined;
          const chipFieldObj = colName
            ? fields.find((f) => f.name === colName || f.prefixed_name === colName)
            : undefined;
          const chipLabelText = formatFilterRowToExpression(row);
          return (
            <div
              key={row.id}
              className="inline-flex items-center"
              onMouseEnter={() => {
                if (chipFieldObj && onFocusField) onFocusField(chipFieldObj);
              }}
            >
              <div
                className={cn(
                  "group inline-flex min-h-10 max-w-full items-center rounded-full border transition-colors",
                  row.readOnly
                    ? "border-line bg-surface-raised opacity-70 text-ink-muted"
                    : row.annotation?.source === "agent"
                      ? "border-accent/70 bg-accent/10 text-ink ring-1 ring-accent/40"
                      : "border-line bg-surface-raised hover:border-accent/60 hover:bg-surface-sunk text-ink"
                )}
              >
                <Button
                  type="button"
                  disabled={row.readOnly}
                  onClick={() => openEdit(row)}
                  title={row.annotation?.rationale ?? (row.readOnly ? "Preset IR condition" : "Edit filter")}
                  variant="ghost"
                  className="h-auto min-h-10 min-w-0 justify-start gap-1.5 rounded-l-full px-3 py-1 text-left font-mono text-[10.5px] disabled:cursor-default"
                >
                  <span className="min-w-0 select-none break-words">{chipLabelText}</span>
                  {row.annotation?.rationale ? (
                    <span className="shrink-0 rounded bg-accent/20 px-1 font-sans text-[8px] uppercase tracking-wide text-accent-ink">
                      why
                    </span>
                  ) : null}
                  {!row.readOnly && <span className="shrink-0 font-sans text-[9px] text-ink-faint group-hover:text-accent">Edit</span>}
                </Button>
                {!row.readOnly && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeFilter(row.id)}
                    className="mr-0.5 h-9 w-9 shrink-0 rounded-full text-ink-faint hover:bg-danger/10 hover:text-danger"
                    aria-label={"Remove filter " + chipLabelText}
                    title="Remove filter"
                  >
                    <span aria-hidden="true">×</span>
                  </Button>
                )}
              </div>
            </div>
          );
        })}

        <Button
          type="button"
          variant="outline"
          onClick={openAdd}
          className="min-h-10 border-dashed border-accent/60 bg-accent/5 px-3 text-xs font-semibold text-accent hover:bg-accent/15"
        >
          + Add Filter
        </Button>
      </div>

      {linterWarnings.length > 0 && (
        <div className="space-y-1 pt-0.5">
          {linterWarnings.map((w) => (
            <div
              key={w.id}
              className="flex items-center justify-between gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[10px] text-amber-300"
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-xs flex-shrink-0">!</span>
                <span className="truncate">{w.message}</span>
              </div>
              {w.quickFix && (
                <Button
                  type="button"
                  onClick={w.quickFix.action}
                  variant="outline"
                  size="sm"
                  className="h-auto flex-shrink-0 border-amber-500/40 bg-amber-500/20 px-2 py-0.5 text-[9.5px] font-semibold text-amber-200 hover:bg-amber-500/30 hover:text-amber-100"
                >
                  Quick Fix: {w.quickFix.label}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default FilterChipBar;
