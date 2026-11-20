import { describe, expect, it } from "vitest";
import {
  campaignFillsForSymbol,
  campaignHoldingSignRuns,
  campaignMarkSeries,
  campaignPerformance,
  campaignShareTotals,
  tickerKey,
} from "./campaignFills";

describe("campaignFillsForSymbol", () => {
  it("labels NVDA test/add then time-stop and T1 from order_events fills", () => {
    const orders = [
      {
        symbolValue: "NVDA",
        time: 1707253200,
        status: "filled",
        direction: "buy",
        fillQuantity: 44,
        fillPrice: 68.223,
        quantity: 44,
      },
      {
        symbolValue: "NVDA",
        time: 1707858000,
        status: "filled",
        direction: "buy",
        fillQuantity: 24,
        fillPrice: 72.128,
        quantity: 24,
      },
      {
        symbolValue: "NVDA",
        time: 1708549200,
        status: "filled",
        direction: "sell",
        fillQuantity: -35,
        fillPrice: 68.006,
        quantity: -35,
      },
      {
        symbolValue: "NVDA",
        time: 1708722000,
        status: "filled",
        direction: "sell",
        fillQuantity: -7,
        fillPrice: 80.79,
        quantity: -7,
      },
      {
        symbolValue: "APP",
        time: 1707253200,
        status: "filled",
        direction: "buy",
        fillQuantity: 10,
        fillPrice: 50,
        quantity: 10,
      },
    ];
    const fills = campaignFillsForSymbol(orders, "NVDA 2T");
    expect(fills.map((f) => [f.date, f.kind, f.qty])).toEqual([
      ["2024-02-06", "test", 44],
      ["2024-02-13", "add", 24],
      ["2024-02-21", "time_stop", 35],
      ["2024-02-23", "t1", 7],
    ]);
    expect(fills[2]?.label).toContain("TIME-STOP");
    expect(fills[3]?.label).toContain("T1");
    expect(fills.map((f) => f.openAfter)).toEqual([44, 68, 33, 26]);
    expect(campaignShareTotals(fills)).toEqual({
      bought: 68,
      sold: 42,
      remaining: 26,
    });
  });

  it("treats a near-full sell as a stop and ignores unfilled orders", () => {
    const orders = [
      {
        symbol: { value: "AAPL" },
        lastFillTime: "2024-03-01T20:00:00Z",
        status: 3,
        quantity: 100,
        price: 180,
      },
      {
        symbol: { value: "AAPL" },
        lastFillTime: "2024-03-04T20:00:00Z",
        status: "submitted",
        quantity: -100,
        price: 170,
      },
      {
        symbol: { value: "AAPL" },
        lastFillTime: "2024-03-05T20:00:00Z",
        status: "Filled",
        quantity: -100,
        price: 171,
      },
    ];
    const fills = campaignFillsForSymbol(orders, "AAPL");
    expect(fills).toHaveLength(2);
    expect(fills[0]?.kind).toBe("test");
    expect(fills[1]?.kind).toBe("stop");
  });

  it("resets buyIndex to test when position returns to flat between campaigns", () => {
    const orders = [
      { symbolValue: "TSLA", time: "2024-01-02", status: "filled", direction: "buy", fillQuantity: 50, fillPrice: 200, quantity: 50 },
      { symbolValue: "TSLA", time: "2024-01-05", status: "filled", direction: "buy", fillQuantity: 25, fillPrice: 210, quantity: 25 },
      { symbolValue: "TSLA", time: "2024-01-10", status: "filled", direction: "sell", fillQuantity: -75, fillPrice: 220, quantity: -75 },
      // New campaign weeks later
      { symbolValue: "TSLA", time: "2024-02-01", status: "filled", direction: "buy", fillQuantity: 40, fillPrice: 190, quantity: 40 },
    ];
    const fills = campaignFillsForSymbol(orders, "TSLA");
    expect(fills).toHaveLength(4);
    expect(fills[0]?.kind).toBe("test");
    expect(fills[1]?.kind).toBe("add");
    expect(fills[2]?.kind).toBe("stop");
    expect(fills[3]?.kind).toBe("test");
  });

  it("normalizes Lean ticker suffixes", () => {
    expect(tickerKey("NVDA 2T")).toBe("NVDA");
    expect(tickerKey("AAPL")).toBe("AAPL");
  });
});

