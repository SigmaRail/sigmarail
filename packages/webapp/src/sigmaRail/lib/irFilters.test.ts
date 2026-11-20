import { describe, it, expect } from "vitest";
import {
  groupsToWhere,
  extractAppliedFilterGroups,
  applyGroupsToSpec,
  emptyFilterGroup,
  cloneOperand,
} from "./irFilters";
import type { AppliedFilterGroup, AppliedFilterRow, UniverseQueryV1 } from "../types";

function cmp(id: string, left: string, op: AppliedFilterRow["op"], value: number): AppliedFilterRow {
  return {
    id,
    op,
    left: { type: "col", name: left },
    right: { type: "lit", value },
  };
}

function group(logic: "all" | "any", rows: AppliedFilterRow[]): AppliedFilterGroup {
  return { id: `g_${logic}_${rows.length}_${Math.random()}`, logic, rows };
}

describe("group AST mapping (Deepvue ALL/ANY)", () => {
  it("lowers group 1 to top-level ALL and later groups to ANY", () => {
    const where = groupsToWhere([
      group("all", [cmp("a", "close", "gte", 10), cmp("b", "rs_rating", "gte", 70)]),
      group("any", [cmp("c", "close", "gte", 5), cmp("d", "sma200d_rising_30d", "eq", 1)]),
    ]);
    expect(where).toMatchObject({ type: "all" });
    const items = (where as { items: unknown[] }).items;
    expect(items).toHaveLength(3);
    expect((items[0] as { type: string }).type).toBe("gte");
    expect((items[2] as { type: string; items: unknown[] }).type).toBe("any");
    expect((items[2] as { items: unknown[] }).items).toHaveLength(2);
  });

  it("round-trips groups through where -> groups", () => {
    const original = [
      group("all", [cmp("a", "close", "gte", 10)]),
      group("any", [cmp("b", "rs_rating", "gte", 90), cmp("c", "close", "gte", 5)]),
      group("any", [cmp("d", "vcp_consolidation_days_5pct_30d", "gte", 5)]),
    ];
    const parsed = extractAppliedFilterGroups(groupsToWhere(original));
    expect(parsed).toHaveLength(3);
    expect(parsed[0]!.logic).toBe("all");
    expect(parsed[0]!.rows).toHaveLength(1);
    expect(parsed[1]!.logic).toBe("any");
    expect(parsed[1]!.rows).toHaveLength(2);
    expect(parsed[2]!.logic).toBe("any");
    expect(parsed[2]!.rows).toHaveLength(1);
  });

  it("preserves a lone top-level ANY as one ANY group", () => {
    const parsed = extractAppliedFilterGroups({
      type: "any",
      items: [
        {
          type: "gte",
          left: { type: "col", name: "rs_rating" },
          right: { type: "lit", value: 90 },
        },
      ],
    });
    expect(parsed).toHaveLength(1);
    expect(parsed[0]!.logic).toBe("any");
    expect(parsed[0]!.rows).toHaveLength(1);
  });

  it("collapses a single condition to a bare comparison node", () => {
    const where = groupsToWhere([group("all", [cmp("a", "close", "gte", 10)])]);
    expect(where).toEqual({
      type: "gte",
      left: { type: "col", name: "close" },
      right: { type: "lit", value: 10 },
    });
  });

  it("folds a nested AND group back into the primary ALL group", () => {
    const where = groupsToWhere([
      group("all", [cmp("a", "close", "gte", 10)]),
      group("any", [cmp("b", "rs_rating", "gte", 90)]),
    ]);
    // Wrap group 1 in a nested `all` to simulate an externally-authored spec.
    const nested = {
      type: "all",
      items: [
        { type: "all", items: (where as { items: unknown[] }).items.slice(0, 1) },
        (where as { items: unknown[] }).items[1],
      ],
    };
    const parsed = extractAppliedFilterGroups(nested as never);
    expect(parsed[0]!.rows).toHaveLength(1);
    expect(parsed[1]!.logic).toBe("any");
  });

  it("applyGroupsToSpec replaces where without mutating select/order_by", () => {
    const spec = {
      version: 1,
      from: "daily_screener",
      select: ["ticker", "close"],
      where: { type: "all", items: [] },
      order_by: [{ field: "close", direction: "desc" }],
      limit_per_day: 50,
    } as UniverseQueryV1;
    const next = applyGroupsToSpec(spec, [group("all", [cmp("a", "close", "gte", 10)])]);
    expect(next.select).toEqual(["ticker", "close"]);
    expect(next.order_by).toEqual([{ field: "close", direction: "desc" }]);
    expect(next.where).toMatchObject({ type: "gte" });
  });

  it("ORs a named code_33 group with membership and ANDs its pills", () => {
    const where = groupsToWhere([
      { id: "g1", logic: "all", name: "membership", rows: [cmp("a", "close", "gte", 5)] },
      {
        id: "g2",
        logic: "all",
        name: "code_33",
        rows: [
          cmp("b", "arq_eps_growth_yoy", "gte", 0.25),
          cmp("c", "arq_eps_acceleration_qoq", "eq", 1),
        ],
      },
    ]);
    expect(where).toMatchObject({ type: "any" });
    const items = (where as { items: { name?: string; type?: string; items?: unknown[] }[] }).items;
    expect(items.map((i) => i.name)).toEqual(["membership", "code_33"]);
    expect(items[1]).toMatchObject({ type: "all", name: "code_33" });
    expect(items[1]!.items).toHaveLength(2);
    const parsed = extractAppliedFilterGroups(where);
    const code33 = parsed.find((g) => g.name === "code_33");
    expect(code33?.logic).toBe("all");
    expect(code33?.rows).toHaveLength(2);
  });

  it("emptyFilterGroup defaults to ALL with no rows", () => {
    const g = emptyFilterGroup();
    expect(g.logic).toBe("all");
    expect(g.rows).toEqual([]);
  });

  it("cloneOperand preserves bar offsets on columns", () => {
    expect(cloneOperand({ type: "col", name: "close", offset: -1 })).toEqual({
      type: "col",
      name: "close",
      offset: -1,
    });
  });
});
