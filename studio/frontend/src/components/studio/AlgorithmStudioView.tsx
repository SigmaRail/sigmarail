import { backtestRunPath, STRATEGY_SLOTS, strategySlotFromSearch } from "../../routes";
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { UniverseSlotCard, type UniverseChoice } from "./UniverseSlotCard";
import { PcmSlotCard } from "./PcmSlotCard";
import { RiskSlotCard } from "./RiskSlotCard";
import { upsertPolicyRuleForBinding } from "./PolicyRulesPanel";
import { ExecutionSlotCard } from "./ExecutionSlotCard";
import { studioAgentBridge, setPathValue } from "../../lib/studioAgentBridge";
import {
  EvaluationSettingsPanel,
  INITIAL_EVALUATION_CONFIG,
} from "./EvaluationSettingsPanel";
import { CopyIdBadge } from "../CopyIdBadge";
import { StrategyEditorView } from "../strategy/StrategyEditorView";
import type { PipelineDocument, SlotExpr } from "../strategy/StrategyDocument";
import { irToFilterTrees, normalizeDocumentScreen } from "../../lib/filterTreeChips";
import { decompilePipeline } from "../../api/strategy";
import { ForkStrategyVersionModal } from "./ForkStrategyVersionModal";
import { StrategyDocumentationBanner } from "./StrategyDocumentationBanner";
import { cn } from "../../lib/utils";
import { Button, Dialog, FormField, TextInput } from "../ui/primitives";

/** Deterministically serializes an object with sorted keys for accurate dirty checking */
function stableSerialize(val: unknown): string {
  if (val === null || val === undefined) return "";
  if (typeof val !== "object") return JSON.stringify(val);
  if (Array.isArray(val)) {
    return "[" + val.map(stableSerialize).join(",") + "]";
  }
  const keys = Object.keys(val as Record<string, unknown>).sort();
  const pairs = keys
    .filter((k) => (val as Record<string, unknown>)[k] !== undefined)
    .map((k) => `${JSON.stringify(k)}:${stableSerialize((val as Record<string, unknown>)[k])}`);
  return "{" + pairs.join(",") + "}";
}
import { slotFieldCatalog } from "../../lib/slotFieldCatalog";
import {
  fillSessionFromDoc,
  patchFillSession,
  pcmFromDoc,
  patchPcm,
  patchPcmRules,
  patchPcmSizeExpr,
  patchPcmBookExpr,
  pcmBookExprFromDoc,
  pcmRulesFromDoc,
  pcmSizeExprFromDoc,
  patchPyramid,
  pyramidFromDoc,
  patchProgressive,
  patchStopCooldown,
  patchExitRules,
  exitRulesFromDoc,
  initStopFromDoc,
  patchInitStop,
  pinChampionPipeline,
  progressiveFromDoc,
  stopCooldownFromDoc,
} from "../../lib/pipelineSlotBindings";
import { parseRules } from "../../lib/rulesAst";
import type {
  ScreenPreset,
  SavedScreen,
  BacktestSpecSummary,
  EvaluationConfig,
  SweepParamRange,
  UniverseQueryV1,
  IrWhereNode,
} from "../../types";

function specDataFromLoadedSpec(
  loadedSpec: { spec?: unknown; algorithm_json?: string | null } | null,
): Record<string, unknown> | null {
  if (!loadedSpec) return null;
  if (loadedSpec.spec && typeof loadedSpec.spec === "object") {
    return loadedSpec.spec as Record<string, unknown>;
  }
  if (loadedSpec.algorithm_json) {
    try {
      return JSON.parse(loadedSpec.algorithm_json) as Record<string, unknown>;
    } catch {
      return null;
    }
  }
  return null;
}

const HYGIENE_STAGE_NAME = "Universe Hygiene";

/** Agent-facing metadata for strategy draft fields (webmcp strategy_list_fields). */
const STRATEGY_FIELD_CATALOG: Record<string, { label: string; hint: string }> = {
  "strategy_name": { label: "Strategy name", hint: "Title shown in the registry and backtests." },
  "min_screens": { label: "Min screens", hint: "Gate: minimum counted screens a candidate needs." },
  "gate_combine": { label: "Gate combine", hint: "How screen gates combine (count / any)." },
  "max_entry_atr_pct": { label: "Entry ATR cap", hint: "Skip candidates whose trailing ATR% exceeds this. 0/null = off." },
  "sizing.policy": { label: "PCM policy", hint: "Portfolio construction model family (risk_budgeted)." },
  "sizing.risk_per_trade_pct": { label: "Risk per trade (1R)", hint: "Fraction of equity risked per name: shares = equity × 1R ÷ (entry − stop)." },
  "sizing.max_weight": { label: "Max capital per name", hint: "Hard cap on target portfolio percent for one name." },
  "sizing.max_positions": { label: "Max positions", hint: "Concurrent position limit." },
  "sizing.default_stop_loss_pct": { label: "Fallback stop", hint: "Stop distance when an Insight carries no stop info." },
  "sizing.min_regime_fraction": { label: "Min regime fraction", hint: "Floor for the weekly regime exposure multiplier." },
  "sizing.regime_neutral_fraction": { label: "Neutral regime fraction", hint: "Exposure when the regime signal is neutral." },
  "sizing.regime_bull_fraction": { label: "Bull regime fraction", hint: "Exposure when the regime signal is bullish." },
  "sizing.scaled_max_positions_floor": { label: "Scaled max positions floor", hint: "Position-count floor when regime scales exposure down." },
  "sizing.honor_insight_confidence": { label: "Honor Insight confidence", hint: "Scale targets by Insight.Confidence." },
  "sizing.allow_adds_on_invested": { label: "Allow adds on invested names", hint: "Permit pyramid adds after the first fill." },
  "risk.max_positions": { label: "Risk max positions", hint: "Position limit mirrored on the risk slot." },
  "regime_gate": { label: "Regime gate", hint: "Cross-slot regime policy (compiles to DataSources.regime + uses[] → PCM/Alpha)." },
  "execution.fill_session": { label: "Fill session", hint: "MOO (market on open) or MOC (market on close) fills." },
  "policy_overrides": { label: "Policy overrides", hint: "Conditional knob overrides (e.g. size up on EPS beat)." },
};

