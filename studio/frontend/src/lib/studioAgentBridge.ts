/**
 * StudioAgentBridge — Central Action Registry & State Observer for AI Agents
 *
 * Exposes a structured, transport-agnostic interface allowing AI agents (via WebMCP,
 * W3C navigator.modelContext, or local dev WebSocket relays) to inspect and drive
 * the live in-browser SigmaRail Studio workstation.
 */

import type { BacktestPrefill, UniverseQueryV1, WorkbenchTab } from "../types";

export interface FieldBrowserBridgeState {
  open: boolean;
  /** Where the picked expression will be applied, e.g. "pcm.allow_entry" or "measure.eps_beat". */
  target: string | null;
  mode: string | null;
  /** Currently authored expression AST at the target (JSON-serializable). */
  current: unknown;
  /** Available field catalog shown inside the dialog. */
  fields: unknown;
}

export interface StudioAgentState {
  activeTab: WorkbenchTab | "screens" | "charts" | "watchlists" | "market" | "strategies" | "backtests" | "optimize" | "deploy" | "monitor";
  selectedTicker: string;
  asOf: string;
  preset: string;
  templateId: string | null;
  savedScreenId: number | string | null;
  rankedRowCount: number;
  dirty: boolean;
  backtestPrefill: BacktestPrefill | null;
  liveSpec: UniverseQueryV1 | null;
  /** Live PipelineDocument being edited in the Strategies composer. */
  strategyDoc: Record<string, unknown> | null;
  strategyIrId: string | null;
  /** Expression picker (FieldBrowserModal) shared UI state. */
  fieldBrowser: FieldBrowserBridgeState | null;

  // Component 3: optimizer / backtest / deploy subsystem states
  activeOptimizerSessionId: string | null;
  selectedOptimizerPoint: unknown | null;
  activeBacktestFilters: Record<string, unknown>;
  selectedCompareRunIds: string[];
  selectedDeploymentId: string | null;
  promotionGateStatus: unknown | null;
}

export interface ToolResult {
  content: Array<{
    type: "text" | "json";
    text: string;
  }>;
  isError?: boolean;
}

export type ActionHandler<TArgs = any, TResult = any> = (args: TArgs) => Promise<TResult> | TResult;

/** Parse "sizing.risk_per_trade_pct" / "stages[3].where.items[0]" into tokens. */
export function parseFieldPath(path: string): (string | number)[] {
  const tokens: (string | number)[] = [];
  for (const part of String(path || "").split(".")) {
    const m = part.match(/^([^\[\]]*)((\[\d+\])*)$/);
    if (!m) throw new Error(`Invalid path segment "${part}" in "${path}"`);
    if (m[1]) tokens.push(m[1]);
    const idx = m[2] || "";
    for (const im of idx.matchAll(/\[(\d+)\]/g)) {
      tokens.push(parseInt(im[1], 10));
    }
  }
  if (tokens.length === 0) throw new Error("Empty path");
  return tokens;
}

export function getPathValue(doc: unknown, path: string): unknown {
  let cur: unknown = doc;
  for (const tok of parseFieldPath(path)) {
    if (cur == null) return undefined;
    cur = (cur as Record<string | number, unknown>)[tok];
  }
  return cur;
}

/** Immutable deep set; returns a new root object. */
export function setPathValue<T>(doc: T, path: string, value: unknown): T {
  const tokens = parseFieldPath(path);
  const assign = (node: unknown, i: number): unknown => {
    if (i === tokens.length) return value;
    const tok = tokens[i];
    if (typeof tok === "number") {
      const arr = Array.isArray(node) ? [...node] : [];
      arr[tok] = assign(arr[tok], i + 1);
      return arr;
    }
    const obj = node && typeof node === "object" ? { ...(node as Record<string, unknown>) } : {};
    obj[tok as string] = assign((node as Record<string, unknown>)?.[tok as string], i + 1);
    return obj;
  };
  return assign(doc, 0) as T;
}

