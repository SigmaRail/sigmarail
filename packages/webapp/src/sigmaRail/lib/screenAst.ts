/**
 * The Universe screen tree, expressed in the AST's own terms — the single model the
 * shared editor speaks (screener and strategy alike).
 *
 * Why this exists: the API's `universe_query_v1` `where` node is the only fully
 * expressive representation (any nesting depth, `not`, all four arithmetic operators,
 * operand offsets). The editor used to speak a reduced "chips" model instead, so every
 * boundary crossing lost whatever chips cannot hold — `not`, `+ - /`, depth > 1.
 *
 * Here the node shapes *are* the AST's. The only addition is an `id` for React keys and
 * edit addressing, and ids are stripped on the way out (`astToWhere`), so they can never
 * leak into a spec, a saved screen, or a URL.
 *
 * A node that cannot be represented returns `null` rather than being dropped — callers
 * fall back to carrying the raw AST instead of silently losing a condition.
 */

export type AstFormulaOp = "+" | "-" | "*" | "/";

export type AstOperand =
  | { type: "col"; name: string; offset?: number }
  | { type: "lit"; value: number | string | boolean }
  | { type: "formula"; op: AstFormulaOp; args: AstOperand[] };

export type AstComparison = {
  type: "gt" | "gte" | "lt" | "lte" | "eq";
  left: AstOperand;
  right: AstOperand;
};

export type AstNot = { type: "not"; item: AstNode };

export type AstGroup = { type: "all" | "any"; name?: string; items: AstNode[] };

export type AstNode = AstComparison | AstNot | AstGroup;

/**
 * UI node: the AST shape plus a render/edit id. An explicit union (not an intersection)
 * so the children stay typed as UI nodes and the tree can be walked recursively.
 */
export type UiComparison = AstComparison & { id: string };
export type UiNot = { id: string; type: "not"; item: UiNode };
export type UiGroup = { id: string; type: "all" | "any"; name?: string; items: UiNode[] };
export type UiNode = UiComparison | UiNot | UiGroup;

export function isUiGroup(node: UiNode): node is UiGroup {
  return node.type === "all" || node.type === "any";
}

export function isUiNot(node: UiNode): node is UiNot {
  return node.type === "not";
}

export const COMPARISONS = ["gt", "gte", "lt", "lte", "eq"] as const;
export const FORMULA_OPS: readonly AstFormulaOp[] = ["+", "-", "*", "/"];

const CMP_SET = new Set<string>(COMPARISONS);
const FORMULA_SET = new Set<string>(FORMULA_OPS);
const GROUP_SET = new Set(["all", "any"]);

export function isGroupNode(node: AstNode): node is AstGroup {
  return GROUP_SET.has(node.type);
}

export function isComparisonNode(node: AstNode): node is AstComparison {
  return CMP_SET.has(node.type);
}

/**
 * Normalisation is *structural*: node shapes are canonicalised and nothing is folded away.
 * A single-child group is preserved as written, and so is an empty one — an empty ALL is
 * vacuously true, but the user just created it and it has to survive the round trip through
 * the address, or adding a group would appear to do nothing.
 */
function tidyGroup(node: AstGroup): AstNode | null {
  const items = node.items.map(normalizeAst).filter((n): n is AstNode => n !== null);
  return { type: node.type, ...(node.name ? { name: node.name } : {}), items };
}

/** Parse/validate an unknown value into an AST node; `null` when unrepresentable. */
export function normalizeAst(value: unknown): AstNode | null {
  if (!value || typeof value !== "object") return null;
  const node = value as Record<string, unknown>;
  const type = String(node.type ?? "");

  if (GROUP_SET.has(type)) {
    if (!Array.isArray(node.items)) return null;
    return tidyGroup({
      type: type as "all" | "any",
      ...(typeof node.name === "string" && node.name ? { name: node.name } : {}),
      items: node.items as AstNode[],
    });
  }
  if (type === "not") {
    const item = normalizeAst(node.item);
    return item ? { type: "not", item } : null;
  }
  if (CMP_SET.has(type) || type === "neq") {
    const left = normalizeOperand(node.left);
    const right = normalizeOperand(node.right);
    if (!left || !right) return null;
    // `neq` is the editor's spelling of the one canonical form the AST has: not(eq)
    if (type === "neq") return { type: "not", item: { type: "eq", left, right } };
    return { type: type as AstComparison["type"], left, right };
  }
  return null; // anything else (e.g. a bespoke operator) must not be silently dropped
}

export function normalizeOperand(value: unknown): AstOperand | null {
  if (!value || typeof value !== "object") return null;
  const op = value as Record<string, unknown>;
  if (op.type === "col") {
    const name = String(op.name ?? "").trim();
    if (!name) return null;
    const offset = Number(op.offset ?? 0);
    return { type: "col", name, ...(Number.isFinite(offset) && offset !== 0 ? { offset } : {}) };
  }
  if (op.type === "lit") {
    const v = op.value;
    if (typeof v === "number" || typeof v === "string" || typeof v === "boolean") {
      return { type: "lit", value: v };
    }
    return null;
  }
  if (op.type === "formula") {
    const fop = String(op.op ?? "");
    if (!FORMULA_SET.has(fop) || !Array.isArray(op.args) || op.args.length < 2) return null;
    const args = (op.args as unknown[]).map(normalizeOperand);
    if (args.some((a) => a === null)) return null;
    return { type: "formula", op: fop as AstFormulaOp, args: args as AstOperand[] };
  }
  return null;
}

