import type {
  AppliedFilterGroup,
  AppliedFilterRow,
  ComparisonOp,
  IrComparisonNode,
  IrGroupNode,
  IrOperand,
  IrWhereNode,
  UniverseQueryV1,
} from "../types";

const COMPARISON_OPS = new Set<ComparisonOp>([
  "gt",
  "gte",
  "lt",
  "lte",
  "eq",
  "neq",
]);

let idSeq = 0;
export function nextFilterId(): string {
  idSeq += 1;
  return `f_${idSeq}_${Math.random().toString(36).slice(2, 7)}`;
}

function nextId(): string {
  return nextFilterId();
}

export function isComparisonOp(op: string): op is ComparisonOp {
  return COMPARISON_OPS.has(op as ComparisonOp);
}

export function isComparisonNode(node: unknown): node is IrComparisonNode {
  if (!node || typeof node !== "object") return false;
  const n = node as Record<string, unknown>;
  return typeof n.type === "string" && isComparisonOp(n.type);
}

export function isAllGroup(node: unknown): node is IrGroupNode {
  if (!node || typeof node !== "object") return false;
  const n = node as Record<string, unknown>;
  return n.type === "all" && Array.isArray(n.items);
}

export function emptyColOperand(name = "close"): IrOperand {
  return { type: "col", name };
}

export function litOperand(value: number | string | boolean): IrOperand {
  return { type: "lit", value };
}

export function formulaMul(col: string, factor: number): IrOperand {
  return {
    type: "formula",
    op: "*",
    args: [{ type: "col", name: col }, { type: "lit", value: factor }],
  };
}

export function defaultFilterRow(): AppliedFilterRow {
  return {
    id: nextId(),
    op: "gte",
    left: emptyColOperand("rs_rating"),
    right: litOperand(70),
  };
}

export function extractAppliedFilters(where: IrWhereNode | undefined): {
  rows: AppliedFilterRow[];
  hasAllRoot: boolean;
} {
  if (!where) return { rows: [], hasAllRoot: false };
  if (isAllGroup(where)) {
    return {
      hasAllRoot: true,
      rows: where.items.map((item) => nodeToRow(item)),
    };
  }
  // Single comparison or non-ALL root — display as one read-only / editable row
  return {
    hasAllRoot: false,
    rows: [nodeToRow(where)],
  };
}

function nodeToRow(node: IrWhereNode): AppliedFilterRow {
  if (isComparisonNode(node)) {
    return {
      id: nextId(),
      op: node.type,
      left: cloneOperand(node.left),
      right: cloneOperand(node.right),
    };
  }
  return {
    id: nextId(),
    op: "eq",
    left: emptyColOperand("ticker"),
    right: litOperand(0),
    readOnly: true,
    raw: node,
  };
}

export function cloneOperand(op: IrOperand): IrOperand {
  if (op.type === "col") {
    return op.offset != null
      ? { type: "col", name: op.name, offset: op.offset }
      : { type: "col", name: op.name };
  }
  if (op.type === "lit") return { type: "lit", value: op.value };
  return {
    type: "formula",
    op: op.op,
    args: op.args.map(cloneOperand),
  };
}

function rowToNode(row: AppliedFilterRow): IrWhereNode {
  if (row.readOnly && row.raw) return row.raw;
  return {
    type: row.op,
    left: cloneOperand(row.left),
    right: cloneOperand(row.right),
  } satisfies IrComparisonNode;
}

export function rowsToWhere(rows: AppliedFilterRow[]): IrGroupNode {
  return { type: "all", items: rows.map(rowToNode) };
}

export function emptyFilterGroup(
  logic: AppliedFilterGroup["logic"] = "all",
  name?: string,
): AppliedFilterGroup {
  return { id: nextId(), logic, name, rows: [] };
}

/**
 * Parse a `universe_query_v1` where clause into Deepvue-style groups.
 *
 * Group ordering: index 0 is the `all` group (top-level comparisons + any
 * nested `all` groups folded in); each top-level `any` node becomes its own
 * subsequent `any` group. Non-comparison leaves (unrecognized nodes) are kept
 * as read-only rows on the first group so they survive round-trips.
 */