export class StudioAgentBridgeRegistry {
  private state: StudioAgentState = {
    activeTab: "screens",
    selectedTicker: "UBER",
    asOf: "",
    preset: "", // no default preset: the screener starts with no conditions (see App NO_PRESET)
    templateId: null,
    savedScreenId: null,
    rankedRowCount: 0,
    dirty: false,
    backtestPrefill: null,
    liveSpec: null,
    strategyDoc: null,
    strategyIrId: null,
    fieldBrowser: null,
    activeOptimizerSessionId: null,
    selectedOptimizerPoint: null,
    activeBacktestFilters: {},
    selectedCompareRunIds: [],
    selectedDeploymentId: null,
    promotionGateStatus: null,
  };

  private handlers = new Map<string, ActionHandler>();
  private stateSubscribers = new Set<(state: StudioAgentState) => void>();

  /**
   * Update the internal snapshot of current UI state.
   */
  public updateState(patch: Partial<StudioAgentState>): void {
    this.state = { ...this.state, ...patch };
    for (const sub of this.stateSubscribers) {
      try {
        sub(this.state);
      } catch (err) {
        console.error("Error in state subscriber:", err);
      }
    }
  }

  /**
   * Read current UI state snapshot.
   */
  public getState(): Readonly<StudioAgentState> {
    return this.state;
  }

  /**
   * Subscribe to UI state changes.
   */
  public subscribe(cb: (state: StudioAgentState) => void): () => void {
    this.stateSubscribers.add(cb);
    return () => {
      this.stateSubscribers.delete(cb);
    };
  }

  /**
   * Register an action handler bound to active React components.
   */
  public registerAction(name: string, handler: ActionHandler): () => void {
    this.handlers.set(name, handler);
    return () => {
      if (this.handlers.get(name) === handler) {
        this.handlers.delete(name);
      }
    };
  }

  /**
   * Check if an action handler is currently registered.
   */
  public hasAction(name: string): boolean {
    return this.handlers.has(name);
  }

  /**
   * Dispatch an action by name with arguments.
   */
  public async dispatch<TArgs = any, TResult = any>(name: string, args: TArgs): Promise<TResult> {
    const handler = this.handlers.get(name);
    if (!handler) {
      throw new Error(`Action "${name}" is not currently available or registered in the active UI.`);
    }
    return await handler(args);
  }

  // --- Convenience Tool Dispatches with MCP Result Formatting ---

  public async handleNavigate(args: {
    route: string;
    ticker?: string;
    as_of?: string;
    run_id?: string;
    section_view?: string;
  }): Promise<ToolResult> {
    try {
      await this.dispatch("navigate", args);
      return {
        content: [
          {
            type: "text",
            text: `Navigated to ${args.route}${args.ticker ? ` (ticker: ${args.ticker})` : ""}${
              args.as_of ? ` (as_of: ${args.as_of})` : ""
            }${args.run_id ? ` (run_id: ${args.run_id})` : ""}.`,
          },
        ],
      };
    } catch (err: any) {
      return {
        isError: true,
        content: [{ type: "text", text: `Navigation failed: ${err.message || String(err)}` }],
      };
    }
  }