/** `/v1/universe/run`-shaped where node — id-free by construction. */
export function astToWhere(node: AstNode): Record<string, unknown> {
  const out: Record<string, unknown> = { type: node.type };
  if (isGroupNode(node)) {
    if (node.name) out.name = node.name;
    out.items = node.items.map(astToWhere);
  } else if (node.type === "not") {
    out.item = astToWhere(node.item);
  } else {
    out.left = node.left;
    out.right = node.right;
  }
  return out;
}

export function whereToAst(where: unknown): AstNode | null {
  return normalizeAst(where);
}

// --- editing -----------------------------------------------------------------

export type IdFactory = () => string;

export function withIds(node: AstNode, makeId: IdFactory): UiNode {
  const id = makeId();
  if (isGroupNode(node)) {
    return {
      id,
      type: node.type,
      ...(node.name ? { name: node.name } : {}),
      items: node.items.map((n) => withIds(n, makeId)),
    };
  }
  if (node.type === "not") {
    return { id, type: "not", item: withIds(node.item, makeId) };
  }
  return { ...node, id };
}

export function stripIds(node: UiNode): AstNode {
  if (isUiGroup(node)) {
    return {
      type: node.type,
      ...(node.name ? { name: node.name } : {}),
      items: node.items.map(stripIds),
    };
  }
  if (isUiNot(node)) return { type: "not", item: stripIds(node.item) };
  return { type: node.type, left: node.left, right: node.right };
}

export function findNode(root: UiNode, id: string): UiNode | null {
  if (root.id === id) return root;
  if (isUiGroup(root)) {
    for (const child of root.items) {
      const hit = findNode(child, id);
      if (hit) return hit;
    }
  } else if (isUiNot(root)) {
    return findNode(root.item, id);
  }
  return null;
}

/** Replace the node with `id` (or the root); `null` from `f` removes it. */
export function mapNode(
  root: UiNode,
  id: string,
  f: (node: UiNode) => UiNode | null,
): UiNode | null {
  if (root.id === id) return f(root);
  if (isUiGroup(root)) {
    const items: UiNode[] = [];
    for (const child of root.items) {
      const next = mapNode(child, id, f);
      if (next) items.push(next);
    }
    return { ...root, items };
  }
  if (isUiNot(root)) {
    const next = mapNode(root.item, id, f);
    return next ? { ...root, item: next } : null;
  }
  return root;
}

export function countPredicates(node: AstNode): number {
  if (isGroupNode(node)) return node.items.reduce((n, c) => n + countPredicates(c), 0);
  if (node.type === "not") return countPredicates(node.item);
  return 1;
}

export function maxDepth(node: AstNode, depth = 0): number {
  if (isGroupNode(node)) {
    return node.items.reduce((d, c) => Math.max(d, maxDepth(c, depth + 1)), depth);
  }
  if (node.type === "not") return maxDepth(node.item, depth + 1);
  return depth;
}

// --- display -----------------------------------------------------------------

export const OP_LABEL: Record<string, string> = {
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  eq: "=",
};

export function operandLabel(op: AstOperand): string {
  if (op.type === "col") return op.offset ? `${op.name}[${op.offset}]` : op.name;
  if (op.type === "lit") return typeof op.value === "string" ? op.value : String(op.value);
  return `(${op.args.map(operandLabel).join(` ${op.op} `)})`;
}

/**
 * How a condition reads in the UI. `not(eq(...))` — the AST's way of saying "not equal",
 * since the AST has no `neq` — reads as `≠`, so there is one canonical representation and
 * one rendering.
 */
export function conditionLabel(node: AstNode): string {
  if (isGroupNode(node)) return node.name ? `${node.type.toUpperCase()}: ${node.name}` : node.type.toUpperCase();
  if (node.type === "not") {
    const inner = node.item;
    if (isComparisonNode(inner) && inner.type === "eq") {
      return `${operandLabel(inner.left)} ≠ ${operandLabel(inner.right)}`;
    }
    return `NOT ${conditionLabel(inner)}`;
  }
  return `${operandLabel(node.left)} ${OP_LABEL[node.type] ?? node.type} ${operandLabel(node.right)}`;
}

/** `empty(group)` helpers used by the editor when adding rows/groups. */
export function emptyGroup(logic: "all" | "any", name?: string): AstGroup {
  return { type: logic, ...(name ? { name } : {}), items: [] };
}

export function defaultComparison(field = "close"): AstComparison {
  return {
    type: "gt",
    left: { type: "col", name: field },
    right: { type: "col", name: "sma50d" },
  };
}