export function extractAppliedFilterGroups(
  where: IrWhereNode | undefined,
): AppliedFilterGroup[] {
  if (!where) return [emptyFilterGroup("all")];

  const root = where as Record<string, unknown>;
  const rootType = root.type;

  if (rootType === "any" && Array.isArray(root.items)) {
    const items = root.items as IrWhereNode[];
    const hasNamed = items.some((item) => {
      const rec = item as Record<string, unknown>;
      return typeof rec.name === "string" && rec.name.length > 0;
    });
    if (hasNamed) {
      const groups: AppliedFilterGroup[] = [];
      for (const item of items) {
        const rec = item as Record<string, unknown>;
        const name = typeof rec.name === "string" ? rec.name : undefined;
        const childItems = Array.isArray(rec.items)
          ? (rec.items as IrWhereNode[])
          : [item];
        const rows = childItems.map(nodeToRow);
        if (name === "membership" || (!name && groups.length === 0)) {
          groups.unshift({ id: nextId(), logic: "all", name: name || "membership", rows });
        } else {
          // Named alternatives (code_33): AND inside the group, OR with membership.
          const namedLogic = rec.type === "any" ? "any" : "all";
          groups.push({ id: nextId(), logic: namedLogic, name, rows });
        }
      }
      return groups.length ? groups : [emptyFilterGroup("all")];
    }
    return [
      {
        id: nextId(),
        logic: "any",
        rows: items.map(nodeToRow),
      },
    ];
  }

  if (rootType === "all" && Array.isArray(root.items)) {
    const allRows: AppliedFilterRow[] = [];
    const anyGroups: AppliedFilterGroup[] = [];
    for (const item of root.items as IrWhereNode[]) {
      const node = item as Record<string, unknown>;
      if (typeof node?.name === "string" && node.name && node.name !== "membership") {
        const childItems = Array.isArray(node.items)
          ? (node.items as IrWhereNode[])
          : [item];
        anyGroups.push({
          id: nextId(),
          name: node.name,
          logic: node.type === "any" ? "any" : "all",
          rows: childItems.map(nodeToRow),
        });
      } else if (node?.type === "any" && Array.isArray(node.items)) {
        anyGroups.push({
          id: nextId(),
          logic: "any",
          name: typeof node.name === "string" ? node.name : undefined,
          rows: (node.items as IrWhereNode[]).map(nodeToRow),
        });
      } else if (node?.type === "all" && Array.isArray(node.items)) {
        // Fold a nested AND group into the primary ALL group.
        allRows.push(...(node.items as IrWhereNode[]).map(nodeToRow));
      } else {
        allRows.push(nodeToRow(item));
      }
    }
    return [{ id: nextId(), logic: "all", name: "membership", rows: allRows }, ...anyGroups];
  }

  return [{ id: nextId(), logic: "all", rows: [nodeToRow(where)] }];
}

/** Compile groups to a nested `all`/`any` where clause (Deepvue semantics). */
export function groupsToWhere(groups: AppliedFilterGroup[]): IrWhereNode {
  const unnamed = groups.filter((g) => !g.name || g.name === "membership");
  const named = groups.filter((g) => g.name && g.name !== "membership");

  const unnamedItems: IrWhereNode[] = [];
  unnamed.forEach((group) => {
    const leaves = group.rows.map(rowToNode);
    if (group.logic === "all") {
      unnamedItems.push(...leaves);
    } else {
      unnamedItems.push({ type: "any", items: leaves });
    }
  });

  if (!named.length) {
    if (unnamedItems.length === 0) return { type: "all", items: [] };
    if (unnamedItems.length === 1) return unnamedItems[0]!;
    return { type: "all", items: unnamedItems };
  }

  const membershipNode: IrGroupNode = {
    type: "all",
    name: "membership",
    items: unnamedItems,
  };
  const namedNodes: IrGroupNode[] = named.map((group) => ({
    type: "all",
    name: group.name,
    items: group.rows.map(rowToNode),
  }));
  return { type: "any", items: [membershipNode, ...namedNodes] };
}

export function applyFiltersToSpec(
  spec: UniverseQueryV1,
  rows: AppliedFilterRow[],
): UniverseQueryV1 {
  return {
    ...spec,
    where: rowsToWhere(rows),
  };
}

export function applyGroupsToSpec(
  spec: UniverseQueryV1,
  groups: AppliedFilterGroup[],
): UniverseQueryV1 {
  return {
    ...spec,
    where: groupsToWhere(groups),
  };
}

export function formatOperand(op: IrOperand): string {
  if (op.type === "col") return op.name;
  if (op.type === "lit") return String(op.value);
  if (op.type === "formula") {
    const parts = op.args.map(formatOperand);
    if (op.op === "*" && parts.length === 2) {
      return `${parts[0]} × ${parts[1]}`;
    }
    return `${op.op}(${parts.join(", ")})`;
  }
  return "?";
}

export function operandKind(op: IrOperand): "field" | "lit" | "formula" {
  if (op.type === "col") return "field";
  if (op.type === "lit") return "lit";
  return "formula";
}

export function parseOperandInput(
  kind: "field" | "lit" | "formula",
  text: string,
  prev?: IrOperand,
): IrOperand {
  const t = text.trim();
  if (kind === "field") {
    return { type: "col", name: t || "close" };
  }
  if (kind === "lit") {
    if (t === "true") return { type: "lit", value: true };
    if (t === "false") return { type: "lit", value: false };
    const n = Number(t);
    if (t !== "" && Number.isFinite(n)) return { type: "lit", value: n };
    return { type: "lit", value: t };
  }
  // formula: "col * 1.3" or "col*0.75"
  const mul = t.match(/^([A-Za-z_][\w.]*)\s*\*\s*(-?\d+(?:\.\d+)?)$/);
  if (mul) {
    return formulaMul(mul[1]!, Number(mul[2]));
  }
  if (prev?.type === "formula") {
    return cloneOperand(prev);
  }
  return formulaMul("close", 1);
}

export function filterChipLabel(row: AppliedFilterRow): string {
  if (row.readOnly) return "group…";
  return `${formatOperand(row.left)} ${row.op} ${formatOperand(row.right)}`;
}

export const OP_LABELS: Record<ComparisonOp, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  neq: "!=",
};
