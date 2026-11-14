/**
 * WebMCP Provider for SigmaRail Studio
 *
 * Exposes Screening Studio capabilities to AI agents (Claude Desktop, Cursor,
 * browser extensions) via the Model Context Protocol (WebMCP / W3C navigator.modelContext).
 */

import { studioAgentBridge } from "./studioAgentBridge";

declare global {
  interface Window {
    WebMCP?: any;
    mcp?: any;
    __STUDIO_AGENT_BRIDGE__?: typeof studioAgentBridge;
  }
}

export interface WebMCPInstance {
  registerTool: (name: string, description: string, schema: any, handler: (args: any) => any) => void;
  /**
   * Matches `webmcp.js`: the third argument is an **options object**. The vendored bundle
   * rejects any registration whose options carry neither `uri` nor `uriTemplate`
   * ("Either uri or uriTemplate is required for a resource"), so passing a mimeType string
   * here silently dropped every resource — and each attempt logged a console error.
   */
  registerResource: (
    name: string,
    description: string,
    options: { uri?: string; uriTemplate?: string; mimeType?: string },
    provider: (uri: string) => any
  ) => void;
  registerPrompt: (name: string, description: string, args: any[], handler: (args: any) => any) => void;
  connect?: (token: string) => Promise<void>;
  disconnect?: () => void;
}

export function initWebMCP(customMcpInstance?: WebMCPInstance): WebMCPInstance | null {
  // Expose global debug reference for dev / Playwright attach
  if (typeof window !== "undefined") {
    window.__STUDIO_AGENT_BRIDGE__ = studioAgentBridge;
  }

  let mcp: WebMCPInstance | null = customMcpInstance ?? null;

  if (!mcp && typeof window !== "undefined") {
    if (window.mcp && typeof window.mcp.registerTool === "function") {
      mcp = window.mcp;
    } else if (typeof window.WebMCP === "function") {
      try {
        mcp = new window.WebMCP({
          color: "#2563eb",
          position: "bottom-right",
          size: "32px",
          padding: "16px",
        });
        window.mcp = mcp;
      } catch (err) {
        console.warn("Failed to instantiate WebMCP widget:", err);
      }
    }
  }

  if (!mcp) {
    return null;
  }

  registerStudioTools(mcp);
  registerStudioResources(mcp);
  registerStudioPrompts(mcp);

  // Auto-connect if token is persisted in localStorage
  if (typeof window !== "undefined") {
    const storedToken = localStorage.getItem("webmcp_token");
    if (storedToken && typeof mcp.connect === "function" && !(mcp as any).isConnected) {
      void mcp.connect(storedToken).catch((err) => {
        console.warn("Auto-connect with stored WebMCP token failed:", err);
      });
    }
  }

  return mcp;
}

