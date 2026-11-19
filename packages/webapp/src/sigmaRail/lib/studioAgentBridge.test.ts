import { describe, expect, it, vi } from "vitest";
import {
  getPathValue,
  parseFieldPath,
  setPathValue,
  studioAgentBridge,
} from "./studioAgentBridge";
import { initWebMCP, type WebMCPInstance } from "./webmcpProvider";

describe("strategy field paths", () => {
  const doc = {
    sizing: { risk_per_trade_pct: 0.008, max_positions: 10 },
    stages: [{ name: "Rank" }, { name: "Setup", where: { type: "all", items: [1, 2] } }],
  };

  it("parses dotted and bracket paths", () => {
    expect(parseFieldPath("sizing.risk_per_trade_pct")).toEqual(["sizing", "risk_per_trade_pct"]);
    expect(parseFieldPath("stages[1].where.items[0]")).toEqual(["stages", 1, "where", "items", 0]);
  });

  it("reads nested values", () => {
    expect(getPathValue(doc, "sizing.max_positions")).toBe(10);
    expect(getPathValue(doc, "stages[1].where.items[1]")).toBe(2);
    expect(getPathValue(doc, "sizing.missing")).toBeUndefined();
  });

  it("writes nested values immutably", () => {
    const next = setPathValue(doc, "sizing.risk_per_trade_pct", 0.005);
    expect(next.sizing.risk_per_trade_pct).toBe(0.005);
    expect(doc.sizing.risk_per_trade_pct).toBe(0.008);
    const next2 = setPathValue(doc, "stages[1].where.items[1]", 9);
    expect(next2.stages[1].where?.items?.[1]).toBe(9);
    expect(doc.stages[1].where?.items?.[1]).toBe(2);
  });

  it("creates intermediate objects when setting new paths", () => {
    const next = setPathValue(doc, "bindings.pcm_allow_entry.where", { type: "all" });
    expect((next as any).bindings.pcm_allow_entry.where).toEqual({ type: "all" });
  });
});

describe("StudioAgentBridge", () => {
  it("initializes with default state", () => {
    const state = studioAgentBridge.getState();
    expect(state).toBeDefined();
    expect(state.selectedTicker).toBe("UBER");
    // No default preset — an empty screen is where the screener starts.
    expect(state.preset).toBe("");
  });

  it("updates state and notifies subscribers", () => {
    const subscriber = vi.fn();
    const unsub = studioAgentBridge.subscribe(subscriber);

    studioAgentBridge.updateState({
      selectedTicker: "NVDA",
      asOf: "2026-09-15",
      activeTab: "charts",
    });

    expect(studioAgentBridge.getState().selectedTicker).toBe("NVDA");
    expect(studioAgentBridge.getState().asOf).toBe("2026-09-15");
    expect(studioAgentBridge.getState().activeTab).toBe("charts");
    expect(subscriber).toHaveBeenCalledTimes(1);

    unsub();
  });

  it("handles navigation dispatch and tool formatting", async () => {
    const navHandler = vi.fn().mockResolvedValue(true);
    const unsub = studioAgentBridge.registerAction("navigate", navHandler);

    const result = await studioAgentBridge.handleNavigate({
      route: "charts",
      ticker: "TSLA",
      as_of: "2026-09-10",
    });

    expect(navHandler).toHaveBeenCalledWith({
      route: "charts",
      ticker: "TSLA",
      as_of: "2026-09-10",
    });
    expect(result.isError).toBeUndefined();
    expect(result.content[0]?.text).toContain("Navigated to charts (ticker: TSLA) (as_of: 2026-09-10)");

    unsub();
  });

  it("handles selectSymbol and validates required parameters", async () => {
    const symbolHandler = vi.fn().mockResolvedValue(true);
    const unsub = studioAgentBridge.registerAction("selectSymbol", symbolHandler);

    // Validation error when ticker is empty
    const errResult = await studioAgentBridge.handleSelectSymbol({ ticker: "  " });
    expect(errResult.isError).toBe(true);
    expect(symbolHandler).not.toHaveBeenCalled();

    // Successful execution
    const okResult = await studioAgentBridge.handleSelectSymbol({ ticker: "aapl" });
    expect(symbolHandler).toHaveBeenCalledWith({ ticker: "AAPL", as_of: undefined });
    expect(okResult.content[0]?.text).toContain("Selected ticker AAPL");

    unsub();
  });

  it("handles setPreset action and validation", async () => {
    const presetHandler = vi.fn().mockResolvedValue(true);
    const unsub = studioAgentBridge.registerAction("setPreset", presetHandler);

    const res = await studioAgentBridge.handleSetPreset({ preset_id: "canslim" });
    expect(presetHandler).toHaveBeenCalledWith({ preset_id: "canslim" });
    expect(res.content[0]?.text).toContain('Active screener preset set to "canslim"');

    unsub();
  });

  it("handles scrubToDate action and validation", async () => {
    const scrubHandler = vi.fn().mockResolvedValue(true);
    const unsub = studioAgentBridge.registerAction("scrubToDate", scrubHandler);

    const res = await studioAgentBridge.handleScrubToDate({ date: "2026-06-01" });
    expect(scrubHandler).toHaveBeenCalledWith({ date: "2026-06-01" });
    expect(res.content[0]?.text).toContain("Backtest scrubber moved to date 2026-06-01");

    unsub();
  });

  it("reports current view, screener state, and strategy draft", () => {
    studioAgentBridge.updateState({
      activeTab: "screens",
      selectedTicker: "PLTR",
      asOf: "2026-09-18",
      preset: "minervini_tt",
      rankedRowCount: 42,
    });

    const view = studioAgentBridge.handleGetCurrentView();
    const viewJson = JSON.parse(view.content[0]!.text);
    expect(viewJson.activeTab).toBe("screens");
    expect(viewJson.selectedTicker).toBe("PLTR");
    expect(viewJson.screener.rankedRowCount).toBe(42);

    const screenerState = studioAgentBridge.handleGetScreenerState();
    const screenerJson = JSON.parse(screenerState.content[0]!.text);
    expect(screenerJson.preset).toBe("minervini_tt");
    expect(screenerJson.rankedRowCount).toBe(42);

    const draft = studioAgentBridge.handleInspectDraft();
    expect(draft.content[0]?.text).toBeDefined();
  });
});

