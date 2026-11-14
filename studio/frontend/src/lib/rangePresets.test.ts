import { describe, expect, it } from "vitest";
import { clampWindow, daysBetween, presetWindow, subtractMonths } from "./rangePresets";

describe("subtractMonths", () => {
  it("steps whole months back", () => {
    expect(subtractMonths("2026-09-23", 1)).toBe("2026-08-23");
    expect(subtractMonths("2026-09-23", 12)).toBe("2025-09-23");
    expect(subtractMonths("2026-09-23", 6)).toBe("2026-03-23");
  });

  it("clamps to the shorter month instead of rolling forward", () => {
    expect(subtractMonths("2026-03-31", 1)).toBe("2026-02-28");
    expect(subtractMonths("2026-08-31", 6)).toBe("2026-02-28");
    expect(subtractMonths("2024-03-31", 1)).toBe("2024-02-29"); // leap year keeps the 29th
  });

  it("crosses year boundaries", () => {
    expect(subtractMonths("2026-01-15", 2)).toBe("2025-11-15");
    expect(subtractMonths("2026-01-15", 24)).toBe("2024-01-15");
  });

  it("returns the input unchanged when it is not an ISO date", () => {
    expect(subtractMonths("", 3)).toBe("");
    expect(subtractMonths("nonsense", 3)).toBe("nonsense");
  });
});

describe("presetWindow", () => {
  const TO = "2026-09-23";
  /** Older than any plausible cap, so the clamp is what is being asserted. */
  const TOO_OLD = subtractMonths(TO, 12 * 40);

  it("ends every window at the given date", () => {
    for (const id of ["1M", "3M", "6M", "1Y", "2Y", "YTD", "MAX"] as const) {
      expect(presetWindow(id, TO)?.to).toBe(TO);
    }
  });

  it("computes each relative span", () => {
    expect(presetWindow("1M", TO)?.from).toBe("2026-08-23");
    expect(presetWindow("3M", TO)?.from).toBe("2026-06-23");
    expect(presetWindow("6M", TO)?.from).toBe("2026-03-23");
    expect(presetWindow("1Y", TO)?.from).toBe("2025-09-23");
    expect(presetWindow("2Y", TO)?.from).toBe("2024-09-23");
  });

  it("starts YTD at the first of the year, and Max at the data floor", () => {
    expect(presetWindow("YTD", TO)?.from).toBe("2026-01-01");
    expect(presetWindow("MAX", TO, "2019-04-01")?.from).toBe("2019-04-01");
    // with no known floor, Max reaches far back rather than pretending to be 1Y
    expect(presetWindow("MAX", TO)?.from).toBe(subtractMonths(TO, 360));
  });

  it("never goes before the data floor, and never inverts", () => {
    expect(presetWindow("2Y", TO, "2026-01-01")?.from).toBe("2026-01-01");
    expect(presetWindow("1Y", "2019-04-01", "2019-04-01")?.from).toBe("2019-04-01");
    // however old the floor is, it is the floor — there is no width cap
    expect(presetWindow("MAX", TO, TOO_OLD)?.from).toBe(TOO_OLD);
  });

  it("imposes no width limit: the whole history is a legal window", () => {
    // 1997-12-31 → today is ~10,500 days and must pass through untouched
    const wholeHistory = presetWindow("MAX", TO, "1997-12-31");
    expect(wholeHistory).toEqual({ from: "1997-12-31", to: TO });
    expect(daysBetween(wholeHistory!.from, wholeHistory!.to)).toBeGreaterThan(10000);
    expect(presetWindow("2Y", TO)).toEqual({ from: "2024-09-23", to: TO });
  });

  it("only normalises an inverted pair, never the width", () => {
    expect(clampWindow("1990-01-01", "2026-09-23")).toEqual({ from: "1990-01-01", to: "2026-09-23" });
    expect(clampWindow("2026-01-01", "2026-09-23")).toEqual({ from: "2026-01-01", to: "2026-09-23" });
    // inverted: collapse to the end date rather than asking for a negative span
    expect(clampWindow("2026-09-23", "2026-01-01").from).toBe("2026-01-01");
  });

  it("returns null for a date it cannot parse", () => {
    expect(presetWindow("1M", "")).toBeNull();
    expect(presetWindow("1M", "23/09/2026")).toBeNull();
  });
});
