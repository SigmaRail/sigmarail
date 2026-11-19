import { describe, expect, it } from "vitest";
import type { PipelineDocument, Stage } from "../components/strategy/StrategyDocument";
import {
  insightPropertyAliases,
  measureAliasesForLookup,
  orderByMeasureAliases,
  patchInsightPropertyAlias,
} from "./insightMeasureBindings";

function stage(partial: Partial<Stage> & Pick<Stage, "mode">): Stage {
  return {
    name: partial.name ?? partial.id ?? "m",
    filters: [],
    factors: [],
    ...partial,
  } as Stage;
}

describe("measureAliasesForLookup", () => {
  it("lists measure stage ids only (not raw L7 field names)", () => {
    const stages = [
      stage({
        mode: "score",
        id: "screen_1",
        as_gate: true,
        filters: [{ logic: "and", conditions: [] }],
      }),
      stage({
        mode: "score",
        id: "slope_sign",
        as_gate: true,
        computed_expr: { type: "lit", value: 1 },
      }),
      stage({
        mode: "score",
        id: "rs_rating",
        as_gate: true,
        computed_expr: { type: "col", name: "rs_rating" },
      }),
      stage({ mode: "signal", id: "setup_pass", filters: [] }),
    ];
    const aliases = measureAliasesForLookup(stages);
    expect(aliases).toEqual(["screen_1", "slope_sign", "rs_rating"]);
    // Legacy API ignores catalog field dump
    expect(insightPropertyAliases(stages, ["close", "volume", "overall_score"])).toEqual(
      aliases,
    );
  });
});

describe("orderByMeasureAliases", () => {
  it("keeps alpha_rank entries that are measures; drops unbound select harvest", () => {
    const stages = [
      stage({
        mode: "score",
        id: "screens_hit",
        as_gate: true,
        computed_expr: { type: "col", name: "screen_1" },
      }),
      stage({
        mode: "score",
        id: "rs_rating",
        as_gate: true,
        computed_expr: { type: "col", name: "rs_rating" },
      }),
    ];
    const doc: PipelineDocument = {
      strategy_name: "t",
      stages,
      bindings: {
        alpha_rank: ["screens_hit", "rs_rating", "overall_score"],
      },
    };
    expect(orderByMeasureAliases(doc)).toEqual(["screens_hit", "rs_rating"]);
  });

  it("excludes rs_rating from ORDER BY when it is not a measure", () => {
    const stages = [
      stage({
        mode: "score",
        id: "screens_hit",
        as_gate: true,
        computed_expr: { type: "lit", value: 1 },
      }),
    ];
    const doc: PipelineDocument = {
      strategy_name: "t",
      stages,
      bindings: { alpha_rank: ["screens_hit", "rs_rating"] },
    };
    expect(orderByMeasureAliases(doc)).toEqual(["screens_hit"]);
  });

  it("drops screens_hit from ORDER BY when it is not a measure stage", () => {
    const stages = [
      stage({
        mode: "score",
        id: "rs_rating",
        as_gate: true,
        computed_expr: { type: "col", name: "rs_rating" },
      }),
    ];
    const doc: PipelineDocument = {
      strategy_name: "t",
      gate_combine: "count",
      stages,
      bindings: { alpha_rank: ["screens_hit", "rs_rating"] },
    };
    expect(orderByMeasureAliases(doc)).toEqual(["rs_rating"]);
  });
});

describe("whereMeasureAliases", () => {
  it("lists setup_pass under WHERE when Insight ✓ on setup", async () => {
    const { whereMeasureAliases } = await import("./insightMeasureBindings");
    const doc: PipelineDocument = {
      strategy_name: "t",
      stages: [stage({ mode: "signal", id: "setup_pass", filters: [] })],
      bindings: {
        alpha_setup: {
          kind: "bool",
          where: {
            type: "all",
            items: [
              {
                type: "eq",
                left: { type: "col", name: "setup_pass" },
                right: { type: "lit", value: 1 },
              },
            ],
          },
        },
      },
    };
    expect(whereMeasureAliases(doc)).toEqual({
      setup: ["setup_pass"],
      eligibility: [],
    });
    expect(orderByMeasureAliases(doc)).toEqual([]);
  });
});