export interface AssembledFrameworkSpec {
  UniverseSelection: {
    Type: string;
    Parameters: Record<string, unknown>;
  };
  Alpha: {
    Type: string;
    Parameters: Record<string, unknown>;
  };
  PortfolioConstruction: {
    Type: string;
    Parameters: Record<string, unknown>;
  };
  RiskManagement: {
    Type: string;
    Parameters: Record<string, unknown>;
  };
  Execution: {
    Type: string;
    Parameters: Record<string, unknown>;
  };
}

// Drafts live only in this browser tab. Saved versions keep separate entries by content hash.
const strategyDrafts = new Map<string, { document: PipelineDocument; title: string }>();

interface AlgorithmStudioViewProps {
  universeTitle?: string;
  universeCandidateCount?: number;
  universeChoice: UniverseChoice;
  onSelectUniverseChoice: (choice: UniverseChoice) => void;
  presets?: ScreenPreset[];
  savedScreens?: SavedScreen[];
  onChangeFramework: (framework: AssembledFrameworkSpec) => void;
  onChangeFullSpec?: (spec: Record<string, unknown>) => void;
  onLaunchBacktest?: () => void;
  onLaunchOptimizer?: () => void;
  evaluationConfig?: EvaluationConfig;
  onChangeEvaluationConfig?: (cfg: EvaluationConfig) => void;
  loadedSpec?: BacktestSpecSummary | null;
  onOpenSpecLibrary?: () => void;
  strategyIrId?: string;
  onChangeStrategyIrId?: (irId: string) => void;
  isTemplate?: boolean;
  onChangeIsTemplate?: (isTemplate: boolean) => void;
  composeTitle?: string;
  onChangeTitle?: (title: string) => void;
  /** Authored PipelineDocument for save/agent round-trip. */
  onChangeAuthoredPipeline?: (doc: PipelineDocument | null) => void;
  /** Persist current pipeline + compiled spec to ClickHouse. */
  onSaveStrategy?: () => Promise<void> | void;
  /** Fork strategy as an incremented/named version. */
  onForkStrategy?: (newIrId: string, newTitle: string, notes?: string) => Promise<void> | void;
  saveStrategyPending?: boolean;
  composeDirty?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  autoSaveKey?: string;
  savedVersionRunId?: string;
  prefillScreen?: UniverseQueryV1 | null;
}

