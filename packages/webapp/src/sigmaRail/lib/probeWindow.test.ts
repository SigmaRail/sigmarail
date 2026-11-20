import { describe, expect, it } from "vitest";
import {
  PROBE_CHUNK_DAYS,
  addCalendarDays,
  extendWindowStart,
  latestChunkWindowStart,
} from "./probeWindow";

describe("probeWindow", () => {
  it("defaults to a 365-day chunk", () => {
    expect(PROBE_CHUNK_DAYS).toBe(365);
  });

  it("latestChunkWindowStart is asOf−365d when within backtest", () => {
    // 2024 is a leap year: Dec 31 − 365d → Jan 1 same year.
    expect(latestChunkWindowStart("2024-12-31", "2020-01-01")).toBe("2024-01-01");
  });

  it("latestChunkWindowStart floors at backtestStart", () => {
    expect(latestChunkWindowStart("2024-02-01", "2024-01-01")).toBe("2024-01-01");
  });

  it("extendWindowStart steps one chunk earlier and clamps", () => {
    expect(extendWindowStart("2024-01-01", "2020-01-01")).toBe("2023-01-01");
    expect(extendWindowStart("2020-02-01", "2020-01-01")).toBe("2020-01-01");
  });

  it("addCalendarDays shifts by UTC day", () => {
    expect(addCalendarDays("2024-12-31", -365)).toBe("2024-01-01");
  });
});
