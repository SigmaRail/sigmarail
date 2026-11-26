import { useState, useMemo, useEffect, useCallback } from "react";
import { UniverseSlotCard, type UniverseChoice } from "./UniverseSlotCard";
import { PcmSlotCard } from "./PcmSlotCard";
import { RiskSlotCard } from "./RiskSlotCard";
import { upsertPolicyRuleForBinding } from "./PolicyRulesPanel";
import { ExecutionSlotCard } from "./ExecutionSlotCard";
import { studioAgentBridge, setPathValue } from "../../lib/studioAgentBridge";
import { StrategyEditorView } from "../strategy/StrategyEditorView";
import type { PipelineDocument, SlotExpr } from "../strategy/StrategyDocument";
import { irToFilterTrees, normalizeDocumentScreen } from "../../lib/filterTreeChips";
import { decompilePipeline } from "../../api/strategy";
import { ForkStrategyVersionModal } from "./ForkStrategyVersionModal";
import { StrategySettingsDialog } from "./StrategySettingsDialog";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import { useSearchParams } from "react-router-dom";

type StrategySlotKey = "universe" | "alpha" | "portfolio" | "risk" | "execution";
const STRATEGY_SLOT_KEYS: StrategySlotKey[] = ["universe", "alpha", "portfolio", "risk", "execution"];

function isStrategySlotKey(value: string | null): value is StrategySlotKey {
  return value !== null && STRATEGY_SLOT_KEYS.includes(value as StrategySlotKey);
}

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

const EMPTY_FRAMEWORK: AssembledFrameworkSpec = {
  UniverseSelection: { Type: "SigmaRailClickHouseUniverseSelection", Parameters: {} },
  Alpha: { Type: "SigmaRailScreenerAlphaModel", Parameters: {} },
  PortfolioConstruction: {
    Type: "SigmaRailScreenerPortfolioConstructionModel",
    Parameters: {},
  },
  RiskManagement: {
    Type: "SigmaRailRiskManagementModel",
    Parameters: {},
  },
  Execution: { Type: "SigmaRailScreenerExecutionModel", Parameters: {} },
};

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
    Type: "SigmaRailClickHouseUniverseSelection";
    Parameters: Record<string, unknown>;
  };
  Alpha: {
    Type: "SigmaRailScreenerAlphaModel";
    Parameters: Record<string, unknown>;
  };
  PortfolioConstruction: {
    Type: "SigmaRailScreenerPortfolioConstructionModel";
    Parameters: Record<string, unknown>;
  };
  RiskManagement: {
    Type: "SigmaRailRiskManagementModel";
    Parameters: Record<string, unknown>;
  };
  Execution: {
    Type: "SigmaRailScreenerExecutionModel";
    Parameters: Record<string, unknown>;
  };
}

interface AlgorithmStudioViewProps {
  universeTitle?: string;
  universeCandidateCount?: number;
  asOfDate?: string;
  startDate?: string;
  onSelectUniverseChoice: (choice: UniverseChoice) => void;
  presets?: ScreenPreset[];
  savedScreens?: SavedScreen[];
  onChangeFramework: (framework: AssembledFrameworkSpec) => void;
  onChangeFullSpec?: (spec: Record<string, unknown>) => void;
  loadedSpec?: BacktestSpecSummary | null;
  onOpenSpecLibrary?: () => void;
  onOpenSaveTemplate?: (spec: AssembledFrameworkSpec) => void;
  composeTitle?: string;
  onChangeTitle?: (title: string) => void;
  strategyNotes?: string;
  onChangeStrategyNotes?: (notes: string) => void;
  composeIrId?: string;
  onChangeIrId?: (irId: string) => void;
  isTemplate?: boolean;
  onChangeIsTemplate?: (isTemplate: boolean) => void;
  /** Authored PipelineDocument for save/agent round-trip. */
  onChangeAuthoredPipeline?: (doc: PipelineDocument | null) => void;
  /** Persist current pipeline + compiled spec to ClickHouse. */
  onSaveStrategy?: () => void;
  /** Fork strategy as an incremented/named version. */
  onForkStrategy?: (newIrId: string, newTitle: string, notes?: string) => Promise<void> | void;
  saveStrategyPending?: boolean;
  composeDirty?: boolean;
}

