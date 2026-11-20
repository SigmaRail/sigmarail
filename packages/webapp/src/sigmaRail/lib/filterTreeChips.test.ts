import { describe, expect, it } from "vitest";
import type { FilterTree } from "../components/strategy/StrategyDocument";
import { filterTreesToGroups, filterTreesToIr, groupsToFilterTrees, irToFilterTrees, screenTreesForWhere } from "./filterTreeChips";
import type { IrWhereNode } from "../types";

describe("filterTreeChips", () => {
  it("round-trips SEPA-style liquidity pills", () => {
    const trees: FilterTree[] = [
      { op: "gte", left: "close", right: 5 },
      { op: "gte", left: "avg_vol_50d", right: 100000 },
    ];
    const groups = filterTreesToGroups(trees);
    expect(groups[0]?.logic).toBe("all");
    expect(groups[0]?.rows).toHaveLength(2);
    const back = groupsToFilterTrees(groups);
    expect(JSON.stringify(back)).toContain("avg_vol_50d");
    expect(JSON.stringify(back)).toContain("close");
  });

  it("maps screener ALL/ANY where into filter trees", () => {
    const where: IrWhereNode = {
      type: "all",
      items: [
        {
          type: "gt",
          left: { type: "col", name: "close" },
          right: { type: "col", name: "sma50d" },
        },
        {
          type: "any",
          items: [
            {
              type: "gte",
              left: { type: "col", name: "rs_rating" },
              right: { type: "lit", value: 70 },
            },
          ],
        },
      ],
    };
    // The top level is the clause list itself: a nameless `and` root carries no meaning and is
    // unwrapped, so nothing has to nest under a wrapper group.
    const trees = irToFilterTrees(where);
    expect(trees).toHaveLength(2);
    expect(trees[0]).toMatchObject({ op: "gt" });
    expect("logic" in trees[1]! && trees[1].logic === "or").toBe(true);
    // and those clauses compile back to the very same where-AST
    expect(filterTreesToIr(trees)).toEqual(where);
  });

  it("round-trips a named code_33 group", () => {
    const trees: FilterTree[] = [
      { op: "gte", left: "close", right: 5 },
      {
        logic: "and",
        name: "code_33",
        conditions: [{ op: "eq", left: "arq_eps_acceleration_qoq", right: 1 }],
      },
    ];
    const groups = filterTreesToGroups(trees);
    expect(groups.some((g) => g.name === "code_33")).toBe(true);
    const back = groupsToFilterTrees(groups);
    expect(JSON.stringify(back)).toContain("code_33");
  });

  it("ANDs Code 33 pills and ORs that set with membership", () => {
    const trees: FilterTree[] = [
      {
        logic: "and",
        name: "membership",
        conditions: [
          { op: "gte", left: "close", right: 5 },
          { op: "gte", left: "avg_vol_50d", right: 100000 },
        ],
      },
      {
        logic: "and",
        name: "code_33",
        conditions: [
          { op: "gte", left: "arq_eps_growth_yoy", right: 0.25 },
          { op: "gte", left: "arq_revenue_growth_yoy", right: 0.25 },
          { op: "eq", left: "arq_eps_acceleration_qoq", right: 1 },
          { op: "eq", left: "arq_revenue_acceleration_qoq", right: 1 },
        ],
      },
    ];
    const groups = filterTreesToGroups(trees);
    expect(groups[0]?.logic).toBe("all");
    expect(groups[0]?.name).toBe("membership");
    const code33 = groups.find((g) => g.name === "code_33");
    expect(code33?.logic).toBe("all");
    expect(code33?.rows).toHaveLength(4);
    const back = groupsToFilterTrees(groups);
    expect(back).toHaveLength(2);
    expect(back.map((n) => ("name" in n ? n.name : undefined))).toEqual([
      "membership",
      "code_33",
    ]);
  });

  it("keeps an empty extra group instead of folding it into membership", () => {
    const groups = filterTreesToGroups([
      {
        logic: "and",
        name: "membership",
        conditions: [{ op: "gte", left: "close", right: 5 }],
      },
      { logic: "and", name: "code_33", conditions: [] },
      { logic: "and", conditions: [] },
    ]);
    expect(groups).toHaveLength(3);
    expect(groups[2]?.rows).toEqual([]);
    const back = groupsToFilterTrees(groups);
    expect(back).toHaveLength(3);
    expect(back[2]).toMatchObject({ logic: "and", conditions: [] });
  });
});

