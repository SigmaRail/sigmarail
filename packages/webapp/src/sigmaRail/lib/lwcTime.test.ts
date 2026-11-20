import { describe, expect, it } from "vitest";
import { lwcTimeToIsoDate } from "./lwcTime";

describe("lwcTimeToIsoDate", () => {
  it("passes through business-day strings", () => {
    expect(lwcTimeToIsoDate("2025-06-15")).toBe("2025-06-15");
  });

  it("formats BusinessDay objects", () => {
    expect(lwcTimeToIsoDate({ year: 2025, month: 3, day: 7 })).toBe("2025-03-07");
  });

  it("returns null for empty", () => {
    expect(lwcTimeToIsoDate(null)).toBeNull();
    expect(lwcTimeToIsoDate(undefined)).toBeNull();
  });
});
