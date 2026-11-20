/**
 * Leaves: the AST's comparison nodes <-> the editor's row model (`AppliedFilterRow`).
 *
 * `FilterChipBar` already edits rows well (field picker, expression parsing, annotations),
 * so it stays the leaf editor and the tree layer above it is what went AST-native. Two
 * mappings, both exact:
 *
 *   comparison          <-> row { op, left, right }
 *   not(eq(a, b))       <-> row with op "neq"      (the AST has no `neq`; `≠` is how the
 *                                                    one canonical form is displayed)
 *   anything else       <-> row { readOnly, raw }  (shown verbatim, never rewritten —
 *                                                    `not(gt(a,b))` is NOT `lte(a, b)`
 *                                                    for strings, so it must survive as-is)
 */

import { nextFilterId } from "./irFilters";
import {
  isComparisonNode,
  isGroupNode,
  normalizeOperand,
  type AstComparison,
  type AstNode,
  type AstNot,
  type AstOperand,
  type UiGroup,
  type UiNode,
  type UiNot,
} from "./screenAst";
import type { AppliedFilterRow, ComparisonOp } from "../types";

/** `not(eq)` reads as `≠`; every other `not` is preserved verbatim. */
function neqComparison(node: AstNot): AstComparison | null {
  const inner = node.item;
  if (isComparisonNode(inner) && inner.type === "eq") {
    return { type: "eq", left: inner.left, right: inner.right };
  }
  return null;
}

export function leafRowFromNode(node: UiNode): AppliedFilterRow {
  if (node.type === "not") {
    const negated = neqComparison(node);
    if (negated) {
      return { id: node.id, op: "neq", left: negated.left, right: negated.right };
    }
    return { id: node.id, op: "eq", left: { type: "lit", value: "" }, right: { type: "lit", value: "" }, readOnly: true, raw: node };
  }
  if (isComparisonNode(node)) {
    return { id: node.id, op: node.type as ComparisonOp, left: node.left, right: node.right };
  }
  // a group cannot be a leaf row; keep it verbatim rather than dropping it
  return { id: node.id, op: "eq", left: { type: "lit", value: "" }, right: { type: "lit", value: "" }, readOnly: true, raw: node };
}

export function nodeFromLeafRow(row: AppliedFilterRow): AstNode {
  if (row.readOnly && row.raw) return row.raw as AstNode;
  // The editor's IrOperand is looser than the AST's (e.g. `formula.op: string`), so
  // operands are normalised back into AST terms rather than cast.
  const left = normalizeOperand(row.left) ?? (row.left as unknown as AstOperand);
  const right = normalizeOperand(row.right) ?? (row.right as unknown as AstOperand);
  if (row.op === "neq") return { type: "not", item: { type: "eq", left, right } };
  return { type: row.op, left, right } as AstComparison;
}

/** Nodes the leaf editor can show as rows: comparisons and `not(comparison)`. */
export function isLeafNode(node: UiNode): boolean {
  if (isComparisonNode(node)) return true;
  if (node.type === "not") return !isGroupNode(node.item);
  return false;
}

export function leafRowsFrom(nodes: UiNode[]): AppliedFilterRow[] {
  return nodes.filter(isLeafNode).map(leafRowFromNode);
}

/** Rebuild a group's items: leaf rows first (as today's editor shows them), then groups. */
export function groupItemsFromRows(
  rows: AppliedFilterRow[],
  nonLeaf: UiNode[],
  madeId: () => string = nextFilterId,
): UiNode[] {
  const fromRows = rows.map((row) => {
    const node = nodeFromLeafRow(row);
    return { ...node, id: row.readOnly && row.raw ? row.id : row.id || madeId() } as UiNode;
  });
  return [...fromRows, ...nonLeaf];
}

export function isLeafGroup(node: UiNode): node is UiNot {
  return node.type === "not";
}

export function childGroups(node: UiGroup): UiGroup[] {
  return node.items.filter((c): c is UiGroup => isGroupNode(c));
}

export function childNotGroups(node: UiGroup): UiNot[] {
  return node.items.filter((c): c is UiNot => c.type === "not" && isGroupNode(c.item));
}
