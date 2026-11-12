import type { AppliedFilterRow, ComparisonOp, ScreenField } from "../types";
import {
  OP_LABELS,
  defaultFilterRow,
  formatOperand,
  operandKind,
  parseOperandInput,
} from "../lib/irFilters";
import { cn } from "../lib/utils";

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
          <button
            type="button"
            onClick={addRow}
            className="rounded border border-line bg-surface-sunk px-2 py-0.5 text-[11px] font-medium text-ink hover:border-accent hover:bg-accent-soft"
          >
            + Add
          </button>
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
        <button
          type="button"
          onClick={onRemove}
          className="text-[10px] text-danger hover:underline"
          aria-label="Remove filter"
        >
          Remove
        </button>
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
        <select
          value={row.op}
          onChange={(e) =>
            onChange({ op: e.target.value as ComparisonOp })
          }
          className="h-7 rounded border border-line bg-surface-sunk px-1 font-mono text-[11px]"
        >
          {OPS.map((op) => (
            <option key={op} value={op}>
              {OP_LABELS[op]}
            </option>
          ))}
        </select>
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
          <button
            key={k}
            type="button"
            onClick={() => onKindChange(k)}
            className={cn(
              "rounded px-1 py-0.5 text-[9px] uppercase tracking-wide",
              kind === k
                ? "bg-accent text-white"
                : "bg-surface-sunk text-ink-muted hover:text-ink",
            )}
          >
            {k === "field" ? "field" : k}
          </button>
        ))}
      </div>
      {kind === "field" && fieldNames.length > 0 ? (
        <select
          value={value.type === "col" ? value.name : ""}
          onChange={(e) => onTextChange(e.target.value)}
          className="h-7 w-full truncate rounded border border-line bg-surface-sunk px-1 font-mono text-[11px]"
        >
          {!fieldNames.includes(display) ? (
            <option value={display}>{display}</option>
          ) : null}
          {fieldNames.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      ) : (
        <input
          value={display}
          onChange={(e) => onTextChange(e.target.value)}
          placeholder={kind === "formula" ? "col * 1.3" : "value"}
          className="h-7 w-full rounded border border-line bg-surface-sunk px-1.5 font-mono text-[11px]"
        />
      )}
    </div>
  );
}
