import { describe, expect, it } from "vitest";
import { normalizeSearchStrategy } from "../types";
import { evaluationExtraEnv, readEvaluation, stampEvaluation } from "./evaluationSpec";

describe("stampEvaluation", () => {
  it("writes VeraBase.Evaluation and string AlgorithmParameters for LEAN", () => {
    const out = stampEvaluation(
      {
        Kind: "VeraLabV1",
        AlgorithmParameters: { "regime-source": "screener" },
        VeraBase: { Universe: { version: 1, select: ["ticker"] } },
      },
      {
        start_date: "2024-01-02",
        end_date: "2024-06-30",
        initial_cash: 50000,
        benchmark: "qqq",
      },
    );
    expect(out.VeraBase).toMatchObject({
      Evaluation: {
        start_date: "2024-01-02",
        end_date: "2024-06-30",
        initial_cash: 50000,
        benchmark: "QQQ",
      },
    });
    expect(out.AlgorithmParameters).toMatchObject({
      "regime-source": "screener",
      "initial-cash": "50000",
      benchmark: "QQQ",
      "start-date": "2024-01-02",
      "end-date": "2024-06-30",
    });
    expect(evaluationExtraEnv(out)).toEqual({
      "initial-cash": "50000",
      benchmark: "QQQ",
    });
  });

  it("readEvaluation hydrates UI fields from a stamped spec", () => {
    const stamped = stampEvaluation(
      { VeraBase: {}, AlgorithmParameters: {} },
      { start_date: "2025-02-01", end_date: "2025-08-01", initial_cash: 25000, benchmark: "IWM" },
    );
    expect(readEvaluation(stamped)).toEqual({
      start_date: "2025-02-01",
      end_date: "2025-08-01",
      initial_cash: 25000,
      benchmark: "IWM",
    });
  });
});

describe("normalizeSearchStrategy", () => {
  it("drops genetic and unknown values onto euler", () => {
    expect(normalizeSearchStrategy("grid")).toBe("grid");
    expect(normalizeSearchStrategy("euler")).toBe("euler");
    expect(normalizeSearchStrategy("genetic")).toBe("euler");
    expect(normalizeSearchStrategy(undefined)).toBe("euler");
  });
});