  public async handleSelectSymbol(args: { ticker: string; as_of?: string }): Promise<ToolResult> {
    try {
      const ticker = (args.ticker || "").trim().toUpperCase();
      if (!ticker) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'ticker'." }] };
      }
      await this.dispatch("selectSymbol", { ticker, as_of: args.as_of });
      return {
        content: [
          {
            type: "text",
            text: `Selected ticker ${ticker} in active workstation${args.as_of ? ` (as_of: ${args.as_of})` : ""}.`,
          },
        ],
      };
    } catch (err: any) {
      return {
        isError: true,
        content: [{ type: "text", text: `Failed to select symbol: ${err.message || String(err)}` }],
      };
    }
  }

  public async handleSetPreset(args: { preset_id: string }): Promise<ToolResult> {
    try {
      const presetId = (args.preset_id || "").trim();
      if (!presetId) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'preset_id'." }] };
      }
      await this.dispatch("setPreset", { preset_id: presetId });
      return {
        content: [
          {
            type: "text",
            text: `Active screener preset set to "${presetId}".`,
          },
        ],
      };
    } catch (err: any) {
      return {
        isError: true,
        content: [{ type: "text", text: `Failed to set preset: ${err.message || String(err)}` }],
      };
    }
  }

  public async handleSetTemplate(args: { template_id: string }): Promise<ToolResult> {
    try {
      const templateId = (args.template_id || "").trim();
      if (!templateId) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'template_id'." }] };
      }
      await this.dispatch("setTemplate", { template_id: templateId });
      return {
        content: [
          {
            type: "text",
            text: `Active screener template set to "${templateId}".`,
          },
        ],
      };
    } catch (err: any) {
      return {
        isError: true,
        content: [{ type: "text", text: `Failed to set template: ${err.message || String(err)}` }],
      };
    }
  }

  public handleGetCurrentView(): ToolResult {
    const s = this.getState();
    const summary = {
      activeTab: s.activeTab,
      selectedTicker: s.selectedTicker,
      asOf: s.asOf,
      screener: {
        preset: s.preset,
        templateId: s.templateId,
        savedScreenId: s.savedScreenId,
        rankedRowCount: s.rankedRowCount,
      },
      strategy: {
        hasDraft: Boolean(s.backtestPrefill || s.liveSpec),
        dirty: s.dirty,
        title: s.backtestPrefill?.title ?? "Untitled",
      },
    };
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(summary, null, 2),
        },
      ],
    };
  }

  public handleGetScreenerState(): ToolResult {
    const s = this.getState();
    const info = {
      preset: s.preset,
      templateId: s.templateId,
      savedScreenId: s.savedScreenId,
      asOf: s.asOf,
      rankedRowCount: s.rankedRowCount,
      isCustomIr: Boolean(s.liveSpec),
      spec: s.liveSpec ?? null,
    };
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(info, null, 2),
        },
      ],
    };
  }

  public handleInspectDraft(): ToolResult {
    const s = this.getState();
    const draft = {
      strategy_ir_id: s.strategyIrId,
      strategy_doc: s.strategyDoc,
      dirty: s.dirty,
      backtestPrefill: s.backtestPrefill,
      liveSpec: s.liveSpec,
    };
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(draft, null, 2),
        },
      ],
    };
  }

  public handleGetStrategyField(args: { path: string }): ToolResult {
    const s = this.getState();
    if (!s.strategyDoc) {
      return { isError: true, content: [{ type: "text", text: "No strategy draft is open." }] };
    }
    try {
      const value = getPathValue(s.strategyDoc, args.path);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ path: args.path, value: value ?? null }, null, 2),
          },
        ],
      };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleSetStrategyField(args: { path: string; value: unknown }): Promise<ToolResult> {
    try {
      await this.dispatch("setStrategyField", { path: args.path, value: args.value });
      const s = this.getState();
      const now = s.strategyDoc ? getPathValue(s.strategyDoc, args.path) : undefined;
      return {
        content: [
          {
            type: "text",
            text: `Set ${args.path} = ${JSON.stringify(now ?? null)} (strategy draft updated).`,
          },
        ],
      };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleListStrategyFields(): Promise<ToolResult> {
    try {
      const catalog = await this.dispatch("listStrategyFields", {});
      return {
        content: [{ type: "text", text: JSON.stringify(catalog, null, 2) }],
      };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleSaveStrategy(): Promise<ToolResult> {
    try {
      const saved = await this.dispatch("saveStrategy", {});
      return {
        content: [{ type: "text", text: JSON.stringify(saved ?? { saved: true }, null, 2) }],
      };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: `Save failed: ${err.message || String(err)}` }] };
    }
  }

  public async handleSubmitStrategyBacktest(args: {
    start_date?: string;
    end_date?: string;
  }): Promise<ToolResult> {
    try {
      const res = await this.dispatch("submitStrategyBacktest", {
        start_date: args.start_date,
        end_date: args.end_date,
      });
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: `Submit failed: ${err.message || String(err)}` }] };
    }
  }

  public async handleFieldBrowserOpen(args: {
    target?: string;
    mode?: string;
  }): Promise<ToolResult> {
    try {
      const res = await this.dispatch("fieldBrowserOpen", { target: args.target, mode: args.mode });
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public handleFieldBrowserState(): ToolResult {
    const s = this.getState();
    return {
      content: [
        { type: "text", text: JSON.stringify(s.fieldBrowser ?? { open: false, target: null, mode: null, current: null, fields: [] }, null, 2) },
      ],
    };
  }

  public async handleFieldBrowserApply(args: { expr: unknown }): Promise<ToolResult> {
    try {
      const res = await this.dispatch("fieldBrowserApply", { expr: args.expr });
      return { content: [{ type: "text", text: JSON.stringify(res ?? { applied: true }, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleScrubToDate(args: { date: string }): Promise<ToolResult> {
    try {
      const date = (args.date || "").trim();
      if (!date) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'date'." }] };
      }
      await this.dispatch("scrubToDate", { date });
      return {
        content: [
          {
            type: "text",
            text: `Backtest scrubber moved to date ${date}.`,
          },
        ],
      };
    } catch (err: any) {
      return {
        isError: true,
        content: [{ type: "text", text: `Failed to scrub to date: ${err.message || String(err)}` }],
      };
    }
  }

  // --- Component 3: optimizer / deploy / compare handlers (plan §Component 3) ---

  public async handleOptimizerSelectSession(args: { session_id: string }): Promise<ToolResult> {
    try {
      const sessionId = (args.session_id || "").trim();
      if (!sessionId) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'session_id'." }] };
      }
      const res = (await this.dispatch("optimizerSelectSession", { session_id: sessionId })) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res ?? { selected_session_id: sessionId }, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleOptimizerSelectPoint(args: { run_id: string }): Promise<ToolResult> {
    try {
      const runId = (args.run_id || "").trim();
      if (!runId) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'run_id'." }] };
      }
      const res = (await this.dispatch("optimizerSelectPoint", { run_id: runId })) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res ?? { selected_run_id: runId }, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleOptimizerLaunchSweep(args: {
    base_ir_id: string;
    param_x_name: string;
    param_x_values: number[];
    param_y_name?: string;
    param_y_values?: number[];
    strategy_type?: string;
  }): Promise<ToolResult> {
    try {
      if (!args.base_ir_id?.trim() || !args.param_x_name?.trim() || !Array.isArray(args.param_x_values)) {
        return { isError: true, content: [{ type: "text", text: "Required: base_ir_id, param_x_name, param_x_values." }] };
      }
      const res = (await this.dispatch("optimizerLaunchSweep", args)) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleOptimizerPromotePoint(args: {
    run_id: string;
    new_ir_id: string;
    new_title: string;
    changelog?: string;
  }): Promise<ToolResult> {
    try {
      if (!args.run_id?.trim() || !args.new_ir_id?.trim()) {
        return { isError: true, content: [{ type: "text", text: "Required: run_id, new_ir_id." }] };
      }
      const res = (await this.dispatch("optimizerPromotePoint", args)) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleDeploySelectRun(args: { run_id: string }): Promise<ToolResult> {
    try {
      const runId = (args.run_id || "").trim();
      if (!runId) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'run_id'." }] };
      }
      const res = (await this.dispatch("deploySelectRun", { run_id: runId })) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res ?? { selected_run_id: runId }, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleDeployRegisterPaper(args: { ir_id?: string; run_id?: string }): Promise<ToolResult> {
    try {
      const res = (await this.dispatch("deployRegisterPaper", args ?? {})) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }

  public async handleBacktestCompareRuns(args: { run_ids: string[] }): Promise<ToolResult> {
    try {
      if (!Array.isArray(args.run_ids) || args.run_ids.length === 0) {
        return { isError: true, content: [{ type: "text", text: "Missing required argument 'run_ids' (non-empty array)." }] };
      }
      const res = (await this.dispatch("backtestCompareRuns", { run_ids: args.run_ids })) as unknown;
      return { content: [{ type: "text", text: JSON.stringify(res, null, 2) }] };
    } catch (err: any) {
      return { isError: true, content: [{ type: "text", text: err.message || String(err) }] };
    }
  }
}

export const studioAgentBridge = new StudioAgentBridgeRegistry();
