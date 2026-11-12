import type { AppliedFilterRow, IrWhereNode, ScreenField } from "../../types";
import type { SlotExpr } from "../strategy/StrategyDocument";
import { FilterChipBar } from "./FilterChipBar";
import { extractAppliedFilters, rowsToWhere } from "../../lib/irFilters";

type Props = {
  label: string;
  hint?: string;
  fields: ScreenField[];
  value: SlotExpr | null | undefined;
  onChange: (next: SlotExpr | null) => void;
};

/** Bool SlotExpr editor reusing FilterChipBar (same AST as stage filters). */
export function SlotBoolExprRow({ label, hint, fields, value, onChange }: Props) {
  const rows: AppliedFilterRow[] =
    value?.kind === "bool" && value.where
      ? extractAppliedFilters(value.where as IrWhereNode).rows
      : [];

  function handleChange(next: AppliedFilterRow[]) {
    if (!next.length) {
      onChange(null);
      return;
    }
    onChange({ kind: "bool", where: rowsToWhere(next) as Record<string, unknown> });
  }

  return (
    <div className="rounded border border-dashed border-line bg-surface-raised/30 p-2 space-y-1">
      <div className="text-[10.5px] font-semibold text-ink">{label}</div>
      {hint ? <p className="text-[10px] text-ink-muted leading-tight">{hint}</p> : null}
      <FilterChipBar
        fields={fields}
        filterRows={rows}
        onFilterRowsChange={handleChange}
      />
    </div>
  );
}
