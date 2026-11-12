/** Convert pipeline FilterTree ↔ screener ALL/ANY chip groups. */

import type { AppliedFilterGroup, AppliedFilterRow, IrOperand, IrWhereNode } from "../types";
import { astToWhere, isGroupNode, whereToAst } from "./screenAst";
import type {
  FilterCondition,
  FilterGroup,
  FilterNode,
  FilterTree,
} from "../components/strategy/StrategyDocument";
import { isFilterGroup, isFilterNot } from "../components/strategy/StrategyDocument";
import {
  cloneOperand,
  isComparisonNode,
  nextFilterId,
} from "./irFilters";

function leftToOperand(left: FilterCondition["left"]): IrOperand {
  if (typeof left === "string") return { type: "col", name: left };
  if (left && typeof left === "object" && "type" in left) return cloneOperand(left);
  return { type: "col", name: "close" };
}

function rightToOperand(
  right: FilterCondition["right"],
  rightKind: FilterCondition["right_kind"],
): IrOperand {
  if (right && typeof right === "object" && "type" in right) {
    return cloneOperand(right as IrOperand);
  }
  if (rightKind === "col" && typeof right === "string") {
    return { type: "col", name: right };
  }
  if (typeof right === "boolean" || typeof right === "number") {
    return { type: "lit", value: right };
  }
  if (typeof right === "string") {
    const n = Number(right);
    if (right !== "" && Number.isFinite(n) && rightKind !== "col") {
      return { type: "lit", value: n };
    }
    return rightKind === "lit" ? { type: "lit", value: right } : { type: "col", name: right };
  }
  return { type: "lit", value: 0 };
}

function filterNodeToIr(node: FilterNode): IrWhereNode {
  if (isFilterNot(node)) {
    return { type: "not", item: filterNodeToIr(node.item) } as IrWhereNode;
  }
  if (isFilterGroup(node)) {
    return {
      type: node.logic === "or" ? "any" : "all",
      name: node.name,
      items: node.conditions.map(filterNodeToIr),
    };
  }
  const cmp = {
    type: node.op === "neq" ? "eq" : node.op,
    left: leftToOperand(node.left),
    right: rightToOperand(node.right, node.right_kind),
  };
  if (node.op === "neq") {
    return { type: "not", item: cmp };
  }
  return cmp;
}

function irToFilterNode(node: IrWhereNode): FilterNode {
  const rec = node as {
    type?: string;
    item?: IrWhereNode;
    items?: IrWhereNode[];
    name?: string;
    left?: IrOperand;
    right?: IrOperand;
  };
  if (rec.type === "not" && rec.item && isComparisonNode(rec.item) && rec.item.type === "eq") {
    const inner = rec.item;
    const rightKind =
      inner.right.type === "col" ? "col" : inner.right.type === "formula" ? "formula" : "lit";
    return {
      op: "neq",
      left: cloneOperand(inner.left),
      right: cloneOperand(inner.right),
      right_kind: rightKind,
    };
  }
  if (rec.type === "not" && !rec.item) {
    return { logic: "and", conditions: [] }; // malformed: no child to negate
  }
  if (rec.type === "not") {
    // A negation with no `neq` spelling stays explicit. Falling through to the group branch
    // below returned an empty AND, dropping the whole negated subtree.
    return { item: irToFilterNode(rec.item as IrWhereNode) } as unknown as FilterNode;
  }
  if (isComparisonNode(node)) {
    const rightKind =
      node.right.type === "col" ? "col" : node.right.type === "formula" ? "formula" : "lit";
    return {
      op: node.type,
      left: cloneOperand(node.left),
      right: cloneOperand(node.right),
      right_kind: rightKind,
    };
  }
  const items = Array.isArray(rec.items) ? rec.items : [];
  return {
    logic: rec.type === "any" ? "or" : "and",
    name: typeof rec.name === "string" ? rec.name : undefined,
    conditions: items.map(irToFilterNode),
  };
}

export function filterTreesToIr(filters: FilterTree[] | undefined): IrWhereNode {
  const items = (filters ?? []).map(filterNodeToIr);
  if (items.length === 0) return { type: "all", items: [] };
  if (items.length === 1) return items[0]!;
  return { type: "all", items };
}

/**
 * The strategy document stores `FilterTree[]`, a model that can express `not(eq(...))`
 * (as `neq`) and nothing else negated. This converts an AST back to it **only when the
 * conversion is exact**, so an edit the document cannot hold is refused rather than
 * silently reduced — the previous behaviour turned `not(any(...))` into an empty AND group
 * and dropped the whole negated subtree.
 *
 * Returns `null` when the tree cannot be expressed losslessly.
 */
/**
 * The top level is a *list* of clauses that means AND. A nameless `and` group is exactly that
 * list, so it is unwrapped whenever a where-AST becomes document clauses — on load and on
 * write — instead of being stored as an extra level (both lower to the same SQL). A *named*
 * group, or a top-level `or`, stays a node: those carry meaning.
 */
function unwrapBareRoot(trees: FilterTree[]): FilterTree[] {
  if (trees.length !== 1) return trees;
  const only = trees[0]!;
  // Any root-level AND is the top level itself, name or not: there is no enclosing group for
  // that name to distinguish, so it is not addressable (a leftover "hygiene" label from the
  // retired hygiene split). `membership` is the one name the compiler reserves.
  if (isFilterGroup(only) && only.logic === "and" && only.name !== "membership") {
    return only.conditions;
  }
  return trees;
}

