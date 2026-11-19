import type { AppliedFilterRow, ComparisonOp, ScreenField } from "../types";
import {
  OP_LABELS,
  defaultFilterRow,
  formatOperand,
  operandKind,
  parseOperandInput,
} from "../lib/irFilters";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

const OPS: ComparisonOp[] = ["gt", "gte", "lt", "lte", "eq", "neq"];

export function AppliedFiltersPanel({
  rows,
  fields,
  enabled,
  onChange,
}: {
  rows: AppliedFilterRow[];
  fields: ScreenField[];
  enabled: boolean;
  onChange: (rows: AppliedFilterRow[]) => void;
}) {
  const fieldNames = fields.map((f) => f.name);

  const updateRow = (id: string, patch: Partial<AppliedFilterRow>) => {
    onChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const removeRow = (id: string) => {
    onChange(rows.filter((r) => r.id !== id));
  };

  const addRow = () => {
    onChange([...rows, defaultFilterRow()]);
  };

  return (
    <div className="flex max-h-[45%] min-h-0 flex-col border-b border-line">
      <div className="flex shrink-0 items-center justify-between border-b border-line px-3 py-2">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Applied filters
          </div>
          <div className="text-[11px] text-ink-muted">
            {enabled ? "ALL group · universe_query_v1" : "Select an IR template"}
          </div>
        </div>
        {enabled ? (
          <Button
            type="button"
            onClick={addRow}
            variant="outline"
            size="sm"
            className="h-7 px-2 text-[11px]"
          >
            + Add
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {!enabled ? (
          <p className="px-1 py-2 text-[11px] text-ink-muted">
            Preset screens use server-side criteria. Pick Minervini or CANSLIM
            (Templates) to edit filters here.
          </p>
        ) : rows.length === 0 ? (
          <p className="px-1 py-2 text-[11px] text-ink-muted">
            No filters — add one or pick a template.
          </p>
        ) : (
          rows.map((row) => (
            <FilterRowEditor
              key={row.id}
              row={row}
              fieldNames={fieldNames}
              onChange={(patch) => updateRow(row.id, patch)}
              onRemove={() => removeRow(row.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function FilterRowEditor({
  row,
  fieldNames,
  onChange,
  onRemove,
}: {
  row: AppliedFilterRow;
  fieldNames: string[];
  onChange: (patch: Partial<AppliedFilterRow>) => void;
  onRemove: () => void;
}) {
  if (row.readOnly) {
    return (
      <div className="rounded border border-dashed border-line bg-surface-sunk/60 px-2 py-1.5 text-[10px] text-ink-muted">
        Nested group (display-only)
        <pre className="mt-1 max-h-16 overflow-auto font-mono text-[9px]">
          {JSON.stringify(row.raw, null, 0)}
        </pre>
      </div>
    );
  }

  const leftKind = operandKind(row.left);
  const rightKind = operandKind(row.right);

  return (
    <div className="rounded border border-line bg-surface-raised p-1.5 shadow-panel">
      <div className="mb-1 flex items-center justify-between gap-1">
        <span className="font-mono text-[10px] text-ink-faint">
          {formatOperand(row.left)} {OP_LABELS[row.op]}{" "}
          {formatOperand(row.right)}
        </span>
        <Button
          type="button"
          onClick={onRemove}
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-[10px] text-destructive"
          aria-label="Remove filter"
        >
          Remove
        </Button>
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] gap-1">
        <OperandEditor
          kind={leftKind}
          value={row.left}
          fieldNames={fieldNames}
          onKindChange={(kind) =>
            onChange({
              left: parseOperandInput(
                kind,
                kind === "field"
                  ? "close"
                  : kind === "lit"
                    ? "0"
                    : "close * 1",
                row.left,
              ),
            })
          }
          onTextChange={(text) =>
            onChange({ left: parseOperandInput(leftKind, text, row.left) })
          }
        />
        <Select value={row.op} onValueChange={(value) => onChange({ op: value as ComparisonOp })}>
          <SelectTrigger className="h-8 min-w-14 px-2 font-mono text-[11px]" aria-label="Comparison operator">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OPS.map((op) => <SelectItem key={op} value={op}>{OP_LABELS[op]}</SelectItem>)}
          </SelectContent>
        </Select>
        <OperandEditor
          kind={rightKind}
          value={row.right}
          fieldNames={fieldNames}
          onKindChange={(kind) =>
            onChange({
              right: parseOperandInput(
                kind,
                kind === "field"
                  ? "sma50d"
                  : kind === "lit"
                    ? "70"
                    : "low_52w * 1.3",
                row.right,
              ),
            })
          }
          onTextChange={(text) =>
            onChange({ right: parseOperandInput(rightKind, text, row.right) })
          }
        />
      </div>
    </div>
  );
}

function OperandEditor({
  kind,
  value,
  fieldNames,
  onKindChange,
  onTextChange,
}: {
  kind: "field" | "lit" | "formula";
  value: AppliedFilterRow["left"];
  fieldNames: string[];
  onKindChange: (kind: "field" | "lit" | "formula") => void;
  onTextChange: (text: string) => void;
}) {
  const display =
    kind === "field" && value.type === "col"
      ? value.name
      : kind === "lit" && value.type === "lit"
        ? String(value.value)
        : formatOperand(value);

  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <div className="flex gap-0.5">
        {(["field", "lit", "formula"] as const).map((k) => (
          <Button
            key={k}
            type="button"
            onClick={() => onKindChange(k)}
            variant={kind === k ? "secondary" : "ghost"}
            size="sm"
            className="h-6 px-1.5 text-[9px] uppercase tracking-wide"
          >
            {k === "field" ? "field" : k}
          </Button>
        ))}
      </div>
      {kind === "field" && fieldNames.length > 0 ? (
        <Select value={value.type === "col" ? value.name : display} onValueChange={onTextChange}>
          <SelectTrigger className="h-8 w-full px-2 font-mono text-[11px]" aria-label="Filter field">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {!fieldNames.includes(display) && display ? <SelectItem value={display}>{display}</SelectItem> : null}
            {fieldNames.map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
          </SelectContent>
        </Select>
      ) : (
        <Input
          value={display}
          onChange={(e) => onTextChange(e.target.value)}
          placeholder={kind === "formula" ? "col * 1.3" : "value"}
          aria-label={kind === "formula" ? "Filter formula" : "Filter value"}
          className="h-8 w-full px-2 font-mono text-[11px]"
        />
      )}
    </div>
  );
}
