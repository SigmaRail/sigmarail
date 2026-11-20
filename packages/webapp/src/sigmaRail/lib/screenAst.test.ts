import { describe, expect, it } from "vitest";
import {
  astToWhere,
  conditionLabel,
  countPredicates,
  findNode,
  mapNode,
  maxDepth,
  stripIds,
  whereToAst,
  withIds,
} from "./screenAst";

let n = 0;
const id = () => `id${++n}`;

/** Test-only narrowing helper (the unions are discriminated at runtime). */
type AnyGroup = { items: Array<{ id: string }>; type: string };
const asGroup = (node: unknown) => node as AnyGroup;

// A screen that the chips model could not hold: a `not`, a division, three levels deep.
const AST = {
  type: "all",
  name: "hygiene",
  items: [
    { type: "gte", left: { type: "col", name: "close" }, right: { type: "lit", value: 5 } },
    { type: "not", item: { type: "eq", left: { type: "col", name: "industry" }, right: { type: "lit", value: "Biotechnology" } } },
    {
      type: "any",
      items: [
        { type: "eq", left: { type: "col", name: "exchange" }, right: { type: "lit", value: "NYSE" } },
        { type: "eq", left: { type: "col", name: "exchange" }, right: { type: "lit", value: "NASDAQ" } },
      ],
    },
    {
      type: "all",
      name: "membership",
      items: [
        { type: "gt", left: { type: "col", name: "close" }, right: { type: "col", name: "sma50d" } },
        {
          type: "gte",
          left: { type: "col", name: "atr_pct" },
          right: { type: "formula", op: "/", args: [{ type: "col", name: "atr_14" }, { type: "col", name: "close" }] },
        },
        {
          type: "any",
          items: [
            { type: "gte", left: { type: "col", name: "rs_rating" }, right: { type: "lit", value: 85 } },
            { type: "eq", left: { type: "col", name: "minervini_score", offset: 1 }, right: { type: "lit", value: true } },
          ],
        },
      ],
    },
  ],
};

describe("screenAst — the AST's own terms", () => {
  it("round-trips a tree the chips model cannot hold (not, division, 3 levels)", () => {
    const ast = whereToAst(AST);
    expect(ast).not.toBeNull();
    expect(astToWhere(ast!)).toEqual(AST);
    expect(maxDepth(ast!)).toBeGreaterThanOrEqual(3);
  });

  it("keeps ids out of the emitted where", () => {
    const ui = withIds(whereToAst(AST)!, id);
    const where = astToWhere(stripIds(ui));
    expect(JSON.stringify(where)).not.toContain("id");
    expect(where).toEqual(AST);
  });

  it("counts predicates and finds/replaces nodes by id", () => {
    const ui = withIds(whereToAst(AST)!, id);
    expect(countPredicates(ui)).toBe(8);
    const venue = findNode(ui, asGroup(ui).items[2]!.id);
    expect(venue).not.toBeNull();
    const changed = mapNode(ui, asGroup(ui).items[2]!.id, (node) => ({ ...node, type: "all" } as typeof node));
    expect(asGroup(stripIds(changed!)).items[2]).toMatchObject({ type: "all" });
  });

  it("removes a node when the mapping returns null", () => {
    const ui = withIds(whereToAst(AST)!, id);
    const pruned = mapNode(ui, asGroup(ui).items[1]!.id, () => null);
    expect(asGroup(stripIds(pruned!)).items).toHaveLength(3);
    expect(JSON.stringify(stripIds(pruned!))).not.toContain("Biotechnology");
  });

  it("reads not(eq) as ≠ — one canonical representation, one rendering", () => {
    const not = whereToAst(AST)!;
    const label = conditionLabel((not as { items: unknown[] }).items[1] as never);
    expect(label).toBe("industry ≠ Biotechnology");
  });

  it("reports unrepresentable nodes instead of dropping them", () => {
    expect(whereToAst({ type: "matches_regex", left: {}, right: {} })).toBeNull();
    expect(whereToAst({ type: "formula", op: "%", args: [] })).toBeNull();
    expect(whereToAst({ type: "all", items: [{ type: "nope" }] })).toEqual({ type: "all", items: [] });
    expect(whereToAst("nonsense")).toBeNull();
    expect(whereToAst(undefined)).toBeNull();
  });

  it("is structural: keeps single-child and empty groups — nothing is folded away", () => {
    // a round trip must reproduce the tree exactly (a just-added group has no children yet)
    expect(whereToAst({ type: "all", items: [AST.items[0]] })).toEqual({ type: "all", items: [AST.items[0]] });
    expect(whereToAst({ type: "all", name: "hygiene", items: [AST.items[0]] })).toMatchObject({ name: "hygiene" });
    expect(whereToAst({ type: "all", items: [] })).toEqual({ type: "all", items: [] });
  });
});
