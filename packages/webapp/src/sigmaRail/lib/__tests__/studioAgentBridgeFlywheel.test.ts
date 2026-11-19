// Component 4 Tier 2: bridge registration lifecycle + optimizer/deploy state sync.
import { describe, expect, it } from "vitest";
import { studioAgentBridge, getPathValue, setPathValue } from "../studioAgentBridge";

describe("Component 3 action lifecycle (optimizer/deploy)", () => {
  it("registers and unregisters optimizer actions without zombies", () => {
    expect(studioAgentBridge.hasAction("optimizerSelectSession")).toBe(false);
    const unreg = studioAgentBridge.registerAction("optimizerSelectSession", () => ({}));
    expect(studioAgentBridge.hasAction("optimizerSelectSession")).toBe(true);
    unreg();
    expect(studioAgentBridge.hasAction("optimizerSelectSession")).toBe(false);
  });

  it("syncs optimizer selection state", () => {
    studioAgentBridge.updateState({
      activeOptimizerSessionId: "opt-test",
      selectedOptimizerPoint: { run_id: "run-1" },
    });
    const s = studioAgentBridge.getState();
    expect(s.activeOptimizerSessionId).toBe("opt-test");
    expect(s.selectedOptimizerPoint).toEqual({ run_id: "run-1" });
  });

  it("syncs deploy gate state", () => {
    studioAgentBridge.updateState({
      selectedDeploymentId: "dep-1",
      promotionGateStatus: { ok: true },
    });
    const s = studioAgentBridge.getState();
    expect(s.selectedDeploymentId).toBe("dep-1");
    expect(s.promotionGateStatus).toEqual({ ok: true });
  });

  it("dispatches registered optimizer handlers and returns payloads", async () => {
    const unreg = studioAgentBridge.registerAction("optimizerSelectPoint", ({ run_id }: any) => ({
      selected_run_id: run_id,
    }));
    const res = await studioAgentBridge
      .handleOptimizerSelectPoint({ run_id: "run-xyz" })
      .then((r) => JSON.parse(r.content[0].text));
    expect(res).toEqual({ selected_run_id: "run-xyz" });
    unreg();
  });

  it("deep path mutations stay immutable", () => {
    const doc = { stages: [{ where: { items: [{ val: 1 }] } }] };
    const next = setPathValue(doc, "stages[0].where.items[0].val", 2);
    expect(getPathValue(next, "stages[0].where.items[0].val")).toBe(2);
    expect(getPathValue(doc, "stages[0].where.items[0].val")).toBe(1);
  });
});