export function registerStudioTools(mcp: WebMCPInstance): void {
  // Tool 1: studio_navigate
  mcp.registerTool(
    "studio_navigate",
    "Navigate to a specific section, subview, or parameterized URL in SigmaRail Studio.",
    {
      type: "object",
      properties: {
        route: {
          type: "string",
          enum: ["screens", "charts", "watchlists", "strategies", "backtests", "optimize", "deploy", "monitor", "market"],
          description: "Target view section in the workspace.",
        },
        ticker: {
          type: "string",
          description: "Optional ticker symbol (e.g. NVDA, AAPL).",
        },
        as_of: {
          type: "string",
          description: "Optional as-of date in YYYY-MM-DD format.",
        },
        run_id: {
          type: "string",
          description: "Optional backtest run UUID for /backtests/:run_id.",
        },
        section_view: {
          type: "string",
          enum: ["overview", "trades", "attribution", "scrubber"],
          description: "Optional subview when navigating to a backtest run.",
        },
      },
      required: ["route"],
    },
    async (args: any) => studioAgentBridge.handleNavigate(args)
  );

  // Tool 2: studio_select_symbol
  mcp.registerTool(
    "studio_select_symbol",
    "Select and inspect a ticker symbol in the active chart workspace (Lightweight Charts) with optional date anchor.",
    {
      type: "object",
      properties: {
        ticker: {
          type: "string",
          description: "Ticker symbol to display (e.g. TSLA, AMD, PLTR).",
        },
        as_of: {
          type: "string",
          description: "Optional as-of date (YYYY-MM-DD).",
        },
      },
      required: ["ticker"],
    },
    async (args: any) => studioAgentBridge.handleSelectSymbol(args)
  );

  // Tool 3: studio_get_current_view
  mcp.registerTool(
    "studio_get_current_view",
    "Inspect the active tab, selected symbol, as-of date, and status in the trader's live viewport.",
    {
      type: "object",
      properties: {},
    },
    async () => studioAgentBridge.handleGetCurrentView()
  );

  // Tool 4: screener_set_preset
  mcp.registerTool(
    "screener_set_preset",
    "Set the active universe screener preset (e.g. minervini_tt, canslim, ipo_breakout) and trigger live evaluation.",
    {
      type: "object",
      properties: {
        preset_id: {
          type: "string",
          description: "Preset or template identifier (e.g. 'julian_komar', 'minervini_tt').",
        },
      },
      required: ["preset_id"],
    },
    async (args: any) => studioAgentBridge.handleSetPreset(args)
  );

  // Tool 5: screener_set_template
  mcp.registerTool(
    "screener_set_template",
    "Set the active universe screener template by ID (e.g. 'julian_komar_best_winners', 'canslim_template', 'minervini_trend_template') and load its full AST filter tree.",
    {
      type: "object",
      properties: {
        template_id: {
          type: "string",
          description: "Canonical screener template identifier.",
        },
      },
      required: ["template_id"],
    },
    async (args: any) => studioAgentBridge.handleSetTemplate(args)
  );

  // Tool 6: screener_get_state
  mcp.registerTool(
    "screener_get_state",
    "Read the current universe screener configuration, preset, template ID, and count of matching stocks.",
    {
      type: "object",
      properties: {},
    },
    async () => studioAgentBridge.handleGetScreenerState()
  );

  // Tool 6: strategy_inspect_draft
  mcp.registerTool(
    "strategy_inspect_draft",
    "Inspect the in-flight, unsaved strategy pipeline and parameter draft in the Compose workstation.",
    {
      type: "object",
      properties: {},
    },
    async () => studioAgentBridge.handleInspectDraft()
  );

  // Tool 7: backtest_scrub_to_date
  mcp.registerTool(
    "backtest_scrub_to_date",
    "Jump the interactive backtest day-by-day scrubber to a specific date to inspect portfolio state and excursions.",
    {
      type: "object",
      properties: {
        date: {
          type: "string",
          description: "Date to scrub to (YYYY-MM-DD).",
        },
      },
      required: ["date"],
    },
    async (args: any) => studioAgentBridge.handleScrubToDate(args)
  );

  // Tool 8: strategy_get_field
  mcp.registerTool(
    "strategy_get_field",
    "Read one field of the live strategy draft by path (e.g. 'sizing.risk_per_trade_pct', 'stages[2].name', 'bindings.pcm_allow_entry').",
    {
      type: "object",
      properties: {
        path: { type: "string", description: "Dotted path with optional [index] segments." },
      },
      required: ["path"],
    },
    async (args: any) => studioAgentBridge.handleGetStrategyField(args)
  );

  // Tool 9: strategy_set_field
  mcp.registerTool(
    "strategy_set_field",
    "Write one field of the live strategy draft by path. Arrays are addressed with [i]. Use strategy_list_fields to discover paths.",
    {
      type: "object",
      properties: {
        path: { type: "string", description: "Dotted path with optional [index] segments." },
        value: { description: "JSON value to assign (number, string, bool, object, array, or null)." },
      },
      required: ["path", "value"],
    },
    async (args: any) => studioAgentBridge.handleSetStrategyField(args)
  );

  // Tool 10: strategy_list_fields
  mcp.registerTool(
    "strategy_list_fields",
    "Enumerate every editable field of the live strategy draft with its current value, type, human label, and description.",
    { type: "object", properties: {} },
    async () => studioAgentBridge.handleListStrategyFields()
  );

  // Tool 11: strategy_save
  mcp.registerTool(
    "strategy_save",
    "Persist the current strategy draft (creates or updates its spec in the registry).",
    { type: "object", properties: {} },
    async () => studioAgentBridge.handleSaveStrategy()
  );

  // Tool 12: strategy_submit_backtest
  mcp.registerTool(
    "strategy_submit_backtest",
    "Compose the current strategy draft and queue a LEAN backtest run. Returns the queued job id; poll /backtests for results.",
    {
      type: "object",
      properties: {
        start_date: { type: "string", description: "Optional override, YYYY-MM-DD." },
        end_date: { type: "string", description: "Optional override, YYYY-MM-DD." },
      },
    },
    async (args: any) => studioAgentBridge.handleSubmitStrategyBacktest(args ?? {})
  );

  // Tool 13: field_browser_open
  mcp.registerTool(
    "field_browser_open",
    "Open the shared expression/field browser dialog against a target slot (e.g. 'pcm.allow_entry', 'measure.eps_beat', 'risk.skip_time_stop').",
    {
      type: "object",
      properties: {
        target: { type: "string", description: "Target slot id; omit to re-open the last target." },
        mode: { type: "string", description: "Optional editor mode hint (bool_expr, number_expr, field)." },
      },
    },
    async (args: any) => studioAgentBridge.handleFieldBrowserOpen(args ?? {})
  );

  // Tool 14: field_browser_get_state
  mcp.registerTool(
    "field_browser_get_state",
    "Inspect the shared expression/field browser dialog: open state, target slot, current expression, and available field catalog.",
    { type: "object", properties: {} },
    async () => studioAgentBridge.handleFieldBrowserState()
  );

  // Tool 15: field_browser_apply
  mcp.registerTool(
    "field_browser_apply",
    "Apply an expression AST (or field reference) to the currently open field-browser target and close the dialog.",
    {
      type: "object",
      properties: {
        expr: { description: "Expression AST / field reference JSON for the target slot." },
      },
      required: ["expr"],
    },
    async (args: any) => studioAgentBridge.handleFieldBrowserApply(args)
  );

  // Tool 16: studio_optimizer_select_session (Component 3)
  mcp.registerTool(
    "studio_optimizer_select_session",
    "Select an active hyperparameter sweep session in the Optimizer workbench.",
    {
      type: "object",
      properties: {
        session_id: { type: "string", description: "Optimizer session id (e.g. opt-abc123)." },
      },
      required: ["session_id"],
    },
    async (args: any) => studioAgentBridge.handleOptimizerSelectSession(args)
  );

  // Tool 17: studio_optimizer_select_point (Component 3)
  mcp.registerTool(
    "studio_optimizer_select_point",
    "Select a response-surface point (sweep run) in the Optimizer inspector.",
    {
      type: "object",
      properties: {
        run_id: { type: "string", description: "Sweep run id to inspect." },
      },
      required: ["run_id"],
    },
    async (args: any) => studioAgentBridge.handleOptimizerSelectPoint(args)
  );

  // Tool 18: studio_optimizer_launch_sweep (Component 3)
  mcp.registerTool(
    "studio_optimizer_launch_sweep",
    "Launch a 1D or 2D hyperparameter sweep from a base strategy spec.",
    {
      type: "object",
      properties: {
        base_ir_id: { type: "string", description: "Base strategy IR id." },
        param_x_name: { type: "string", description: "Primary parameter name (e.g. risk_per_trade_pct)." },
        param_x_values: { type: "array", items: { type: "number" }, description: "Primary parameter values." },
        param_y_name: { type: "string", description: "Optional secondary parameter name." },
        param_y_values: { type: "array", items: { type: "number" }, description: "Optional secondary parameter values." },
        strategy_type: { type: "string", description: "euler (default) or grid." },
      },
      required: ["base_ir_id", "param_x_name", "param_x_values"],
    },
    async (args: any) => studioAgentBridge.handleOptimizerLaunchSweep(args)
  );

  // Tool 19: studio_optimizer_promote_point (Component 3)
  mcp.registerTool(
    "studio_optimizer_promote_point",
    "Promote a sweep winner to a new strategy spec version (sweep_promotion lineage).",
    {
      type: "object",
      properties: {
        run_id: { type: "string", description: "Winning sweep run id." },
        new_ir_id: { type: "string", description: "New spec IR id." },
        new_title: { type: "string", description: "New spec title." },
        changelog: { type: "string", description: "Optional changelog notes." },
      },
      required: ["run_id", "new_ir_id", "new_title"],
    },
    async (args: any) => studioAgentBridge.handleOptimizerPromotePoint(args)
  );

  // Tool 20: studio_deploy_select_run (Component 3)
  mcp.registerTool(
    "studio_deploy_select_run",
    "Select a backtest run for paper promotion in the Deploy panel.",
    {
      type: "object",
      properties: {
        run_id: { type: "string", description: "Backtest run id." },
      },
      required: ["run_id"],
    },
    async (args: any) => studioAgentBridge.handleDeploySelectRun(args)
  );

  // Tool 21: studio_deploy_register_paper (Component 3)
  mcp.registerTool(
    "studio_deploy_register_paper",
    "Register the selected run as a paper deployment (gate-then-INSERT into live_deployments).",
    {
      type: "object",
      properties: {
        ir_id: { type: "string", description: "Strategy IR id (omit to use the selected run's)." },
        run_id: { type: "string", description: "Backtest run id (omit to use the selected run)." },
      },
    },
    async (args: any) => studioAgentBridge.handleDeployRegisterPaper(args ?? {})
  );

  // Tool 22: studio_backtest_compare_runs (Component 3)
  mcp.registerTool(
    "studio_backtest_compare_runs",
    "Compare two or more backtest runs side-by-side in the multi-run compare view.",
    {
      type: "object",
      properties: {
        run_ids: { type: "array", items: { type: "string" }, description: "Run ids to compare." },
      },
      required: ["run_ids"],
    },
    async (args: any) => studioAgentBridge.handleBacktestCompareRuns(args)
  );
}

