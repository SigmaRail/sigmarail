import type { ReactNode } from "react";
import type { ScreenField } from "../../types";
import { Button } from "@sb/webapp-core/components/ui/button";

type AstRecord = Record<string, unknown>;

function record(value: unknown): AstRecord | null {
  return value && typeof value === "object" ? value as AstRecord : null;
}

function operandText(value: unknown, labels: Map<string, string>): string {
  const item = record(value);
  if (!item) return "?";
  if (item.type === "col") {
    const name = String(item.name ?? "?");
    const label = labels.get(name) ?? name.replaceAll("_", " ");
    const offset = Number(item.offset ?? 0);
    return offset ? `${label} (${offset > 0 ? "+" : ""}${offset}d)` : label;
  }
  if (item.type === "lit") {
    const literal = item.value;
    if (typeof literal === "string") return `“${literal}”`;
    if (typeof literal === "boolean") return literal ? "true" : "false";
    return String(literal ?? "?");
  }
  if (item.type === "formula" && Array.isArray(item.args)) {
    return item.args.map((arg) => operandText(arg, labels)).join(` ${String(item.op ?? "?")} `);
  }
  return "expression";
}

function describeNode(value: unknown, labels: Map<string, string>, nested = false): string {
  const node = record(value);
  if (!node) return "";
  if ((node.type === "all" || node.type === "any") && Array.isArray(node.items)) {
    const parts = node.items.map((item) => describeNode(item, labels, true)).filter(Boolean);
    if (!parts.length) return "";
    const joined = parts.join(node.type === "all" ? " and " : " or ");
    return parts.length === 1 || !nested ? joined : `(${joined})`;
  }
  if (node.type === "not") return `not ${describeNode(node.item, labels, true)}`;
  const operators: Record<string, string> = {
    eq: "=", neq: "≠", gt: ">", gte: "≥", lt: "<", lte: "≤",
  };
  const operator = operators[String(node.type)];
  if (!operator) return "custom condition";
  return `${operandText(node.left, labels)} ${operator} ${operandText(node.right, labels)}`;
}

export function describeScreenerFilters(where: unknown, fields: ScreenField[]): string {
  const labels = new Map<string, string>();
  for (const field of fields) {
    labels.set(field.name, field.label || field.name.replaceAll("_", " "));
    if (field.prefixed_name) labels.set(field.prefixed_name, field.label || field.name.replaceAll("_", " "));
  }
  return describeNode(where, labels) || "All stocks match";
}

function countNodes(value: unknown): number {
  const node = record(value);
  if (!node) return 0;
  if ((node.type === "all" || node.type === "any") && Array.isArray(node.items)) {
    return node.items.reduce((total, child) => total + countNodes(child), 0);
  }
  if (node.type === "not") return countNodes(node.item);
  return 1;
}

/** Shared compact filter summary used by the standalone screener and Strategy → Universe. */
export function ScreenerFilterSummary({
  where,
  fields,
  editorOpen,
  onToggleEditor,
  editor,
}: {
  where: unknown;
  fields: ScreenField[];
  editorOpen: boolean;
  onToggleEditor: () => void;
  editor?: ReactNode;
}) {
  const description = describeScreenerFilters(where, fields);
  const count = countNodes(where);
  return (
    <section className="min-w-0 border-b border-line bg-surface">
      <div className="flex min-w-0 items-start gap-2 px-3 py-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
            <span>Filters</span>
            <span className="font-mono tabular-nums">{count}</span>
          </div>
          <p className="mt-0.5 line-clamp-2 break-words text-xs text-ink" title={description}>
            {description}
          </p>
        </div>
        <Button
          type="button"
          onClick={onToggleEditor}
          variant="outline"
          size="sm"
          className="h-7 shrink-0 px-2 text-[10px]"
          aria-expanded={editorOpen}
        >
          {editorOpen ? "Done" : "Edit"}
        </Button>
      </div>
      {editorOpen && editor ? <div className="border-t border-line px-3 py-2">{editor}</div> : null}
    </section>
  );
}
