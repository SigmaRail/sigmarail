import { describe, expect, it } from "vitest";
import {
  stockFromPath,
  stockPath,
  strategyIrIdFromPath,
  strategyPath,
  tabForPath,
} from "./routes";

describe("strategyPath / strategyIrIdFromPath", () => {
  it("builds bare and ir_id paths", () => {
    expect(strategyPath()).toBe("/strategies");
    expect(strategyPath("")).toBe("/strategies");
    expect(strategyPath("my-spec")).toBe("/strategies/my-spec");
    expect(strategyPath("a/b")).toBe("/strategies/a%2Fb");
  });

  it("parses ir_id from path", () => {
    expect(strategyIrIdFromPath("/strategies")).toBeNull();
    expect(strategyIrIdFromPath("/strategies/")).toBeNull();
    expect(strategyIrIdFromPath("/strategies/my-spec")).toBe("my-spec");
    expect(strategyIrIdFromPath("/strategies/a%2Fb")).toBe("a/b");
  });

  it("maps strategies segment to compose tab", () => {
    expect(tabForPath("/strategies")).toBe("compose");
    expect(tabForPath("/strategies/foo")).toBe("compose");
  });
});

describe("stockPath / stockFromPath", () => {
  it("builds the canonical ticker path", () => {
    expect(stockPath("nvda")).toBe("/stock/NVDA/chart");
    expect(stockPath(" nvda ", "chart")).toBe("/stock/NVDA/chart");
    expect(stockPath("brk.b")).toBe("/stock/BRK.B/chart");
  });

  it("parses ticker + section", () => {
    expect(stockFromPath("/stock/NVDA/chart")).toEqual({ ticker: "NVDA", section: "chart" });
    expect(stockFromPath("/stock/nvda")).toEqual({ ticker: "NVDA", section: "chart" });
    expect(stockFromPath("/stock/BRK.B/chart")).toEqual({ ticker: "BRK.B", section: "chart" });
  });

  it("falls back to chart for an unknown section and null for a bare path", () => {
    expect(stockFromPath("/stock/NVDA/technical-analysis").section).toBe("chart");
    expect(stockFromPath("/stock")).toEqual({ ticker: null, section: "chart" });
    expect(stockFromPath("/stock/")).toEqual({ ticker: null, section: "chart" });
  });

  it("maps the stock segment to the charts tab (and keeps /charts working)", () => {
    expect(tabForPath("/stock/NVDA/chart")).toBe("charts");
    expect(tabForPath("/stock/NVDA")).toBe("charts");
    expect(tabForPath("/charts")).toBe("charts");
  });
});