export function registerStudioResources(mcp: WebMCPInstance): void {
  // Resource 1: studio://current-view
  mcp.registerResource(
    "current-view",
    "Current viewport status of SigmaRail Studio (active tab, selected ticker, date, screener mode).",
    { uri: "studio://current-view", mimeType: "application/json" },
    () => {
      const view = studioAgentBridge.handleGetCurrentView();
      return {
        contents: [
          {
            uri: "studio://current-view",
            text: view.content[0]?.text ?? "{}",
            mimeType: "application/json",
          },
        ],
      };
    }
  );

  // Resource 2: studio://strategy/draft
  mcp.registerResource(
    "strategy-draft",
    "The in-memory unsaved strategy prefill / pipeline spec in the composer.",
    { uri: "studio://strategy/draft", mimeType: "application/json" },
    () => {
      const draft = studioAgentBridge.handleInspectDraft();
      return {
        contents: [
          {
            uri: "studio://strategy/draft",
            text: draft.content[0]?.text ?? "{}",
            mimeType: "application/json",
          },
        ],
      };
    }
  );

  // Resource 3: studio://chart/quote
  mcp.registerResource(
    "chart-quote",
    "Active chart symbol and as-of date.",
    { uri: "studio://chart/quote", mimeType: "application/json" },
    () => {
      const s = studioAgentBridge.getState();
      return {
        contents: [
          {
            uri: "studio://chart/quote",
            text: JSON.stringify({ ticker: s.selectedTicker, asOf: s.asOf }, null, 2),
            mimeType: "application/json",
          },
        ],
      };
    }
  );

  // Resource 4: studio://screener/spec
  mcp.registerResource(
    "screener-spec",
    "Current active universe query AST specification (UniverseQueryV1) in the screener workspace.",
    { uri: "studio://screener/spec", mimeType: "application/json" },
    () => {
      const s = studioAgentBridge.getState();
      return {
        contents: [
          {
            uri: "studio://screener/spec",
            text: JSON.stringify(s.liveSpec ?? {}, null, 2),
            mimeType: "application/json",
          },
        ],
      };
    }
  );

  // Resource 5: studio://strategy/fields
  mcp.registerResource(
    "strategy-fields",
    "Live strategy draft field catalog: every editable path with current value, type, label, and description.",
    { uri: "studio://strategy/fields", mimeType: "application/json" },
    () => {
      const s = studioAgentBridge.getState();
      const body = {
        ir_id: s.strategyIrId,
        dirty: s.dirty,
        doc: s.strategyDoc,
        field_browser: s.fieldBrowser,
      };
      return {
        contents: [
          {
            uri: "studio://strategy/fields",
            text: JSON.stringify(body, null, 2),
            mimeType: "application/json",
          },
        ],
      };
    }
  );
}

