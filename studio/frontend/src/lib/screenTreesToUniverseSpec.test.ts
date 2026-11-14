import { describe, expect, it } from "vitest";
import {
  REQUIRED_MEMBERSHIP_SELECT,
  screenTreesToUniverseSpec,
} from "../components/studio/UniverseSlotCard";

describe("screenTreesToUniverseSpec", () => {
  it("builds screener UniverseQueryV1 from empty screen", () => {
    const spec = screenTreesToUniverseSpec([]);
    expect(spec.from).toBe("screener");
    expect(spec.select).toEqual([...REQUIRED_MEMBERSHIP_SELECT]);
    expect(spec.where).toEqual({ type: "all", items: [] });
    expect(spec.limit_per_day).toBe(5000);
  });

  it("compiles a filter condition into where", () => {
    const spec = screenTreesToUniverseSpec([
      {
        op: "gte",
        left: "close",
        right: 10,
        right_kind: "lit",
      },
    ]);
    expect(spec.where).toMatchObject({ type: "gte" });
  });

  it("merges optional extraSelect and keeps required cols", () => {
    const spec = screenTreesToUniverseSpec([], {
      extraSelect: ["minervini_score", "sector", "exchange"],
    });
    expect(spec.select?.slice(0, REQUIRED_MEMBERSHIP_SELECT.length)).toEqual([
      ...REQUIRED_MEMBERSHIP_SELECT,
    ]);
    expect(spec.select).toContain("minervini_score");
    expect(spec.select).toContain("sector");
    // enrich-only: not IR-selectable
    expect(spec.select).not.toContain("exchange");
  });

  it("includes sortField in select when not already required", () => {
    const spec = screenTreesToUniverseSpec([], {
      sortField: "technical_rating",
      sortDir: "asc",
    });
    expect(spec.select).toContain("technical_rating");
    expect(spec.order_by?.[0]).toEqual({
      field: "technical_rating",
      direction: "asc",
    });
  });
});
