import { describe, expect, it } from "vitest";
import type { PipelineDocument, Stage } from "../components/strategy/StrategyDocument";
import {
  countAsSignalAliases,
  ensureScreensHitMeasures,
  sumColsExpr,
} from "./screensHitMeasure";

function gateFilters(): Stage["filters"] {
  return [
    {
      logic: "and",
      conditions: [
        {
          left: { type: "col", name: "close" },
          op: "gt",
          right: { type: "lit", value: 0 },
        },
      ],
    },
  ];
}

function baseDoc(): PipelineDocument {
  return {
    strategy_name: "test",
    gate_combine: "count",
    stages: [
      {
        mode: "score",
        name: "S1",
        id: "screen_1",
        as_gate: true,
        count_as_signal: true,
        signal_weight: 1,
        filters: gateFilters(),
        factors: [],
      },
      {
        mode: "score",
        name: "S2",
        id: "screen_2",
        as_gate: true,
        count_as_signal: true,
        signal_weight: 1,
        filters: gateFilters(),
        factors: [],
      },
    ],
  };
}

describe("screensHitMeasure", () => {
  it("builds sum formula AST", () => {
    expect(sumColsExpr(["screen_1", "screen_2"])).toEqual({
      type: "formula",
      op: "+",
      args: [
        { type: "col", name: "screen_1" },
        { type: "col", name: "screen_2" },
      ],
    });
  });

  it("ensures screens_hit computed_expr stage", () => {
    const next = ensureScreensHitMeasures(baseDoc());
    const hit = next.stages.find((s) => (s.id || "") === "screens_hit");
    expect(hit?.computed_expr).toEqual(sumColsExpr(["screen_1", "screen_2"]));
    expect(countAsSignalAliases(next.stages)).toEqual(["screen_1", "screen_2"]);
  });

  it("inserts screens_hit after the last gate", () => {
    const next = ensureScreensHitMeasures(baseDoc());
    const ids = next.stages.map((s) => s.id);
    expect(ids).toEqual(["screen_1", "screen_2", "screens_hit"]);
  });
});