export function registerStudioPrompts(mcp: WebMCPInstance): void {
  // Prompt 1: audit-strategy-draft
  mcp.registerPrompt(
    "audit-strategy-draft",
    "Audit the in-memory strategy draft against the Five Lean slots, Alpha measure bindings, and risk sizing rules.",
    [],
    () => {
      const state = studioAgentBridge.getState();
      const draftJson = JSON.stringify(state.backtestPrefill ?? state.liveSpec ?? {}, null, 2);
      return {
        messages: [
          {
            role: "user",
            content: {
              type: "text",
              text: `Please audit this Vera strategy draft against the platform design guidelines:\n\n` +
                `- 5 Framework Slots: Universe, Alpha, PCM, Risk, Execution\n` +
                `- Alpha rules: Measures for math/ranking; Insights for property lookup only; no stock QC type pickers\n` +
                `- PCM rules: RiskBudgeted sizing, scale-in, regime thermostat\n` +
                `- Risk rules: Exits and stop management (no Alpha exit blocks)\n\n` +
                `Current Draft:\n\`\`\`json\n${draftJson}\n\`\`\``,
            },
          },
        ],
      };
    }
  );

  // Prompt 2: summarize-active-view
  mcp.registerPrompt(
    "summarize-active-view",
    "Summarize what the trader is currently looking at in Screening Studio.",
    [],
    () => {
      const s = studioAgentBridge.getState();
      return {
        messages: [
          {
            role: "user",
            content: {
              type: "text",
              text: `Summarize the trader's current workspace state in SigmaRail Studio:\n` +
                `- Active Tab: ${s.activeTab}\n` +
                `- Selected Ticker: ${s.selectedTicker}\n` +
                `- As-of Date: ${s.asOf}\n` +
                `- Screener Preset: ${s.preset} (Matches: ${s.rankedRowCount})\n` +
                `- Strategy Draft: ${s.backtestPrefill ? s.backtestPrefill.title : "None"} (Dirty: ${s.dirty})\n`,
            },
          },
        ],
      };
    }
  );
}
