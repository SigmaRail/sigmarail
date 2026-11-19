import { describe, expect, it } from "vitest";
import { describeScreenerFilters } from "./ScreenerFilterSummary";

const fields = [
  { name: "rs_rating", label: "RS Rating", category: "momentum" },
  { name: "exchange", label: "Exchange", category: "security" },
];

describe("describeScreenerFilters", () => {
  it("uses field labels and preserves nested ALL/ANY meaning", () => {
    const where = {
      type: "all",
      items: [
        { type: "gte", left: { type: "col", name: "rs_rating" }, right: { type: "lit", value: 80 } },
        {
          type: "any",
          items: [
            { type: "eq", left: { type: "col", name: "exchange" }, right: { type: "lit", value: "NYSE" } },
            { type: "eq", left: { type: "col", name: "exchange" }, right: { type: "lit", value: "NASDAQ" } },
          ],
        },
      ],
    };
    expect(describeScreenerFilters(where, fields)).toBe(
      "RS Rating ≥ 80 and (Exchange = “NYSE” or Exchange = “NASDAQ”)",
    );
  });

  it("describes an empty screen without exposing AST details", () => {
    expect(describeScreenerFilters({ type: "all", items: [] }, fields)).toBe("All stocks match");
  });

  it("formats arithmetic expressions and prior-period offsets", () => {
    const where = {
      type: "gte",
      left: { type: "formula", op: "/", args: [{ type: "col", name: "sales", offset: -1 }, { type: "lit", value: 100 }] },
      right: { type: "lit", value: 1.2 },
    };
    expect(describeScreenerFilters(where, fields)).toBe("sales (-1d) / 100 ≥ 1.2");
  });
});