/**
 * Normalise a stored pipeline document's screen: the top level is a clause list, so a wrapper
 * group saved by an older build is unwrapped when the document is adopted. Nothing is
 * migrated in place — the next save writes the flat form.
 */
export function normalizeDocumentScreen<
  T extends { universe?: { screen?: FilterTree[] } | null },
>(doc: T | null | undefined): T | null | undefined {
  const screen = doc?.universe?.screen;
  if (!doc || !Array.isArray(screen)) return doc;
  const flat = unwrapBareRoot(screen);
  if (flat === screen) return doc;
  return { ...doc, universe: { ...doc.universe, screen: flat } };
}

export function screenTreesForWhere(where: IrWhereNode): FilterTree[] | null {
  const canonical = (w: unknown): string | null => {
    const ast = whereToAst(w);
    if (!ast) return null;
    // A root-level AND and its clause list are the same screen, so the wrapper's inert `name`
    // must not make an exact conversion look lossy (which would refuse the write).
    const root =
      isGroupNode(ast) && ast.type === "all" && ast.name !== "membership"
        ? { ...ast, name: undefined }
        : ast;
    return JSON.stringify(astToWhere(root));
  };
  const wanted = canonical(where);
  const trees = irToFilterTrees(where);
  if (canonical(filterTreesToIr(trees)) !== wanted) return null;
  const flat = unwrapBareRoot(trees);
  // the unwrapped list must compile to the very same node, or the wrapper stays
  return canonical(filterTreesToIr(flat)) === wanted ? flat : trees;
}

export function irToFilterTrees(where: IrWhereNode | undefined | null): FilterTree[] {
  if (!where) return [];
  const rec = where as { type?: string; items?: IrWhereNode[] };
  if (
    (rec.type === "all" || rec.type === "any") &&
    Array.isArray(rec.items) &&
    rec.items.length === 0
  ) {
    return [];
  }
  return unwrapBareRoot([irToFilterNode(where)]);
}

function conditionToRow(node: FilterCondition): AppliedFilterRow {
  return {
    id: node.id?.trim() || nextFilterId(),
    op: node.op,
    left: leftToOperand(node.left),
    right: rightToOperand(node.right, node.right_kind),
    annotation: node.annotation ?? undefined,
  };
}

function filterNodeToRows(node: FilterNode): AppliedFilterRow[] {
  if (isFilterGroup(node)) {
    return node.conditions.flatMap(filterNodeToRows);
  }
  if (isFilterNot(node)) {
    // The row editor cannot edit a negation, but it must not vanish: carry it verbatim.
    return [
      {
        id: nextFilterId(),
        op: "eq",
        left: { type: "lit", value: "" },
        right: { type: "lit", value: "" },
        readOnly: true,
        raw: filterNodeToIr(node),
      },
    ];
  }
  return [conditionToRow(node)];
}

function rowToFilterCondition(row: AppliedFilterRow): FilterCondition {
  const rightKind =
    row.right.type === "col" ? "col" : row.right.type === "formula" ? "formula" : "lit";
  return {
    op: row.op,
    left: cloneOperand(row.left),
    right: cloneOperand(row.right),
    right_kind: rightKind,
    id: row.id,
    annotation: row.annotation ?? null,
  };
}

export function filterTreesToGroups(filters: FilterTree[] | undefined): AppliedFilterGroup[] {
  if (!filters?.length) {
    return [{ id: nextFilterId(), logic: "all", name: "membership", rows: [] }];
  }
  const groups: AppliedFilterGroup[] = [];
  const loose: AppliedFilterRow[] = [];
  for (const node of filters) {
    if (isFilterGroup(node)) {
      groups.push({
        id: nextFilterId(),
        logic: node.logic === "or" ? "any" : "all",
        name: node.name,
        rows: node.conditions.flatMap(filterNodeToRows),
      });
    } else if (isFilterNot(node)) {
      loose.push(...filterNodeToRows(node));
    } else {
      loose.push(conditionToRow(node));
    }
  }
  if (loose.length) {
    const membership = groups.find((g) => g.name === "membership");
    if (membership) {
      membership.rows = [...membership.rows, ...loose];
    } else if (groups[0]?.logic === "all" && !groups[0].name) {
      groups[0].rows = [...groups[0].rows, ...loose];
      groups[0].name = "membership";
    } else {
      groups.unshift({
        id: nextFilterId(),
        logic: "all",
        name: "membership",
        rows: loose,
      });
    }
  }
  if (!groups.some((g) => g.name === "membership") && groups[0]?.logic === "all") {
    groups[0] = { ...groups[0], name: groups[0].name ?? "membership" };
  }
  return groups.length
    ? groups
    : [{ id: nextFilterId(), logic: "all", name: "membership", rows: [] }];
}

function appliedToFilterGroup(group: AppliedFilterGroup): FilterGroup {
  return {
    logic: group.logic === "any" ? "or" : "and",
    name: group.name,
    conditions: [
      ...group.rows.map(rowToFilterCondition),
      ...(group.children ?? []).map(appliedToFilterGroup),
    ],
  };
}

export function groupsToFilterTrees(groups: AppliedFilterGroup[]): FilterTree[] {
  return groups.map((group) => ({
    logic: group.logic === "any" ? "or" : "and",
    name: group.name,
    conditions: [
      ...group.rows.map(rowToFilterCondition),
      ...(group.children ?? []).map(appliedToFilterGroup),
    ],
  }));
}