describe("repairHitRankBindings", () => {
  it("is a no-op (no reserved screens_hit rank)", async () => {
    const { repairHitRankBindings } = await import("./insightMeasureBindings");
    const stages = [
      stage({
        mode: "score",
        id: "hit_count",
        as_gate: true,
        computed_expr: { type: "lit", value: 1 },
      }),
      stage({
        mode: "score",
        id: "rs_rating",
        as_gate: true,
        computed_expr: { type: "col", name: "rs_rating" },
      }),
    ];
    const doc: PipelineDocument = {
      strategy_name: "t",
      gate_combine: "count",
      stages,
      bindings: { alpha_rank: ["rs_rating"] },
    };
    expect(repairHitRankBindings(doc).bindings?.alpha_rank).toEqual(["rs_rating"]);
  });
});

describe("renameMeasureAlias", () => {
  it("renames stage id and remaps alpha_rank + property bindings", async () => {
    const { renameMeasureAlias } = await import("./insightMeasureBindings");
    const stages = [
      stage({
        mode: "score",
        id: "screens_hit",
        as_gate: true,
        computed_expr: {
          type: "formula",
          op: "+",
          args: [
            { type: "col", name: "screen_1" },
            { type: "col", name: "screen_2" },
          ],
        },
      }),
      stage({
        mode: "score",
        id: "w_conviction",
        as_gate: true,
        computed_expr: {
          type: "formula",
          op: "/",
          args: [
            { type: "col", name: "screens_hit" },
            { type: "lit", value: 5 },
          ],
        },
      }),
    ];
    const doc: PipelineDocument = {
      strategy_name: "t",
      stages,
      bindings: {
        alpha_rank: ["screens_hit", "rs_rating"],
        alpha_rank_directions: { screens_hit: "desc" },
        alpha_weight: {
          kind: "number",
          expr: { type: "col", name: "screens_hit" },
        },
      },
    };
    const next = renameMeasureAlias(doc, 0, "hit_count");
    expect(next.stages[0]?.id).toBe("hit_count");
    expect(next.bindings?.alpha_rank).toEqual(["hit_count", "rs_rating"]);
    expect(next.bindings?.alpha_rank_directions).toEqual({ hit_count: "desc" });
    expect(next.bindings?.alpha_weight).toEqual({
      kind: "number",
      expr: { type: "col", name: "hit_count" },
    });
    expect(next.stages[1]?.computed_expr).toEqual({
      type: "formula",
      op: "/",
      args: [
        { type: "col", name: "hit_count" },
        { type: "lit", value: 5 },
      ],
    });
  });
});

describe("applySepaInsightPropertyBindings", () => {
  it("binds Champion SEPA Insight.Price aliases when measures exist", async () => {
    const { applySepaInsightPropertyBindings } = await import("./insightMeasureBindings");
    const stages = [
      stage({
        mode: "score",
        id: "insight_dir",
        as_gate: true,
        computed_expr: { type: "lit", value: 1 },
      }),
      stage({
        mode: "score",
        id: "mag_thrust",
        as_gate: true,
        computed_expr: { type: "lit", value: 0.1 },
      }),
      stage({
        mode: "score",
        id: "w_conviction",
        as_gate: true,
        computed_expr: { type: "lit", value: 0.8 },
      }),
      stage({
        mode: "score",
        id: "conf_scale",
        as_gate: true,
        computed_expr: { type: "lit", value: 0.8 },
      }),
    ];
    const doc: PipelineDocument = { strategy_name: "t", stages, bindings: {} };
    const { used, missing, bindings } = applySepaInsightPropertyBindings(doc);
    expect(missing).toEqual([]);
    expect(used).toEqual({
      alpha_direction: "insight_dir",
      alpha_magnitude: "mag_thrust",
      alpha_weight: "w_conviction",
      alpha_confidence: "conf_scale",
    });
    expect(bindings.alpha_insight_period_days).toBe(1);
  });
});

describe("patchInsightPropertyAlias", () => {
  it("binds and clears Direction from a measure alias", () => {
    const bound = patchInsightPropertyAlias(null, "alpha_direction", "slope_sign");
    expect(bound.alpha_direction).toEqual({
      kind: "number",
      expr: { type: "col", name: "slope_sign" },
    });
    const cleared = patchInsightPropertyAlias(bound, "alpha_direction", null);
    expect(cleared.alpha_direction).toBeNull();
  });
});