export function AlgorithmStudioView({
  universeTitle = "Minervini Trend Template",
  universeCandidateCount: _universeCandidateCount,
  universeChoice,
  onSelectUniverseChoice,
  presets = [],
  savedScreens = [],
  onChangeFramework,
  onChangeFullSpec,
  onLaunchBacktest,
  onLaunchOptimizer,
  evaluationConfig,
  onChangeEvaluationConfig,
  loadedSpec,
  onOpenSpecLibrary,
  strategyIrId = "",
  onChangeStrategyIrId,
  isTemplate = false,
  onChangeIsTemplate,
  composeTitle = "",
  onChangeTitle,
  onChangeAuthoredPipeline,
  onSaveStrategy,
  onForkStrategy,
  saveStrategyPending = false,
  composeDirty = false,
  onDirtyChange,
  autoSaveKey = "",
  savedVersionRunId,
  prefillScreen,
}: AlgorithmStudioViewProps) {
  const location = useLocation();
  const activeSlot = strategySlotFromSearch(location.search);
  const draftKey = loadedSpec
    ? JSON.stringify([loadedSpec.ir_id, loadedSpec.ir_content_hash ?? loadedSpec.updated_at ?? loadedSpec.algorithm_json ?? loadedSpec.pipeline_document])
    : "untitled";

  const [pipelineDoc, setPipelineDocState] = useState<PipelineDocument | null>(null);
  const [pipelineDecompileError, setPipelineDecompileError] = useState<string | null>(null);
  const [compiledFromAlpha, setCompiledFromAlpha] = useState<AssembledFrameworkSpec | null>(null);
  const [baselineSnapshot, setBaselineSnapshot] = useState<{
    irId: string;
    title: string;
    pipelineJson: string;
    pipelineDoc: PipelineDocument;
  } | null>(null);
  const [strategySettingsOpen, setStrategySettingsOpen] = useState(false);
  const [forkModalOpen, setForkModalOpen] = useState(false);
  const autoSaveAttemptRef = useRef("");

  const normalizePipeline = useCallback((doc: PipelineDocument | null) => {
    if (!doc) return null;
    return doc;
  }, []);

  const commitPipelineDoc = useCallback(
    (next: PipelineDocument | null) => {
      const normalized = normalizePipeline(next);
      setPipelineDocState(normalized);
      // Keep parent authoredPipelineRef in sync for Save (Universe AST, stage AST, PCM/Risk).
      onChangeAuthoredPipeline?.(normalized);
    },
    [onChangeAuthoredPipeline, normalizePipeline],
  );

  const setPipelineDoc = useCallback(
    (update: PipelineDocument | null | ((prev: PipelineDocument | null) => PipelineDocument | null)) => {
      setPipelineDocState((prev) => {
        const raw = typeof update === "function" ? update(prev) : update;
        const next = normalizePipeline(raw);
        queueMicrotask(() => onChangeAuthoredPipeline?.(next));
        return next;
      });
    },
    [onChangeAuthoredPipeline, normalizePipeline],
  );

  // Automatically deserialize and populate state when a spec/template is loaded
  useEffect(() => {
    if (!loadedSpec) return;

    const specData = specDataFromLoadedSpec(loadedSpec);
    if (!specData) return;

    const fw = (specData.Framework || specData.framework || {}) as Record<string, unknown>;

    // 1. Universe Slot
    const uni = (fw.UniverseSelection || fw.universe || {}) as Record<string, unknown>;
    const uniType = String(uni.Type || uni.type_id || "VeraScreenerUniverseSelectionModel");

    const vb = (specData.VeraBase || specData.vera_base || {}) as Record<string, unknown>;
    // Do not stuff the full VeraBase.Universe (computed gates / screens_hit) into the
    // Universe slot inline AST — that bypasses pipeline compile and can surface
    // dangling screen_* columns in SQL preview. Prefer pipeline_document recompile.
    const hasPipelineAuthored =
      (loadedSpec.pipeline_document &&
        typeof loadedSpec.pipeline_document === "object" &&
        "stages" in loadedSpec.pipeline_document) ||
      (vb.Pipeline &&
        typeof vb.Pipeline === "object" &&
        "stages" in (vb.Pipeline as Record<string, unknown>));
    if (
      !hasPipelineAuthored &&
      uniType === "VeraScreenerUniverseSelectionModel" &&
      vb.Universe &&
      typeof vb.Universe === "object"
    ) {
      onSelectUniverseChoice({ kind: "inline" });
    }
  }, [loadedSpec, onSelectUniverseChoice]);

  // Decompile a loaded full spec into a PipelineDocument so the pipeline canvas
  // (the source of truth for authoring) can faithfully re-edit and recompile it.
  useEffect(() => {
    function restoreDraft(baseline: PipelineDocument, baselineTitle: string) {
      const draft = strategyDrafts.get(draftKey);
      setPipelineDoc(draft?.document ?? baseline);
      if (draft) onChangeTitle?.(draft.title);
      setBaselineSnapshot({
        irId: loadedSpec?.ir_id ?? "", title: baselineTitle,
        pipelineJson: stableSerialize(baseline), pipelineDoc: baseline,
      });
    }
    if (!loadedSpec) {
      const screen = prefillScreen?.where ? irToFilterTrees(prefillScreen.where as IrWhereNode) : [];
      const name = composeTitle || (screen.length ? universeTitle : "");
      restoreDraft(pinChampionPipeline({
        strategy_name: name, stages: [],
        universe: { source: "screener", screen, limit_per_day: prefillScreen?.limit_per_day ?? (typeof prefillScreen?.limit === "number" ? prefillScreen.limit : 100) },
        sizing: { policy: "risk_budgeted", max_positions: 10, risk_per_trade_pct: 0.005, max_weight: 0.25 },
        risk: { max_positions: 10, max_sector_exposure: 0.25 }, execution: { type: "market_order" },
      }), composeTitle);
      setPipelineDecompileError(null);
      return;
    }

    const applyAuthored = (raw: PipelineDocument) => {
      let doc = pinChampionPipeline({
        ...raw,
        universe: {
          ...(raw.universe ?? {}),
          source: raw.universe?.source ?? "screener",
          screen: raw.universe?.screen ?? [],
        },
        stages: (raw.stages ?? []).filter((s) => s.name !== HYGIENE_STAGE_NAME),
        sizing: {
          ...(raw.sizing ?? {}),
          policy: "risk_budgeted",
        },
      });
      // Read-side mirror: specs persisted before save-time materialization carry the
      // generated ladder only in Framework.RiskManagement.Parameters — hydrate the
      // exit stage (rules + init_stop) so the Risk card renders what actually ran.
      {
        const specData = specDataFromLoadedSpec(loadedSpec);
        const fw = (specData?.Framework ?? specData?.framework ?? {}) as Record<
          string,
          unknown
        >;
        const risk = (fw.RiskManagement ?? fw.risk_management ?? {}) as Record<
          string,
          unknown
        >;
        const params = (risk.Parameters ?? risk.parameters ?? {}) as Record<
          string,
          unknown
        >;
        if (exitRulesFromDoc(doc).length === 0) {
          const rules = parseRules(params.rules);
          if (rules.length > 0) doc = patchExitRules(doc, rules);
        }
        // Same mirror for the materialized initial-stop AST (C-VERA-EXPR-V2):
        // Parameters.init_stop hydrates the exit stage when the doc lacks it.
        if (initStopFromDoc(doc) == null) {
          const initStop = params.init_stop;
          if (initStop && typeof initStop === "object") {
            doc = patchInitStop(doc, initStop as Record<string, unknown>);
          }
        }
      }
      restoreDraft(doc, (loadedSpec.title || composeTitle).trim());
      setPipelineDecompileError(null);
    };

    const authored = loadedSpec.pipeline_document;
    if (authored && typeof authored === "object" && "stages" in authored) {
      applyAuthored(authored as PipelineDocument);
      return;
    }

    const specData = specDataFromLoadedSpec(loadedSpec);
    if (!specData) {
      setPipelineDoc(null);
      setPipelineDecompileError(null);
      return;
    }

    const vb = (specData.VeraBase || specData.vera_base || {}) as Record<string, unknown>;
    if (vb.Pipeline && typeof vb.Pipeline === "object" && "stages" in (vb.Pipeline as Record<string, unknown>)) {
      applyAuthored(vb.Pipeline as PipelineDocument);
      return;
    }

    let cancelled = false;
    setPipelineDecompileError(null);
    void decompilePipeline(specData)
      .then((doc) => {
        if (cancelled) return;
        applyAuthored(doc);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setPipelineDoc(null);
        const detail = err instanceof Error ? err.message : String(err);
        setPipelineDecompileError(
          `This spec could not be loaded into Universe + Alpha. ${detail}`,
        );
      });
    return () => {
      cancelled = true;
    };
  }, [loadedSpec]);

  useEffect(() => {
    if (compiledFromAlpha) onChangeFramework(compiledFromAlpha);
  }, [compiledFromAlpha, onChangeFramework]);

  // Dynamic Universe title based on active model and choice
  const activePreset = presets.find(
    (p) => universeChoice.kind === "preset" && p.id === universeChoice.id
  );
  const activeSaved = savedScreens.find(
    (s) => universeChoice.kind === "saved" && String(s.id) === String(universeChoice.id)
  );

  const dynamicUniverseTitle = useMemo(() => {
    if (universeChoice.kind === "preset") {
      return activePreset?.label || universeChoice.id;
    }
    if (universeChoice.kind === "saved") {
      return activeSaved?.name || "Saved Screen";
    }
    if (universeChoice.kind === "inline") {
      return "Custom AST Screen";
    }
    return universeTitle || "Universe AST Screen";
  }, [
    universeChoice,
    activePreset,
    activeSaved,
    universeTitle,
  ]);

  const evalConfig = evaluationConfig ?? INITIAL_EVALUATION_CONFIG;
  const strategyNameValue = pipelineDoc?.strategy_name ?? composeTitle;
  const pcm = pcmFromDoc(pipelineDoc ?? { strategy_name: "", stages: [] });
  const pyramid = pyramidFromDoc(pipelineDoc ?? { strategy_name: "", stages: [] });
  const progressive = progressiveFromDoc(
    pipelineDoc ?? { strategy_name: "", stages: [] },
  );
  const fillSession = fillSessionFromDoc(pipelineDoc ?? { strategy_name: "", stages: [] });
  const pcmSlotFields = useMemo(
    () => slotFieldCatalog(pipelineDoc?.stages ?? []),
    [pipelineDoc?.stages],
  );
  const riskSlotFields = useMemo(
    () => slotFieldCatalog(pipelineDoc?.stages ?? []),
    [pipelineDoc?.stages],
  );

  // --- StudioAgentBridge: publish the live draft + agent authoring handlers ---
  useEffect(() => {
    studioAgentBridge.updateState({
      // the top level is a clause list: adopt the flat form so the wrapper cannot come back
      strategyDoc: normalizeDocumentScreen(pipelineDoc) as unknown as Record<string, unknown> | null,
      strategyIrId: loadedSpec?.ir_id ?? null,
      dirty: composeDirty,
    });
  }, [pipelineDoc, loadedSpec?.ir_id, composeDirty]);

  useEffect(() => {
    const offSet = studioAgentBridge.registerAction(
      "setStrategyField",
      ({ path, value }: { path: string; value: unknown }) => {
        setPipelineDoc((doc) => {
          const base = doc ?? ({ strategy_name: "", stages: [] } as PipelineDocument);
          return setPathValue(base, path, value) as PipelineDocument;
        });
        return { path, value };
      },
    );
    const offSave = studioAgentBridge.registerAction("saveStrategy", () => {
      onSaveStrategy?.();
      return { ok: true, pending: saveStrategyPending };
    });
    return () => {
      offSet();
      offSave();
    };
  }, [onSaveStrategy, saveStrategyPending, setPipelineDoc]);

  const listStrategyFields = useCallback(() => {
    const doc = (pipelineDoc ?? {}) as unknown as Record<string, unknown>;
    const out: Array<{ path: string; value: unknown; type: string; label?: string; description?: string }> = [];
    const walk = (node: unknown, prefix: string, depth: number) => {
      if (node == null || depth > 6) return;
      if (Array.isArray(node)) {
        node.forEach((item, i) => walk(item, `${prefix}[${i}]`, depth + 1));
        return;
      }
      if (typeof node === "object") {
        for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
          walk(v, prefix ? `${prefix}.${k}` : k, depth + 1);
        }
        return;
      }
      const meta = STRATEGY_FIELD_CATALOG[prefix];
      out.push({
        path: prefix,
        value: node,
        type: typeof node,
        ...(meta ? { label: meta.label, description: meta.hint } : {}),
      });
    };
    walk(doc, "", 0);
    return out;
  }, [pipelineDoc]);

  useEffect(() => {
    return studioAgentBridge.registerAction("listStrategyFields", listStrategyFields);
  }, [listStrategyFields]);

  function patchBindings(
    doc: PipelineDocument,
    patch: Partial<NonNullable<PipelineDocument["bindings"]>>,
  ): PipelineDocument {
    let rules = doc.policy_rules ?? [];
    const syncRoles = [
      "pcm_allow_entry",
      "risk_allow_pyramid_add",
      "risk_skip_time_stop",
      "alpha_eligibility",
      "alpha_setup",
      "alpha_confidence",
      "pcm_scale",
    ] as const;
    for (const role of syncRoles) {
      if (role in patch) {
        rules = upsertPolicyRuleForBinding(
          rules,
          role,
          (patch[role] as SlotExpr | null | undefined) ?? null,
        );
      }
    }
    return {
      ...doc,
      bindings: { ...(doc.bindings ?? {}), ...patch },
      policy_rules: rules,
    };
  }
  const availableSweepParams = useMemo<SweepParamRange[]>(
    () => [
      { name: "risk_per_trade_pct", label: "Risk Budget % (1R)", target_slot: "Portfolio", min: 0.005, max: 0.02, step: 0.0025 },
      { name: "take_profit_r", label: "Tranche 1 Profit (R)", target_slot: "Risk", min: 1.5, max: 3.5, step: 0.5 },
      { name: "max_positions", label: "Max Portfolio Capacity", target_slot: "Portfolio", min: 5, max: 20, step: 5 },
    ],
    [],
  );

  const isCatalog = Boolean(loadedSpec?.ir_id?.startsWith("catalog:") || loadedSpec?.is_system);
  const isNewDraft = !loadedSpec || !loadedSpec.ir_id;
  const isLegacySpec = Boolean(loadedSpec && loadedSpec.schema_status === "legacy" && !loadedSpec.has_pipeline);
  const canAutoSave = Boolean(onSaveStrategy && loadedSpec && !isCatalog && !isNewDraft && !isLegacySpec);
  const [autoSaveStatus, setAutoSaveStatus] = useState<"idle" | "waiting" | "saving" | "saved" | "error">("idle");

  const currentPipelineJson = useMemo(() => stableSerialize(pipelineDoc), [pipelineDoc]);
  const currentTitleClean = (composeTitle || "").trim();
  const autoSaveSignature = stableSerialize([loadedSpec?.ir_id, currentPipelineJson, currentTitleClean, autoSaveKey]);

  const hasLocalUnsavedEdits = useMemo(() => {
    if (!baselineSnapshot || baselineSnapshot.irId !== (loadedSpec?.ir_id ?? "")) return false;
    const docChanged = currentPipelineJson !== baselineSnapshot.pipelineJson;
    const titleChanged = currentTitleClean !== baselineSnapshot.title;
    return docChanged || titleChanged;
  }, [baselineSnapshot, loadedSpec?.ir_id, currentPipelineJson, currentTitleClean]);
  const hasUnsavedEdits = hasLocalUnsavedEdits || composeDirty;

  useEffect(() => {
    if (!canAutoSave || !hasUnsavedEdits || !onSaveStrategy) return;
    if (autoSaveAttemptRef.current === autoSaveSignature) return;
    if (saveStrategyPending) {
      setAutoSaveStatus("saving");
      return;
    }
    setAutoSaveStatus("waiting");
    const timeout = window.setTimeout(() => {
      autoSaveAttemptRef.current = autoSaveSignature;
      setAutoSaveStatus("saving");
      Promise.resolve(onSaveStrategy()).then(
        () => setAutoSaveStatus("saved"),
        () => setAutoSaveStatus("error"),
      );
    }, 900);
    return () => window.clearTimeout(timeout);
  }, [canAutoSave, hasUnsavedEdits, onSaveStrategy, saveStrategyPending, draftKey, autoSaveSignature]);

  useEffect(() => {
    onDirtyChange?.(hasLocalUnsavedEdits);
  }, [hasLocalUnsavedEdits, onDirtyChange]);

  useEffect(() => {
    if (!pipelineDoc || !baselineSnapshot || baselineSnapshot.irId !== (loadedSpec?.ir_id ?? "")) return;
    if (hasUnsavedEdits) strategyDrafts.set(draftKey, { document: pipelineDoc, title: composeTitle });
    else strategyDrafts.delete(draftKey);
  }, [draftKey, pipelineDoc, composeTitle, hasUnsavedEdits, baselineSnapshot, loadedSpec?.ir_id]);

  return (
    <div className="space-y-4">
      <div className="strategy-workspace-toolbar" aria-label="Strategy workspace">
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">Strategy</span>
          <strong className="truncate text-sm font-semibold text-ink">{strategyNameValue || "Untitled strategy"}</strong>
          {canAutoSave && (
            <span role="status" className={cn(
              "hidden rounded-full px-2 py-1 text-[10px] font-medium sm:inline-flex",
              autoSaveStatus === "error" ? "bg-danger-soft text-danger" :
                autoSaveStatus === "waiting" || autoSaveStatus === "saving" ? "bg-warn/10 text-warn" :
                  "bg-surface-sunk text-ink-muted",
            )}>
              {autoSaveStatus === "waiting" ? "Saving shortly" : autoSaveStatus === "saving" ? "Saving…" : autoSaveStatus === "error" ? "Save failed" : autoSaveStatus === "saved" ? "Saved" : "Up to date"}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {onOpenSpecLibrary && (
            <Button type="button" variant="secondary" className="min-h-9 px-3 text-xs" onClick={onOpenSpecLibrary}>
              Strategies
            </Button>
          )}
          <Button type="button" variant="ghost" className="min-h-9 px-2.5 text-xs" aria-label="Strategy settings" onClick={() => setStrategySettingsOpen(true)}>
            <span aria-hidden="true">⚙</span><span className="hidden sm:inline">Settings</span>
          </Button>
        </div>
      </div>
      <Dialog
        open={strategySettingsOpen}
        title="Strategy settings"
        onClose={() => setStrategySettingsOpen(false)}
        footer={(
          <>
            {loadedSpec && !isCatalog && (
              <Button type="button" variant="secondary" onClick={() => {
                setStrategySettingsOpen(false);
                setForkModalOpen(true);
              }}>Fork version…</Button>
            )}
            <Button type="button" variant="primary" onClick={() => setStrategySettingsOpen(false)}>Done</Button>
          </>
        )}
      >
        <div className="space-y-4">
          <p className="text-xs leading-5 text-ink-muted">Workspace metadata for this strategy. Pipeline behavior remains configured in the five slots.</p>
          <FormField label="Strategy name" hint="Shown in the strategy library and backtest records.">
            <TextInput
              type="text"
              value={strategyNameValue}
              onChange={(event) => {
                const name = event.target.value;
                onChangeTitle?.(name);
                setPipelineDoc((doc) => doc
                  ? { ...doc, strategy_name: name }
                  : pinChampionPipeline({
                      strategy_name: name,
                      stages: [],
                      universe: { source: "screener" },
                      sizing: { policy: "risk_budgeted", max_positions: 10, risk_per_trade_pct: 0.005, max_weight: 0.25 },
                      risk: { max_positions: 10 },
                      execution: { type: "market_order" },
                    }));
              }}
              placeholder="Strategy name"
            />
          </FormField>
          <FormField label="Strategy ID" hint="Stable registry identity; existing saved strategy links use this value.">
            <TextInput
              type="text"
              value={strategyIrId}
              onChange={(event) => onChangeStrategyIrId?.(event.target.value)}
              placeholder="Assigned when saved"
              className="font-mono"
            />
          </FormField>
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            <input type="checkbox" checked={isTemplate} onChange={(event) => onChangeIsTemplate?.(event.target.checked)} />
            Show in the template filter
          </label>
          <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs text-ink-muted">
            <span>{isCatalog ? "System template" : isNewDraft ? "New draft" : isLegacySpec ? "Legacy format" : "Five-slot pipeline"}</span>
            {loadedSpec?.ir_id && <CopyIdBadge id={loadedSpec.ir_id} label="Copy strategy ID" head={10} tail={6} />}
          </div>
        </div>
      </Dialog>
      <nav aria-label="Strategy slots" className="slot-navigation">
        {STRATEGY_SLOTS.map((slot, index) => {
          const params = new URLSearchParams(location.search);
          params.set("slot", slot.id);
          return (
            <Link key={slot.id} className="slot-link" aria-current={slot.id === activeSlot.id ? "page" : undefined}
              to={{ pathname: location.pathname, search: params.toString(), hash: location.hash }}>
              <span aria-hidden="true" className="slot-step-number">{index + 1}</span>
              <span className="slot-step-label">{slot.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="space-y-3">

        <div>
          <section aria-label="Universe" hidden={activeSlot.id !== "universe"}>
            <UniverseSlotCard
              screen={pipelineDoc?.universe?.screen ?? []}
              asOf={evalConfig.end_date || ""}
              startDate={evalConfig.start_date || ""}
              onChangeScreen={(nextScreen) => {
                setPipelineDoc((doc) =>
                  doc
                    ? {
                        ...doc,
                        universe: {
                          ...(doc.universe ?? {}),
                          source: doc.universe?.source ?? "screener",
                          screen: nextScreen,
                        },
                      }
                    : pinChampionPipeline({
                        strategy_name: composeTitle.trim() || "Untitled Strategy",
                        stages: [],
                        universe: { source: "screener", screen: nextScreen },
                        sizing: { policy: "risk_budgeted", max_positions: 10, risk_per_trade_pct: 0.005, max_weight: 0.25 },
                        risk: { max_positions: 10, max_sector_exposure: 0.25 },
                        execution: { type: "market_order" },
                      }),
                );
              }}
            />

          </section>
          <section aria-label="Alpha" hidden={activeSlot.id !== "alpha"}>
            <div className="space-y-3 rounded-lg border border-line bg-surface p-3.5 shadow-sm">
              <div className="border-b border-line pb-2">
                <h4 className="text-[12.5px] font-bold text-ink">2. Alpha</h4>
              </div>
              <p className="text-[10.5px] text-ink-muted leading-tight">
                Measures (SQL + Insight ✓ for who/when) → Insights (Insight.Price property lookup
                only). Stops / scale-in on PCM + Risk — not Alpha trigger lists.
              </p>
              <div className="rounded border border-line bg-surface-raised/40 px-2.5 py-2">
                {progressive.regimeOn ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      title="Stop Alpha from emitting new Up insights while the regime is risk-off. Existing positions are still managed by Risk. The regime thermostat lives on the PCM card."
                      onClick={() =>
                        setPipelineDoc((doc) =>
                          doc
                            ? patchProgressive(doc, {
                                regimeUses: progressive.regimeUses.includes("block_new_longs")
                                  ? progressive.regimeUses.filter((u) => u !== "block_new_longs")
                                  : [...progressive.regimeUses, "block_new_longs"],
                              })
                            : doc,
                        )
                      }
                      className={
                        progressive.regimeUses.includes("block_new_longs")
                          ? "rounded border border-accent bg-accent/10 px-1.5 py-0.5 text-[9.5px] font-semibold text-accent-ink"
                          : "rounded border border-line px-1.5 py-0.5 text-[9.5px] text-ink-muted"
                      }
                    >
                      Block new longs in risk-off
                    </button>
                    <span className="text-[9px] text-ink-faint">
                      Regime entry gate — suppresses new Up insights; holds stay managed. Regime
                      source + exposure scaling on the PCM card.
                    </span>
                  </div>
                ) : (
                  <p className="text-[9px] text-ink-faint">
                    Regime entry gate off — enable the regime thermostat on the PCM card to gate
                    new Up insights in risk-off.
                  </p>
                )}
              </div>
              {pipelineDecompileError ? (
                <div className="rounded border border-warn/30 bg-warn-soft px-3 py-2 text-[11px] text-warn">
                  {pipelineDecompileError}
                </div>
              ) : null}
              <StrategyEditorView
                initialDocument={pipelineDoc}
                asOf={evalConfig.end_date || ""}
                startDate={evalConfig.start_date || ""}
                prepareRevision={JSON.stringify(pipelineDoc?.universe?.screen ?? [])}
                prepareDocument={(doc) =>
                  pinChampionPipeline({
                    ...doc,
                    universe: {
                      ...(doc.universe ?? {}),
                      source: doc.universe?.source ?? "screener",
                      screen: pipelineDoc?.universe?.screen ?? doc.universe?.screen ?? [],
                    },
                    stages: (doc.stages ?? []).filter((s) => s.name !== HYGIENE_STAGE_NAME),
                    sizing: {
                      ...(doc.sizing ?? {}),
                      policy: "risk_budgeted",
                    },
                  })
                }
                onChangeDocument={commitPipelineDoc}
                onChangeSpec={(spec) => {
                  const framework = (spec as { Framework?: AssembledFrameworkSpec })?.Framework;
                  if (framework) {
                    setCompiledFromAlpha(framework);
                    onChangeFramework(framework);
                  }
                  onChangeFullSpec?.(spec);
                }}
              />
            </div>

          </section>
          <section aria-label="Portfolio Construction" hidden={activeSlot.id !== "portfolio-construction"}>
            <PcmSlotCard
              phases={pyramid.phases}
              onChangePhases={(phases) =>
                setPipelineDoc((doc) => (doc ? patchPyramid(doc, { phases }) : doc))
              }
              regimeOn={progressive.regimeOn}
              onToggleRegime={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { regimeOn: v }) : doc))
              }
              regimeUses={progressive.regimeUses}
              onChangeRegimeUses={(uses) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { regimeUses: uses }) : doc))
              }
              enableSurrogates={pcm.enableSurrogates}
              onChangeEnableSurrogates={(v) =>
                setPipelineDoc((doc) => (doc ? patchPcm(doc, { enableSurrogates: v }) : doc))
              }
              surrogateSizingMode={pcm.surrogateSizingMode}
              onChangeSurrogateSizingMode={(v) =>
                setPipelineDoc((doc) => (doc ? patchPcm(doc, { surrogateSizingMode: v }) : doc))
              }
              minSurrogateAdv={pcm.minSurrogateAdv}
              onChangeMinSurrogateAdv={(v) =>
                setPipelineDoc((doc) => (doc ? patchPcm(doc, { minSurrogateAdv: v }) : doc))
              }
              slotFields={pcmSlotFields}
              rules={pipelineDoc ? pcmRulesFromDoc(pipelineDoc) : []}
              testIrId={loadedSpec?.ir_id ?? null}
              onChangeRules={(next) =>
                setPipelineDoc((doc) => (doc ? patchPcmRules(doc, next) : doc))
              }
              sizeExpr={pipelineDoc ? pcmSizeExprFromDoc(pipelineDoc) : null}
              onChangeSizeExpr={(v) =>
                setPipelineDoc((doc) => (doc ? patchPcmSizeExpr(doc, v) : doc))
              }
              bookExprs={
                pipelineDoc
                  ? {
                      scale_expr: pcmBookExprFromDoc(pipelineDoc, "scale_expr"),
                      slots_expr: pcmBookExprFromDoc(pipelineDoc, "slots_expr"),
                      order_expr: pcmBookExprFromDoc(pipelineDoc, "order_expr"),
                    }
                  : undefined
              }
              onChangeBookExpr={(key, v) =>
                setPipelineDoc((doc) => (doc ? patchPcmBookExpr(doc, key, v) : doc))
              }
            />

          </section>
          <section aria-label="Risk Management" hidden={activeSlot.id !== "risk-management"}>
            <RiskSlotCard
              tranches={progressive.tranches}
              onChangeTranches={(tranches) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { tranches }) : doc))
              }
              trailingStopPct={progressive.trailingStopPct}
              onChangeTrailingStopPct={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { trailingStopPct: v }) : doc))
              }
              maxHoldDays={progressive.maxHoldDays}
              onChangeMaxHoldDays={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { maxHoldDays: v }) : doc))
              }
              atrStopMultiplier={progressive.atrStopMultiplier}
              onChangeAtrStopMultiplier={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { atrStopMultiplier: v }) : doc))
              }
              maxStopLossPct={progressive.maxStopLossPct}
              onChangeMaxStopLossPct={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { maxStopLossPct: v }) : doc))
              }
              useAtrStops={progressive.useAtrStops}
              onChangeUseAtrStops={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { useAtrStops: v }) : doc))
              }
              breakevenTimeStopDays={progressive.breakevenTimeStopDays}
              onChangeBreakevenTimeStopDays={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { breakevenTimeStopDays: v }) : doc))
              }
              breakevenRTrigger={progressive.breakevenRTrigger}
              onChangeBreakevenRTrigger={(v) =>
                setPipelineDoc((doc) => (doc ? patchProgressive(doc, { breakevenRTrigger: v }) : doc))
              }
              stopCooldownDays={stopCooldownFromDoc(pipelineDoc ?? { strategy_name: "", stages: [] })}
              onChangeStopCooldownDays={(v) =>
                setPipelineDoc((doc) => (doc ? patchStopCooldown(doc, v) : doc))
              }
              slotFields={riskSlotFields}
              skipTimeStopExpr={pipelineDoc?.bindings?.risk_skip_time_stop}
              onChangeSkipTimeStopExpr={(v: SlotExpr | null) =>
                setPipelineDoc((doc) =>
                  doc ? patchBindings(doc, { risk_skip_time_stop: v }) : doc,
                )
              }
              rules={pipelineDoc ? exitRulesFromDoc(pipelineDoc) : []}
              onChangeRules={(next) =>
                setPipelineDoc((doc) => (doc ? patchExitRules(doc, next) : doc))
              }
              testIrId={loadedSpec?.ir_id ?? null}
              initStop={pipelineDoc ? initStopFromDoc(pipelineDoc) : null}
              onChangeInitStop={(v) =>
                setPipelineDoc((doc) => (doc ? patchInitStop(doc, v) : doc))
              }
            />

          </section>
          <section aria-label="Execution" hidden={activeSlot.id !== "execution"}>
            <ExecutionSlotCard
              fillSession={fillSession}
              onChangeFillSession={(v) =>
                setPipelineDoc((doc) => (doc ? patchFillSession(doc, v) : doc))
              }
            />
          </section>
        </div>
        {loadedSpec && !isCatalog && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>Saved-version evidence</span>
            {savedVersionRunId ? (
              <Link className="workbench-control inline-flex items-center text-accent" to={backtestRunPath(savedVersionRunId, "scrubber")}>
                Inspect dated run {savedVersionRunId}
              </Link>
            ) : <span>Matching run unavailable</span>}
          </div>
        )}
        <StrategyDocumentationBanner spec={loadedSpec} defaultExpanded={false} />
      </div>

      {/* In-Canvas Simulation & Evaluation Protocol Panel */}
      {onChangeEvaluationConfig && (
        <EvaluationSettingsPanel
          config={evalConfig}
          onChangeConfig={onChangeEvaluationConfig}
          availableParams={availableSweepParams}
        />
      )}

      {/* Bottom Lifecycle Action Strip */}
      <div className="evaluation-action-bar">
        <div className="evaluation-action-summary" aria-live="polite">
          <span className="evaluation-action-kicker">Backtest</span>
          <span className="evaluation-action-title">Ready to run</span>
          <span className="evaluation-action-detail">
            {dynamicUniverseTitle} · {evalConfig.start_date}–{evalConfig.end_date} · {evalConfig.benchmark}
          </span>
        </div>

        <div className="flex w-full items-center gap-2 sm:w-auto">
          {evalConfig.strategy === "optimization_sweep" ? (
            <Button
              type="button"
              variant="primary"
              onClick={onLaunchOptimizer ?? onLaunchBacktest}
              className="min-h-11 w-full px-4 text-xs font-bold shadow-sm sm:w-auto"
            >
              <span>⚡</span>
              <span>Launch Optimization Sweep</span>
            </Button>
          ) : (
            <Button
              type="button"
              variant="primary"
              onClick={onLaunchBacktest}
              className="min-h-11 w-full px-4 text-xs font-bold shadow-sm sm:w-auto"
            >
              <span>▶</span>
              <span>Launch Baseline Backtest</span>
            </Button>
          )}
        </div>
      </div>

      <ForkStrategyVersionModal
        isOpen={forkModalOpen}
        onClose={() => setForkModalOpen(false)}
        sourceSpec={loadedSpec ?? null}
        currentTitle={composeTitle || loadedSpec?.title || ""}
        onConfirmFork={async (newId, newTitle, notes) => {
          await onForkStrategy?.(newId, newTitle, notes);
        }}
        isPending={saveStrategyPending}
      />
    </div>
  );
}
