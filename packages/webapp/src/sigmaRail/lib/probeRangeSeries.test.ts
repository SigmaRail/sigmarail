import { describe, expect, it } from "vitest";
import { buildProbeRangeSeries } from "./probeRangeSeries";

describe("buildProbeRangeSeries", () => {
  it("maps member_counts and measure_series to ascending day points", () => {
    const out = buildProbeRangeSeries({
      dates: ["2024-01-02", "2024-01-03", "bad", "2024-01-05"],
      member_counts: [10, 12, 99, 14],
      measure_series: {
        screen_1: [0.2, 0.3, 0.9, 0.4],
        screens_hit: [2, 3, 9, 4],
      },
      maxMeasures: 2,
    });
    expect(out.memberCount).toEqual([
      { time: "2024-01-02", value: 10 },
      { time: "2024-01-03", value: 12 },
      { time: "2024-01-05", value: 14 },
    ]);
    expect(out.measures.map((m) => m.id)).toEqual(["screen_1", "screens_hit"]);
    expect(out.measures[0]!.points).toEqual([
      { time: "2024-01-02", value: 0.2 },
      { time: "2024-01-03", value: 0.3 },
      { time: "2024-01-05", value: 0.4 },
    ]);
  });

  it("caps measure series count", () => {
    const series: Record<string, number[]> = {};
    for (let i = 0; i < 6; i++) series[`m${i}`] = [i];
    const out = buildProbeRangeSeries({
      dates: ["2024-06-01"],
      member_counts: [1],
      measure_series: series,
      maxMeasures: 3,
    });
    expect(out.measures).toHaveLength(3);
  });
});
