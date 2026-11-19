import { describe, expect, it } from "vitest";
import type { PipelineDocument } from "../components/strategy/StrategyDocument";
import {
  ALPHA_ADD_MODES,
  CHAMPION_EXIT_TRANCHES,
  fillSessionFromDoc,
  patchFillSession,
  pcmFromDoc,
  patchPcm,
  patchProgressive,
  patchStopCooldown,
  pinChampionGateRanking,
  pinChampionPipeline,
  pinDailyMarketExecution,
  progressiveFromDoc,
  stopCooldownFromDoc,
  scoreRankingEditorsHidden,
  exitRulesFromDoc,
  patchExitRules,
} from "./pipelineSlotBindings";

const base: PipelineDocument = {
  strategy_name: "Test",
  stages: [
    { name: "Rank", mode: "score", as_gate: true, filters: [] },
    {
      name: "Progressive Exposure",
      mode: "pyramid",
      phases: [{ name: "test", size_pct: 0.5 }],
    },
  ],
  sizing: { policy: "atr_risk", max_positions: 8 },
  risk: { max_positions: 8 },
  execution: { type: "vwap" },
};

describe("pipelineSlotBindings", () => {
  it("only allows score/signal/pyramid on the Alpha add-stage menu", () => {
    expect([...ALPHA_ADD_MODES]).toEqual(["score", "signal", "pyramid"]);
  });

  it("defaults Champion 0.5% / 25% when sizing is missing", () => {
    expect(pcmFromDoc({ strategy_name: "x", stages: [] })).toEqual({
      riskPerTrade: 0.005,
      maxWeight: 0.25,
      maxPositions: 10,
      honorInsightConfidence: true,
      allowAddsOnInvested: true,
      defaultStopLossPct: 0.08,
      rebalance: 'weekly',
      minRegimeFraction: 0.15,
      regimeNeutralFraction: 0.5,
      regimeBullFraction: 1.0,
      scaledMaxPositionsFloor: 2,
      enableSurrogates: false,
      surrogateSizingMode: "dollar_risk_parity",
      preferCapitalEfficientSurrogates: true,
      minSurrogateAdv: 5000000,
    });
  });

  it("patches regime fractions and floor onto sizing", () => {
    const next = patchPcm(base, {
      regimeNeutralFraction: 0.67,
      regimeBullFraction: 1.0,
      scaledMaxPositionsFloor: 0,
    });
    expect(next.sizing?.regime_neutral_fraction).toBe(0.67);
    expect(next.sizing?.regime_bull_fraction).toBe(1.0);
    expect(next.sizing?.scaled_max_positions_floor).toBe(0);
    expect(pcmFromDoc(next).regimeNeutralFraction).toBe(0.67);
  });

  it("edits stop cooldown through the signal stage from the Risk card", () => {
    const withSignal = {
      ...base,
      stages: [...base.stages, { name: "Setup", mode: "signal" as const }],
    };
    expect(stopCooldownFromDoc(withSignal)).toBe(10);
    const next = patchStopCooldown(withSignal, 7);
    expect(next.stages.find((s) => s.mode === "signal")?.stop_cooldown_days).toBe(7);
    expect(stopCooldownFromDoc(next)).toBe(7);
  });

  it("patches PCM onto risk_budgeted sizing and pins daily market fill", () => {
    const next = patchPcm(base, { riskPerTrade: 0.005, maxWeight: 0.25, maxPositions: 10 });
    expect(next.sizing?.policy).toBe("risk_budgeted");
    expect(pcmFromDoc(next).riskPerTrade).toBe(0.005);
    expect(pcmFromDoc(next).maxWeight).toBe(0.25);
    expect(pcmFromDoc(next).maxPositions).toBe(10);
    expect(next.sizing?.honor_insight_confidence).toBe(true);
    expect(next.execution?.type).toBe("market_order");
    expect(next.risk?.max_positions).toBe(10);
  });

  it("writes Champion T1/T2/T3 onto an exit stage the compiler already maps", () => {
    const next = patchProgressive(base, {
      tranches: CHAMPION_EXIT_TRANCHES,
      trailingStopPct: 0.15,
      maxHoldDays: 63,
    });
    const exit = next.stages.find((s) => s.mode === "exit");
    expect(exit?.tranches).toEqual(CHAMPION_EXIT_TRANCHES);
    expect(exit?.trailing_stop_pct).toBe(0.15);
    expect(exit?.max_hold_days).toBe(63);
    expect(progressiveFromDoc(next).tranches[0]?.sell_pct).toBe(0.2);
    expect(next.execution?.type).toBe("market_order");
  });

  it("pins VWAP authored execution to daily market fill", () => {
    expect(pinDailyMarketExecution(base).execution?.type).toBe("market_order");
  });

  it("pins Champion pipeline to moo fill_session", () => {
    const next = pinChampionPipeline({ ...base, execution: { type: "vwap", fill_session: "moc" } });
    expect(next.execution?.type).toBe("market_order");
    expect(next.execution?.fill_session).toBe("moo");
  });

  it("round-trips fill_session without collapsing moc to moo on PCM patch", () => {
    const moc = patchFillSession(base, "moc");
    expect(fillSessionFromDoc(moc)).toBe("moc");
    const afterPcm = patchPcm(moc, { maxPositions: 12 });
    expect(fillSessionFromDoc(afterPcm)).toBe("moc");
  });

  it("hides Score ranking editors when gate_combine is count", () => {
    expect(scoreRankingEditorsHidden("count")).toBe(true);
    expect(scoreRankingEditorsHidden("union")).toBe(false);
    expect(scoreRankingEditorsHidden(undefined)).toBe(false);
  });

  it("Champion exit defaults omit stop_ratchet", () => {
    expect(CHAMPION_EXIT_TRANCHES.every((t) => t.stop_ratchet == null)).toBe(true);
  });

  it("stamps live Risk ATR / time-stop knobs onto the exit stage", () => {
    const next = patchProgressive(base, {
      atrStopMultiplier: 2.5,
      maxStopLossPct: 0.06,
      useAtrStops: true,
      breakevenTimeStopDays: 8,
      maxSingleWeight: 0.18,
      breakevenRTrigger: 1.25,
    });
    const exit = next.stages.find((s) => s.mode === "exit");
    expect(exit?.atr_stop_multiplier).toBe(2.5);
    expect(exit?.max_stop_loss_pct).toBe(0.06);
    expect(exit?.use_atr_stops).toBe(true);
    expect(exit?.breakeven_time_stop_days).toBe(8);
    expect(exit?.max_single_weight).toBe(0.18);
    expect(exit?.breakeven_r_trigger).toBe(1.25);
  });

  it("pins union gate_combine to Champion count ranking", () => {
    const next = pinChampionGateRanking({ ...base, gate_combine: "union", min_screens: 2 });
    expect(next.gate_combine).toBe("count");
    expect(next.min_screens).toBe(2);
    expect(pinChampionGateRanking(base).min_screens).toBe(1);
  });

  it("round-trips exit-stage rules and survives progressive knob edits", () => {
    const rules = [
      {
        name: "time_stop_partial",
        priority: 10,
        once: false,
        when: {
          type: "all",
          items: [
            { type: "gte", left: { type: "col", name: "__position.days_held" }, right: { type: "lit", value: 10 } },
          ],
        },
        then: [{ type: "trim", fraction: 0.5 }],
        tag: "time_stop",
      },
    ];
    const withRules = patchExitRules(base, rules as never);
    expect(exitRulesFromDoc(withRules)).toHaveLength(1);
    expect(exitRulesFromDoc(withRules)[0]?.name).toBe("time_stop_partial");
    // progressive knob edits must not clobber the rules
    const after = patchProgressive(withRules, { maxHoldDays: 40 });
    expect(exitRulesFromDoc(after)).toHaveLength(1);
    expect(after.stages.find((s) => s.mode === "exit")?.max_hold_days).toBe(40);
    // rules only ever land on the exit stage
    expect(withRules.stages.filter((s) => (s.rules?.length ?? 0) > 0)).toHaveLength(1);
    expect(withRules.stages.find((s) => (s.rules?.length ?? 0) > 0)?.mode).toBe("exit");
  });
});