describe("campaignPerformance", () => {
  it("marks leftover COIN shares so total P&L matches cash + runner", () => {
    const orders = [
      { symbolValue: "COIN", time: "2024-02-27", status: "filled", direction: "buy", fillQuantity: 15, fillPrice: 199.22, quantity: 15 },
      { symbolValue: "COIN", time: "2024-02-29", status: "filled", direction: "buy", fillQuantity: 9, fillPrice: 203.56, quantity: 9 },
      { symbolValue: "COIN", time: "2024-03-05", status: "filled", direction: "sell", fillQuantity: -5, fillPrice: 230, quantity: -5 },
      { symbolValue: "COIN", time: "2024-03-11", status: "filled", direction: "sell", fillQuantity: -7, fillPrice: 270.085, quantity: -7 },
      { symbolValue: "COIN", time: "2024-03-26", status: "filled", direction: "sell", fillQuantity: -4, fillPrice: 280.12, quantity: -4 },
    ];
    const fills = campaignFillsForSymbol(orders, "COIN");
    const perf = campaignPerformance(fills, 265.12);
    expect(perf).not.toBeNull();
    expect(perf!.bought).toBe(24);
    expect(perf!.sold).toBe(16);
    expect(perf!.remaining).toBe(8);
    expect(perf!.avgEntry).toBeCloseTo(200.8475, 3);
    expect(perf!.totalPnl).toBeCloseTo(1461.695, 2);
    expect(perf!.returnPct).toBeCloseTo(1461.695 / 4820.34, 4);
    expect(perf!.realizedPnl).toBeGreaterThan(0);
    expect(perf!.unrealizedPnl).toBeGreaterThan(0);
  });
});

describe("campaignMarkSeries", () => {
  it("marks P&L at each close and stops after a flatten", () => {
    const fills = campaignFillsForSymbol(
      [
        {
          symbolValue: "XYZ",
          time: "2024-01-02",
          status: "filled",
          direction: "buy",
          fillQuantity: 10,
          fillPrice: 100,
          quantity: 10,
        },
        {
          symbolValue: "XYZ",
          time: "2024-01-04",
          status: "filled",
          direction: "sell",
          fillQuantity: -10,
          fillPrice: 108,
          quantity: -10,
        },
      ],
      "XYZ",
    );
    const marks = campaignMarkSeries(fills, [
      { date: "2024-01-01", close: 99 },
      { date: "2024-01-02", close: 98 },
      { date: "2024-01-03", close: 105 },
      { date: "2024-01-04", close: 110 },
      { date: "2024-01-05", close: 120 },
    ]);
    expect(marks.map((m) => [m.date, m.remaining, Math.round(m.totalPnl)])).toEqual([
      ["2024-01-02", 10, -20],
      ["2024-01-03", 10, 50],
      ["2024-01-04", 0, 80],
    ]);
    expect(campaignHoldingSignRuns(marks)).toEqual([
      { startDate: "2024-01-02", endDate: "2024-01-02", positive: false },
      { startDate: "2024-01-03", endDate: "2024-01-04", positive: true },
    ]);
  });

  it("turns green after a later rally even if an early clip was underwater", () => {
    const fills = campaignFillsForSymbol(
      [
        {
          symbolValue: "NVDA",
          time: "2024-02-06",
          status: "filled",
          direction: "buy",
          fillQuantity: 44,
          fillPrice: 68.223,
          quantity: 44,
        },
        {
          symbolValue: "NVDA",
          time: "2024-02-13",
          status: "filled",
          direction: "buy",
          fillQuantity: 24,
          fillPrice: 72.128,
          quantity: 24,
        },
        {
          symbolValue: "NVDA",
          time: "2024-02-21",
          status: "filled",
          direction: "sell",
          fillQuantity: -35,
          fillPrice: 68.006,
          quantity: -35,
        },
        {
          symbolValue: "NVDA",
          time: "2024-02-23",
          status: "filled",
          direction: "sell",
          fillQuantity: -7,
          fillPrice: 80.79,
          quantity: -7,
        },
      ],
      "NVDA",
    );
    const marks = campaignMarkSeries(fills, [
      { date: "2024-02-21", close: 67.47 },
      { date: "2024-03-08", close: 87.53 },
    ]);
    expect(marks[0]!.totalPnl).toBeLessThan(0);
    expect(marks[1]!.totalPnl).toBeGreaterThan(0);
    expect(marks[1]!.remaining).toBe(26);
    expect(campaignHoldingSignRuns(marks).map((r) => r.positive)).toEqual([
      false,
      true,
    ]);
  });
});