describe("what the strategy document's model can hold — and the refusal when it cannot", () => {
  const cmpIr = (left: string, right: string) =>
    ({ type: "gt", left: { type: "col", name: left }, right: { type: "col", name: right } }) as unknown as IrWhereNode;

  it("holds not(eq) as ≠ — the strategy's own hygiene rule round-trips", () => {
    const where = {
      type: "not",
      item: { type: "eq", left: { type: "col", name: "industry" }, right: { type: "lit", value: "Biotechnology" } },
    } as unknown as IrWhereNode;
    const trees = screenTreesForWhere(where);
    expect(trees).not.toBeNull();
    expect(trees![0]).toMatchObject({ op: "neq" });
    expect(filterTreesToIr(trees!)).toMatchObject({ type: "not", item: { type: "eq" } });
  });

  it("stores a general negation instead of dropping it (was: an EMPTY AND group)", () => {
    const notGt = { type: "not", item: cmpIr("close", "sma50d") } as unknown as IrWhereNode;
    const trees = irToFilterTrees(notGt);
    // `not(...)` is a document node now; the old behaviour rebuilt it as an empty AND, so
    // the negated subtree vanished and a "not" screen loaded back as its opposite
    expect(trees).toHaveLength(1);
    expect(trees[0]).toMatchObject({ item: { op: "gt" } });
    expect(filterTreesToIr(trees)).toEqual(notGt);
    expect(screenTreesForWhere(notGt)).not.toBeNull();
  });

  it("still refuses a node the document genuinely cannot express", () => {
    const weird = { type: "matches_regex", left: { type: "col", name: "ticker" }, right: { type: "lit", value: "AA" } } as unknown as IrWhereNode;
    expect(screenTreesForWhere(weird)).toBeNull();
  });

  it("holds nesting, including a group inside a group", () => {
    const deep = {
      type: "all",
      name: "membership",
      items: [cmpIr("close", "sma50d"), { type: "any", items: [cmpIr("close", "sma150d"), cmpIr("close", "sma200d")] }],
    } as unknown as IrWhereNode;
    const trees = screenTreesForWhere(deep);
    expect(trees).not.toBeNull();
    expect(filterTreesToIr(trees!)).toMatchObject({ type: "all", name: "membership" });
  });

  it("ANDs a legacy sibling list: a bare list becomes a root ALL of those siblings", () => {
    // Universe hygiene used to be a flat list of sibling groups; it still means ALL of them.
    const screen: FilterTree[] = [
      { logic: "and", name: "membership", conditions: [{ op: "gte", left: "close", right: 5 }] },
      { logic: "and", name: "code_33", conditions: [{ op: "eq", left: "arq_eps_acceleration_qoq", right: 1 }] },
    ];
    const where = filterTreesToIr(screen) as unknown as { type: string; items: { name?: string }[] };
    expect(where.type).toBe("all");
    expect(where.items.map((i) => i.name)).toEqual(["membership", "code_33"]);
    expect(screenTreesForWhere(where as never)).not.toBeNull();
  });

  it("drops a nameless top-level AND into a flat clause list", () => {
    const wrapped = { type: "all", items: [cmpIr("close", "sma50d"), cmpIr("rs_rating", "sma200d")] } as unknown as IrWhereNode;
    const trees = screenTreesForWhere(wrapped);
    expect(trees).toHaveLength(2); // the clauses themselves, not one wrapper group
    expect(filterTreesToIr(trees!)).toEqual(wrapped); // same meaning, one level less
  });

  it("flattens a named root AND too — a leftover label is not addressable", () => {
    const legacy = { type: "all", name: "hygiene", items: [cmpIr("close", "sma50d"), cmpIr("avg_vol_50d", "close")] } as unknown as IrWhereNode;
    const trees = screenTreesForWhere(legacy);
    expect(trees).toHaveLength(2);
    // same clauses, same where — with the inert label dropped along with the wrapper
    const compiled = filterTreesToIr(trees!) as { type: string; items: unknown[] };
    expect(compiled.type).toBe("all");
    expect(compiled.items).toHaveLength(2);
    expect(JSON.stringify(compiled)).not.toContain("hygiene");
  });

  it("keeps the reserved `membership` group and a top-level OR as nodes", () => {
    const named = { type: "all", name: "membership", items: [cmpIr("close", "sma50d")] } as unknown as IrWhereNode;
    const namedTrees = screenTreesForWhere(named);
    expect(namedTrees).toHaveLength(1);
    expect(namedTrees![0]).toMatchObject({ logic: "and", name: "membership" });

    const orRoot = { type: "any", items: [cmpIr("close", "sma50d"), cmpIr("rs_rating", "sma200d")] } as unknown as IrWhereNode;
    const orTrees = screenTreesForWhere(orRoot);
    expect(orTrees).toHaveLength(1);
    expect(orTrees![0]).toMatchObject({ logic: "or" });
  });

  it("treats an empty screen as empty, not as a mismatch", () => {
    expect(screenTreesForWhere({ type: "all", items: [] } as unknown as IrWhereNode)).toEqual([]);
  });
});