export function AlgorithmStudioView({
  universeTitle = "Minervini Trend Template",
  universeCandidateCount: _universeCandidateCount,
  asOfDate = "",
  startDate = "",
  onSelectUniverseChoice,
  onChangeFramework,
  onChangeFullSpec,
  loadedSpec,
  onOpenSpecLibrary,
  onOpenSaveTemplate,
  composeTitle = "",
  onChangeTitle,
  strategyNotes = "",
  onChangeStrategyNotes,
  composeIrId = "",
  onChangeIrId,
  isTemplate = false,
  onChangeIsTemplate,
  onChangeAuthoredPipeline,
  onSaveStrategy,
  onForkStrategy,
  saveStrategyPending = false,
  composeDirty = false,
}: AlgorithmStudioViewProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeSlot, setActiveSlot] = useState<StrategySlotKey>(() => {
    const requestedSlot = searchParams.get("slot");
    return isStrategySlotKey(requestedSlot) ? requestedSlot : "universe";
  });

  useEffect(() => {
    const requestedSlot = searchParams.get("slot");
    if (isStrategySlotKey(requestedSlot) && requestedSlot !== activeSlot) {
      setActiveSlot(requestedSlot);
    }
  }, [searchParams, activeSlot]);

  const selectStrategySlot = useCallback((value: string) => {
    if (!isStrategySlotKey(value)) return;
    setActiveSlot(value);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("slot", value);
    setSearchParams(nextParams, { replace: true });
  }, [searchParams, setSearchParams]);

  // Slot 1: Universe State
  const [inlineSpec, setInlineSpec] = useState<UniverseQueryV1 | null>(null);

  const [pipelineDoc, setPipelineDocState] = useState<PipelineDocument | null>(null);
  const [pipelineDecompileError, setPipelineDecompileError] = useState<string | null>(null);
  const [compiledFromAlpha, setCompiledFromAlpha] = useState<AssembledFrameworkSpec | null>(null);
  const [baselineSnapshot, setBaselineSnapshot] = useState<{
    irId: string;
    title: string;
    notes: string;
    pipelineJson: string;
    pipelineDoc: PipelineDocument;
  } | null>(null);
  const [forkModalOpen, setForkModalOpen] = useState(false);
  const [strategySettingsOpen, setStrategySettingsOpen] = useState(false);

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
        // A new strategy draft has no authored document until its first slot
        // edit. Seed that first edit with the same minimal document shape used
        // by the agent bridge so slot controls never appear interactive while
        // silently dropping changes.
        const base =
          prev ??
          (!loadedSpec && typeof update === "function"
            ? {
                strategy_name: composeTitle.trim() || "Untitled strategy",
                stages: [],
              }
            : prev);
        const raw = typeof update === "function" ? update(base) : update;
        const next = normalizePipeline(raw);
        queueMicrotask(() => onChangeAuthoredPipeline?.(next));
        return next;
      });
    },
    [composeTitle, loadedSpec, onChangeAuthoredPipeline, normalizePipeline],
  );

  // Automatically deserialize and populate state when a spec/template is loaded
  useEffect(() => {
    if (!loadedSpec) return;

    const specData = specDataFromLoadedSpec(loadedSpec);
    if (!specData) return;

    const framework = (specData.Framework || {}) as Record<string, unknown>;
    const universeSlot = (framework.UniverseSelection || {}) as Record<string, unknown>;
    const universeParams = (universeSlot.Parameters || {}) as Record<string, unknown>;
    const universeQuery = universeParams.query;
    const hasPipelineAuthored =
      (loadedSpec.pipeline_document &&
        typeof loadedSpec.pipeline_document === "object" &&
        "stages" in loadedSpec.pipeline_document) ||
      ((specData.SigmaRail as Record<string, unknown> | undefined)?.Pipeline &&
        typeof (specData.SigmaRail as Record<string, unknown>).Pipeline === "object" &&
        "stages" in ((specData.SigmaRail as Record<string, unknown>).Pipeline as Record<string, unknown>));
    if (
      !hasPipelineAuthored &&
      universeQuery &&
      typeof universeQuery === "object"
    ) {
      const uAst = universeQuery as UniverseQueryV1;
      setInlineSpec(uAst);
      onSelectUniverseChoice({ kind: "inline" });
    }
  }, [loadedSpec, onSelectUniverseChoice]);

  // Decompile a loaded full spec into a PipelineDocument so the pipeline canvas
  // (the source of truth for authoring) can faithfully re-edit and recompile it.
  useEffect(() => {
    if (!loadedSpec) {
      setPipelineDoc(null);
      setPipelineDecompileError(null);
      setBaselineSnapshot(null);
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
        // Same mirror for the materialized initial-stop AST (C-SIGMARAIL-EXPR-V2):
        // Parameters.init_stop hydrates the exit stage when the doc lacks it.
        if (initStopFromDoc(doc) == null) {
          const initStop = params.init_stop;
          if (initStop && typeof initStop === "object") {
            doc = patchInitStop(doc, initStop as Record<string, unknown>);
          }
        }
      }
      setPipelineDoc(doc);
      setPipelineDecompileError(null);
      setBaselineSnapshot({
        irId: loadedSpec.ir_id,
        title: (composeTitle || loadedSpec.title || "").trim(),
        notes: loadedSpec.notes ?? "",
        pipelineJson: stableSerialize(doc),
        pipelineDoc: doc,
      });
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

    const vb = (specData.SigmaRail || specData.sigmarail_base || {}) as Record<string, unknown>;
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

  // Send to Strategy / prefilled screen → Universe extra filters (the screen AST).
  useEffect(() => {
    if (!loadedSpec && inlineSpec?.where && !pipelineDoc) {
      const trees = irToFilterTrees(inlineSpec.where as IrWhereNode);
      const name = composeTitle.trim()
        || (universeTitle ? `${universeTitle} Strategy` : "Screen Strategy");
      setPipelineDoc(
        pinChampionPipeline({
          strategy_name: name,
          stages: [],
          universe: {
            source: "screener",
            screen: trees,
            limit_per_day:
              typeof inlineSpec.limit_per_day === "number"
                ? inlineSpec.limit_per_day
                : typeof inlineSpec.limit === "number"
                  ? (inlineSpec.limit as number)
                  : 100,
          },
          sizing: { policy: "risk_budgeted", max_positions: 10, risk_per_trade_pct: 0.005, max_weight: 0.25 },
          risk: { max_positions: 10, max_sector_exposure: 0.25 },
          execution: { type: "market_order" },
        }),
      );
      onChangeTitle?.(name);
    }
  }, [loadedSpec, inlineSpec, universeTitle, pipelineDoc, composeTitle, onChangeTitle]);

  useEffect(() => {
    if (compiledFromAlpha) onChangeFramework(compiledFromAlpha);
  }, [compiledFromAlpha, onChangeFramework]);

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
  const isCatalog = Boolean(loadedSpec?.ir_id?.startsWith("catalog:") || loadedSpec?.is_system);
  const isNewDraft = !loadedSpec || !loadedSpec.ir_id;
  const isLegacySpec = Boolean(loadedSpec && loadedSpec.schema_status === "legacy" && !loadedSpec.has_pipeline);
  const isSharedSpec = Boolean(loadedSpec?.is_shared);

  const currentPipelineJson = useMemo(() => stableSerialize(pipelineDoc), [pipelineDoc]);
  const currentTitleClean = (composeTitle || "").trim();

  const hasUnsavedEdits = useMemo(() => {
    if (isNewDraft) return Boolean(pipelineDoc && (pipelineDoc.stages?.length || pipelineDoc.universe?.screen?.length));
    if (!baselineSnapshot || baselineSnapshot.irId !== loadedSpec?.ir_id) return false;
    const docChanged = currentPipelineJson !== baselineSnapshot.pipelineJson;
    const titleChanged = currentTitleClean !== baselineSnapshot.title;
    const notesChanged = strategyNotes !== baselineSnapshot.notes;
    return docChanged || titleChanged || notesChanged;
  }, [isNewDraft, pipelineDoc, baselineSnapshot, loadedSpec?.ir_id, currentPipelineJson, currentTitleClean, strategyNotes]);

  const handleRevert = useCallback(() => {
    if (!baselineSnapshot) return;
    setPipelineDoc(baselineSnapshot.pipelineDoc);
    if (baselineSnapshot.title && onChangeTitle) {
      onChangeTitle(baselineSnapshot.title);
    }
    onChangeStrategyNotes?.(baselineSnapshot.notes);
  }, [baselineSnapshot, setPipelineDoc, onChangeTitle, onChangeStrategyNotes]);

  return (
    <div className="space-y-3">
      <Card className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 shadow-none">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Badge variant={hasUnsavedEdits ? "warning" : "muted"} className="px-2 py-0.5 text-[11px]">
            {isCatalog ? "System template" : isNewDraft ? "Draft" : isSharedSpec ? "Shared" : hasUnsavedEdits ? "Unsaved changes" : "Saved"}
          </Badge>
          {loadedSpec ? (
            <span className="truncate font-mono text-[10px] text-muted-foreground">{loadedSpec.ir_id}</span>
          ) : null}
          {hasUnsavedEdits && baselineSnapshot ? (
            <Button type="button" variant="ghost" size="sm" onClick={handleRevert} className="h-7 px-2 text-xs">
              Revert
            </Button>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            onClick={onOpenSpecLibrary}
            variant="outline"
            size="sm"
          >
            Strategy library
          </Button>
          <Button
            type="button"
            onClick={() => setStrategySettingsOpen(true)}
            variant="outline"
            size="sm"
            aria-haspopup="dialog"
          >
            Strategy settings
          </Button>
        </div>
      </Card>

      <StrategySettingsDialog
        open={strategySettingsOpen}
        onOpenChange={setStrategySettingsOpen}
        strategyName={strategyNameValue}
        strategyId={composeIrId}
        onStrategyIdChange={onChangeIrId}
        notes={strategyNotes}
        onNotesChange={onChangeStrategyNotes ?? (() => undefined)}
        isTemplate={isTemplate}
        onTemplateChange={onChangeIsTemplate}
        onStrategyNameChange={(name) => {
          onChangeTitle?.(name);
          setPipelineDoc((doc) =>
            doc
              ? { ...doc, strategy_name: name }
              : pinChampionPipeline({
                  strategy_name: name,
                  stages: [],
                  universe: { source: "screener" },
                  sizing: { policy: "risk_budgeted", max_positions: 10, risk_per_trade_pct: 0.005, max_weight: 0.25 },
                  risk: { max_positions: 10 },
                  execution: { type: "market_order" },
                }),
          );
        }}
        loadedSpec={loadedSpec}
        isNewDraft={isNewDraft}
        isCatalog={isCatalog}
        isSharedSpec={isSharedSpec}
        isLegacySpec={isLegacySpec}
        hasUnsavedEdits={hasUnsavedEdits}
        savePending={saveStrategyPending}
        onSave={() => onSaveStrategy?.()}
        onFork={() => {
          setStrategySettingsOpen(false);
          setForkModalOpen(true);
        }}
        onSaveTemplate={() => {
          setStrategySettingsOpen(false);
          onOpenSaveTemplate?.(compiledFromAlpha ?? EMPTY_FRAMEWORK);
        }}
      />

      <Tabs value={activeSlot} onValueChange={selectStrategySlot} className="space-y-0">
          <TabsList
            className="w-full grid grid-cols-5 gap-1 overflow-x-auto"
            style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}
          >
            {([
              ["universe", "Universe", "Universe"],
              ["alpha", "Alpha", "Alpha"],
              ["portfolio", "Portfolio", "Portfolio construction"],
              ["risk", "Risk", "Risk management"],
              ["execution", "Execution", "Execution"],
            ] as [StrategySlotKey, string, string][]).map(([key, label, accessibleName]) => (
              <TabsTrigger
                key={key}
                value={key}
                aria-label={accessibleName}
                className="min-h-10 w-full min-w-0 px-1 py-2 text-[10px] sm:text-xs"
              >
                <span className="max-w-full truncate">{label}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="universe" forceMount className={cn("mt-3", activeSlot === "universe" ? "block" : "hidden")}>
          <UniverseSlotCard
              screen={pipelineDoc?.universe?.screen ?? []}
              asOf={asOfDate}
              startDate={startDate}
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
          </TabsContent>

          <TabsContent value="alpha" forceMount className={cn("mt-3", activeSlot === "alpha" ? "block" : "hidden")}>
              <Card className="space-y-3 rounded-lg p-3.5 shadow-sm">
              <div className="rounded border border-line bg-surface-raised/40 px-2.5 py-2">
                {progressive.regimeOn ? (
                  <Button
                    type="button"
                    variant={progressive.regimeUses.includes("block_new_longs") ? "secondary" : "outline"}
                    size="sm"
                    title="Block new long entries during risk-off. Existing positions remain under Risk rules."
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
                    className="h-7 px-2 text-[10px]"
                    aria-pressed={progressive.regimeUses.includes("block_new_longs")}
                  >
                    Block new longs in risk-off
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="link"
                    size="sm"
                    className="h-6 px-0 text-[10px]"
                    onClick={() => selectStrategySlot("portfolio")}
                  >
                    Enable entry gate in Portfolio
                  </Button>
                )}
              </div>
              {pipelineDecompileError ? (
                <div className="rounded border border-warn/30 bg-warn-soft px-3 py-2 text-[11px] text-warn">
                  {pipelineDecompileError}
                </div>
              ) : null}
              <StrategyEditorView
                initialDocument={pipelineDoc}
                asOf={asOfDate}
                startDate={startDate}
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
              </Card>
          </TabsContent>

          <TabsContent value="portfolio" forceMount className={cn("mt-3", activeSlot === "portfolio" ? "block" : "hidden")}>
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
          </TabsContent>

          <TabsContent value="risk" forceMount className={cn("mt-3", activeSlot === "risk" ? "block" : "hidden")}>
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
          </TabsContent>

          <TabsContent value="execution" forceMount className={cn("mt-3", activeSlot === "execution" ? "block" : "hidden")}>
            <ExecutionSlotCard
              fillSession={fillSession}
              onChangeFillSession={(v) =>
                setPipelineDoc((doc) => (doc ? patchFillSession(doc, v) : doc))
              }
            />
          </TabsContent>
      </Tabs>

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