describe("WebMCP Tool, Resource, and Prompt Registration", () => {
  it("registers 23 tools, 5 resources, and 2 prompts onto a WebMCP instance", () => {
    const tools: Record<string, any> = {};
    const resources: Record<string, any> = {};
    const prompts: Record<string, any> = {};

    const mockMcp: WebMCPInstance = {
      registerTool: vi.fn((name, desc, schema, handler) => {
        tools[name] = { desc, schema, handler };
      }),
      // Mirrors webmcp.js: keyed by resource *name*, uri lives in the options object, and
      // a registration without uri/uriTemplate is refused (the bundle logs and skips).
      registerResource: vi.fn((name, desc, options, provider) => {
        if (!options?.uri && !options?.uriTemplate) {
          throw new Error(`resource '${name}' needs uri or uriTemplate (webmcp.js refuses it)`);
        }
        resources[name] = { desc, options, provider };
      }),
      registerPrompt: vi.fn((name, desc, args, handler) => {
        prompts[name] = { desc, args, handler };
      }),
    };

    initWebMCP(mockMcp);

    // Verify tools
    expect(Object.keys(tools)).toHaveLength(23);
    expect(tools.studio_navigate).toBeDefined();
    expect(tools.studio_select_symbol).toBeDefined();
    expect(tools.studio_get_current_view).toBeDefined();
    expect(tools.screener_set_preset).toBeDefined();
    expect(tools.screener_set_template).toBeDefined();
    expect(tools.screener_get_state).toBeDefined();
    expect(tools.strategy_inspect_draft).toBeDefined();
    expect(tools.backtest_scrub_to_date).toBeDefined();
    expect(tools.strategy_get_field).toBeDefined();
    expect(tools.strategy_set_field).toBeDefined();
    expect(tools.strategy_list_fields).toBeDefined();
    expect(tools.strategy_save).toBeDefined();
    expect(tools.strategy_submit_backtest).toBeDefined();
    expect(tools.field_browser_open).toBeDefined();
    expect(tools.field_browser_get_state).toBeDefined();
    expect(tools.field_browser_apply).toBeDefined();
    expect(tools.studio_optimizer_select_session).toBeDefined();
    expect(tools.studio_optimizer_select_point).toBeDefined();
    expect(tools.studio_optimizer_launch_sweep).toBeDefined();
    expect(tools.studio_optimizer_promote_point).toBeDefined();
    expect(tools.studio_deploy_select_run).toBeDefined();
    expect(tools.studio_deploy_register_paper).toBeDefined();
    expect(tools.studio_backtest_compare_runs).toBeDefined();

    // Verify resources (keys are resource names, URIs live in the options object)
    expect(Object.keys(resources)).toHaveLength(5);
    expect(resources["current-view"]).toBeDefined();
    expect(resources["strategy-draft"]).toBeDefined();
    expect(resources["chart-quote"]).toBeDefined();
    expect(resources["screener-spec"]).toBeDefined();
    expect(resources["strategy-fields"]).toBeDefined();

    const currentViewContent = resources["current-view"].provider("studio://current-view");
    expect(currentViewContent.contents[0].mimeType).toBe("application/json");

    // Verify prompts
    expect(Object.keys(prompts)).toHaveLength(2);
    expect(prompts["audit-strategy-draft"]).toBeDefined();
    expect(prompts["summarize-active-view"]).toBeDefined();

    const auditPrompt = prompts["audit-strategy-draft"].handler({});
    expect(auditPrompt.messages[0].content.text).toContain("5 Framework Slots");
  });
});
