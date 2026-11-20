import { describe, expect, it } from "vitest";
import { groupItemsFromRows, leafRowFromNode, leafRowsFrom, nodeFromLeafRow } from "./astRows";
import { astToWhere, withIds, type AstNode, type UiNode } from "./screenAst";

let n = 0;
const id = () => `r${++n}`;

const cmp: AstNode = { type: "gt", left: { type: "col", name: "close" }, right: { type: "col", name: "sma50d" } };
const neq: AstNode = { type: "not", item: { type: "eq", left: { type: "col", name: "industry" }, right: { type: "lit", value: "Biotechnology" } } };
const notGt: AstNode = { type: "not", item: { type: "gt", left: { type: "col", name: "close" }, right: { type: "col", name: "sma50d" } } };

describe("leaf rows <-> AST", () => {
  it("round-trips a plain comparison", () => {
    const node = withIds(cmp, id);
    const row = leafRowFromNode(node);
    expect(row.op).toBe("gt");
    expect(astToWhere(nodeFromLeafRow(row))).toEqual(astToWhere(cmp));
  });

  it("shows not(eq) as ≠ and writes it back as not(eq)", () => {
    const node = withIds(neq, id);
    const row = leafRowFromNode(node);
    expect(row.op).toBe("neq");
    expect(row.readOnly).toBeUndefined();
    expect(astToWhere(nodeFromLeafRow(row))).toEqual(astToWhere(neq));
  });

  it("preserves an unusual not verbatim — never rewrites semantics", () => {
    const node = withIds(notGt, id);
    const row = leafRowFromNode(node);
    expect(row.readOnly).toBe(true);
    // not(gt) must NOT be silently turned into lte (wrong for strings) — it comes back identical
    expect(astToWhere(nodeFromLeafRow(row))).toEqual(astToWhere(notGt));
  });

  it("keeps rows then groups, and preserves every node", () => {
    const group: AstNode = {
      type: "all",
      name: "membership",
      items: [cmp, { type: "any", items: [neq, notGt] }],
    };
    const ui = withIds(group, id);
    const leaves = leafRowsFrom((ui as UiNode & { items: UiNode[] }).items);
    expect(leaves).toHaveLength(1); // only the comparison is a leaf
    const nonLeaf = (ui as UiNode & { items: UiNode[] }).items.filter(
      (c) => !["gt", "gte", "lt", "lte", "eq"].includes(c.type) && !(c.type === "not" && !["all", "any"].includes((c as { item: AstNode }).item.type)),
    );
    const rebuilt = groupItemsFromRows(leaves, nonLeaf as UiNode[], id);
    expect(rebuilt.map((c) => c.type)).toEqual(["gt", "any"]);
    expect(astToWhere({ type: "all", name: "membership", items: rebuilt })).toEqual(astToWhere(group));
  });

  it("hides nothing when a group is handed to the leaf editor", () => {
    const group = withIds({ type: "any", items: [cmp] } as AstNode, id);
    const row = leafRowFromNode(group);
    expect(row.readOnly).toBe(true);
    expect(row.raw).toBeDefined();
    expect(astToWhere(nodeFromLeafRow(row))).toEqual(astToWhere({ type: "any", items: [cmp] }));
  });
});
