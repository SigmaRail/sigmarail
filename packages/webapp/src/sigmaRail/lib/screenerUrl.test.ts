import { describe, expect, it } from "vitest";
import {
  FILTERS_MAX_ENCODED,
  astParams,
  buildScreenerSearch,
  readScreenerState,
  screenerHref,
} from "./screenerUrl";
import { astToWhere, countPredicates, whereToAst, type AstNode } from "./screenAst";
import { extractAppliedFilterGroups } from "./irFilters";

// A tree the old chips codec could not carry: a not, a division, and three levels.
const AST: AstNode = {
  type: "all",
  name: "hygiene",
  items: [
    { type: "gte", left: { type: "col", name: "close" }, right: { type: "lit", value: 5 } },
    {
      type: "not",
      item: { type: "eq", left: { type: "col", name: "industry" }, right: { type: "lit", value: "Biotechnology" } },
    },
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

describe("screener address — the AST itself", () => {
  it("writes the tree readably, path-keyed, with no ids", () => {
    const q = buildScreenerSearch({ screen: "7", where: AST });
    expect(q).toContain("screen=7");
    expect(q).toContain("g=all:hygiene");
    expect(q).toContain("f.0=close>=5");
    expect(q).toContain("f.1=not(industry='Biotechnology')");
    expect(q).toContain("g.2=any");
    expect(q).toContain("f.2.0=exchange='NYSE'");
    expect(q).toContain("g.3=all:membership");
    expect(q).toContain("f.3.1=atr_pct>=(atr_14/close)");
    expect(q).toContain("f.3.2.1=minervini_score[1]=true");
    expect(q).not.toContain("%20");
    expect(q).not.toMatch(/id\d|v1\.|eyJ/);
  });

  it("round-trips exactly — not, division and three levels intact", () => {
    const state = readScreenerState("?" + buildScreenerSearch({ screen: "7", where: AST }));
    expect(state.where).not.toBeNull();
    expect(astToWhere(state.where!)).toEqual(astToWhere(AST));
    expect(countPredicates(state.where!)).toBe(countPredicates(AST));
    expect(state.filters!.length).toBeGreaterThan(0); // display chips derived for the editor
  });

  it("keeps every child of a group nested inside a group (regression: dropped subtree)", () => {
    // root > named all > any > named all: a group three levels down inside another group
    const deep: AstNode = {
      type: "all",
      name: "universe",
      items: [
        { type: "gt", left: { type: "col", name: "close" }, right: { type: "col", name: "sma50d" } },
        {
          type: "any",
          items: [
            { type: "gte", left: { type: "col", name: "rs_rating" }, right: { type: "lit", value: 85 } },
            {
              type: "all",
              name: "venue",
              items: [
                { type: "eq", left: { type: "col", name: "exchange" }, right: { type: "lit", value: "NYSE" } },
                { type: "eq", left: { type: "col", name: "exchange" }, right: { type: "lit", value: "NASDAQ" } },
              ],
            },
          ],
        },
      ],
    };
    const q = buildScreenerSearch({ where: deep });
    expect(q).toContain("g.1.1=all:venue");
    const back = readScreenerState("?" + q).where;
    expect(back).not.toBeNull();
    expect(astToWhere(back!)).toEqual(astToWhere(deep));
    expect(countPredicates(back!)).toBe(4); // close>sma50d, rs>=85, NYSE, NASDAQ
  });

  it("falls back to the raw node rather than dropping an unwritable one", () => {
    const notGroup: AstNode = { type: "not", item: { type: "all", items: [{ type: "gt", left: { type: "col", name: "a" }, right: { type: "col", name: "b" } }] } };
    const q = buildScreenerSearch({ screen: "7", where: notGroup });
    expect(q).toContain("where=");
    const back = readScreenerState(`?${q}`);
    expect(astToWhere(back.where!)).toEqual(astToWhere(notGroup));
  });

  it("falls back to the raw node when the tree is too long to spell out", () => {
    const huge: AstNode = {
      type: "all",
      items: Array.from({ length: 400 }, (_, i) => ({
        type: "eq" as const,
        left: { type: "col" as const, name: `long_column_name_${i}` },
        right: { type: "lit" as const, value: String(i).padStart(6, "0") },
      })),
    };
    expect(astParams(huge)).toEqual([]);
    expect(buildScreenerSearch({ where: huge })).toContain("where=");
    expect(FILTERS_MAX_ENCODED).toBeGreaterThan(1000);
  });

  it("accepts the editor's chips too, so callers can migrate one at a time", () => {
    const q = buildScreenerSearch({ screen: "7", filters: extractAppliedFilterGroups(astToWhere(AST) as never) });
    expect(q).not.toContain("v1.");          // no legacy blob
    expect(q).not.toContain("where=");       // still the readable AST form
    expect(q).toMatch(/f(\.\d+)*=/);
    expect(q).toContain("f.0=close>=5");
    const back = readScreenerState("?" + q).where;
    expect(back).not.toBeNull();
    expect(countPredicates(back!)).toBeGreaterThan(0);
  });

  it("keeps a just-added (childless) group through the address", () => {
    const withNewGroup: AstNode = { type: "all", name: "membership", items: [AST.items[0]!, { type: "any", items: [] }] };
    const q = buildScreenerSearch({ where: withNewGroup });
    expect(q).toContain("g.1=any");
    expect(astToWhere(readScreenerState("?" + q).where!)).toEqual(astToWhere(withNewGroup));
  });

  it("never emits the editor's `neq` spelling — it is not(eq) in the AST", () => {
    const neq = { type: "neq", left: { type: "col", name: "industry" }, right: { type: "lit", value: "Biotech" } };
    const q = buildScreenerSearch({ where: whereToAst(neq)! });
    expect(q).toContain("f=not(industry='Biotech')");
    expect(q).not.toContain("!=");
  });

  it("still reads the older chips params (short-lived links)", () => {
    const q = "g=all&f=close>sma50d&f=rs_rating>=70&g2=any:exchange&f2=exchange='NYSE'&f2=exchange='NASDAQ'&screen=7";
    const state = readScreenerState(`?${q}`);
    expect(state.screen).toBe("7");
    expect(state.where).not.toBeNull();
    expect(countPredicates(state.where!)).toBe(4);
  });

  it("tolerates a legacy base64 blob and junk", () => {
    const blob = encodeURIComponent("v1." + btoa(JSON.stringify([{ id: "g", logic: "all", rows: [{ id: "r", op: "gt", left: { type: "col", name: "close" }, right: { type: "col", name: "sma50d" } }] }])));
    expect(readScreenerState(`?filters=${blob}&screen=7`).screen).toBe("7");
    expect(readScreenerState("?f=not-a-condition").where).toBeNull();
    expect(readScreenerState("?g=any").where).toEqual({ type: "any", items: [] }); // a just-added group survives
  });
});

describe("reference + defaults", () => {
  it("keeps template > preset > screen precedence", () => {
    expect(buildScreenerSearch({ template: "t", preset: "p", screen: "7" })).toBe("template=t");
    expect(buildScreenerSearch({ preset: "p", screen: "7" })).toBe("preset=p");
    expect(buildScreenerSearch({ screen: "7" })).toBe("screen=7");
  });

  it("omits defaults so a plain screener stays /screens", () => {
    expect(screenerHref({}, { today: "2026-09-23" })).toBe("/screens");
    expect(buildScreenerSearch({ asOf: "2026-09-23", universe: "all" }, { today: "2026-09-23" })).toBe("");
    expect(buildScreenerSearch({ asOf: "2026-09-22" }, { today: "2026-09-23" })).toBe("as_of=2026-09-22");
  });

  it("reads a shared reference link", () => {
    const s = readScreenerState("?template=minervini_trend_template&as_of=2026-09-23&view=grid");
    expect(s.template).toBe("minervini_trend_template");
    expect(s.asOf).toBe("2026-09-23");
    expect(s.view).toBe("grid");
    expect(s.where).toBeNull();
  });
});
