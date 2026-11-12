import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { studioAgentBridge } from "../lib/studioAgentBridge";
import { compileUniverseSql, fetchAsOfRange } from "../api/screens";
import {
  composeBacktest,
  fetchBacktestRuns,
  fetchBacktestSpecDetail,
  fetchBacktestSpecHead,
  fetchExecutionHealth,
  launchOptimizerSession,
  saveBacktestSpec,
  submitBacktest,
} from "../api/backtests";
import {
  compilePipeline,
  fetchCatalogTemplate,
  fetchStrategyPreset,
} from "../api/strategy";
import type { PipelineDocument } from "./strategy/StrategyDocument";
import type {
  BacktestPrefill,
  BacktestSpecSummary,
  ComposeBacktestResponse,
  LaunchOptimizerRequest,
  SavedScreen,
  ScreenPreset,
  UniverseQueryV1,
  EvaluationConfig,
} from "../types";

import { AlgorithmStudioView, type AssembledFrameworkSpec } from "./studio/AlgorithmStudioView";
import { SpecLibraryModal } from "./studio/SpecLibraryModal";
import { SaveStrategyTemplateModal } from "./studio/SaveStrategyTemplateModal";
import { OptimizerSweepModal } from "./OptimizerSweepModal";
import { INITIAL_EVALUATION_CONFIG } from "./studio/EvaluationSettingsPanel";
import { evaluationExtraEnv, readEvaluation, stampEvaluation } from "../lib/evaluationSpec";
import { exitRulesFromDoc, patchExitRules } from "../lib/pipelineSlotBindings";
import { parseRules } from "../lib/rulesAst";

const COMPOSE_DEBOUNCE_MS = 500;



type UniverseChoice =
  | { kind: "inline" }
  | { kind: "saved"; id: number | string }
  | { kind: "preset"; id: string };

function sameScreenId(
  a: number | string | null | undefined,
  b: number | string | null | undefined,
): boolean {
  if (a == null || b == null) return false;
  return String(a) === String(b);
}

function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function yearBackStart(datesDesc: string[]): string {
  if (datesDesc.length === 0) return "";
  const idx = Math.min(datesDesc.length - 1, 251);
  return datesDesc[idx] ?? datesDesc[datesDesc.length - 1]!;
}

function validationMessage(
  validation: ComposeBacktestResponse["validation"] | undefined,
): string | undefined {
  if (!validation) return undefined;
  return validation.error ?? validation.message ?? undefined;
}

function initialUniverseChoice(
  savedScreens: SavedScreen[],
  savedScreenId: number | string | null,
  liveSpec: UniverseQueryV1 | null,
  prefill: BacktestPrefill | null | undefined,
): UniverseChoice {
  if (prefill?.universeSource === "preset" && prefill.presetId) {
    return { kind: "preset", id: prefill.presetId };
  }
  if (prefill?.universeSource === "saved" && prefill.savedScreenId != null) {
    return { kind: "saved", id: prefill.savedScreenId };
  }
  if (prefill?.universeSource === "inline" && prefill.inlineSpec) {
    return { kind: "inline" };
  }
  if (savedScreenId != null && savedScreens.some((s) => sameScreenId(s.id, savedScreenId))) {
    return { kind: "saved", id: savedScreenId };
  }
  if (liveSpec) return { kind: "inline" };
  if (savedScreens.length > 0) return { kind: "saved", id: savedScreens[0]!.id };
  return { kind: "inline" };
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-line bg-surface px-3 py-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
        {title}
      </h3>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[11px] font-medium text-ink-muted">
      {children}
    </label>
  );
}

function textInputClassName(): string {
  return "mt-0.5 w-full rounded border border-line bg-surface-raised px-2 py-1.5 font-mono text-[12px] text-ink";
}

export function BacktestComposePanel({
  savedScreens,
  savedScreenId,
  liveSpec,
  backtestPrefill,
  presets = [],
  initialSpec,
  routeStrategyIrId = null,
  onNavigateStrategy,
  onNavigateToRuns,
  onNavigateToOptimize,
}: {
  savedScreens: SavedScreen[];
  savedScreenId: number | string | null;
  liveSpec: UniverseQueryV1 | null;
  backtestPrefill?: BacktestPrefill | null;
  presets?: ScreenPreset[];
  initialSpec?: BacktestSpecSummary | null;
  /** From `/strategies/:irId` — drives hydrate + head poll. */
  routeStrategyIrId?: string | null;
  /** Update address bar when opening/saving a strategy. */
  onNavigateStrategy?: (irId: string | null) => void;
  onOpenScreenerStudio?: never; // screener now inline
  onNavigateToRuns?: () => void;
  onNavigateToOptimize?: () => void;
}) {
  const [universeChoice, setUniverseChoice] = useState<UniverseChoice>(() =>
    initialUniverseChoice(savedScreens, savedScreenId, liveSpec, backtestPrefill),
  );
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewTab, setPreviewTab] = useState<"json" | "sql">("json");
  const [universeSql, setUniverseSql] = useState<string | null>(null);
  const [universeSqlParams, setUniverseSqlParams] = useState<Record<string, unknown> | null>(
    null,
  );
  const [universeSqlError, setUniverseSqlError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [irId, setIrId] = useState("");
  const [irIdTouched, setIrIdTouched] = useState(false);
  const [evaluationConfig, setEvaluationConfig] = useState<EvaluationConfig>(INITIAL_EVALUATION_CONFIG);
  const [composeResult, setComposeResult] = useState<ComposeBacktestResponse | null>(
    null,
  );
  const [composeError, setComposeError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [queueFlash, setQueueFlash] = useState<string | null>(null);
  const leanProject = "VeraTradingLab";

  const [assembledFramework, setAssembledFramework] = useState<AssembledFrameworkSpec | null>(null);
  const [pipelineSpec, setPipelineSpec] = useState<Record<string, unknown> | null>(null);
  const [authoredPipeline, setAuthoredPipeline] = useState<PipelineDocument | null>(null);
  const authoredPipelineRef = useRef<PipelineDocument | null>(null);
  const handleAuthoredPipelineChange = useCallback((doc: PipelineDocument | null) => {
    authoredPipelineRef.current = doc;
    setAuthoredPipeline(doc);
  }, []);
  const [specHash, setSpecHash] = useState<string | null>(null);
  const [composeDirty, setComposeDirty] = useState(false);
  const [activeFrameworkSpec, setActiveFrameworkSpec] = useState<AssembledFrameworkSpec | null>(null);
  const [specLibraryOpen, setSpecLibraryOpen] = useState(false);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [sweepModalOpen, setSweepModalOpen] = useState(false);
  const [loadedSpec, setLoadedSpec] = useState<BacktestSpecSummary | null>(initialSpec || null);
  const [customInlineSpec, setCustomInlineSpec] = useState<UniverseQueryV1 | null>(null);
  const [isTemplate, setIsTemplate] = useState(Boolean(initialSpec?.is_template));
  const [pendingRemote, setPendingRemote] = useState<{
    hash: string;
    title?: string;
    updated_at?: string;
  } | null>(null);
  const [dismissedRemoteHash, setDismissedRemoteHash] = useState<string | null>(null);

  function newStrategyIrId(prefix = "strat"): string {
    return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  }

  function applyLoadedDetail(detail: BacktestSpecSummary) {
    setLoadedSpec(detail);
    if (detail.title) setTitle(detail.title);
    if (detail.ir_id) {
      setIrId(detail.ir_id);
      setIrIdTouched(true);
    }
    if (detail.ir_content_hash) setSpecHash(String(detail.ir_content_hash));
    setIsTemplate(Boolean(detail.is_template));
    const loaded =
      detail.pipeline_document && typeof detail.pipeline_document === "object"
        ? (detail.pipeline_document as PipelineDocument)
        : null;
    // C-FW-RULES read-side mirror: specs saved before save-time materialization
    // (or via paths that skipped it) carry the generated ladder only in
    // Parameters.rules — mirror it onto the exit stage so the Risk card shows
    // the decision table that actually ran, not "runtime defaults".
    let pipe = loaded;
    if (pipe && exitRulesFromDoc(pipe).length === 0) {
      const compiledRaw =
        detail.spec && typeof detail.spec === "object"
          ? (detail.spec as Record<string, unknown>)
          : (() => {
              try {
                return JSON.parse(String(detail.algorithm_json)) as Record<string, unknown>;
              } catch {
                return null;
              }
            })();
      const specParams = (
        (compiledRaw?.Framework as Record<string, unknown> | undefined)
          ?.RiskManagement as Record<string, unknown> | undefined
      )?.Parameters as Record<string, unknown> | undefined;
      const specRules = parseRules(specParams?.rules);
      if (specRules.length > 0) {
        pipe = patchExitRules(pipe, specRules);
      }
    }
    authoredPipelineRef.current = pipe;
    setAuthoredPipeline(pipe);
    // Prefer fresh pipeline compile for SQL preview. Stale algorithm_json may
    // reference screen_* aliases that are no longer emitted as computed bools.
    setPipelineSpec(null);
    setUniverseSql(null);
    setUniverseSqlError(null);
    if (pipe && Array.isArray(pipe.stages) && pipe.stages.length > 0) {
      void compilePipeline(pipe)
        .then((compiled) => {
          setPipelineSpec(compiled as Record<string, unknown>);
        })
        .catch(() => {
          const compiled =
            detail.spec && typeof detail.spec === "object"
              ? (detail.spec as Record<string, unknown>)
              : detail.algorithm_json
                ? (() => {
                    try {
                      return JSON.parse(String(detail.algorithm_json)) as Record<string, unknown>;
                    } catch {
                      return null;
                    }
                  })()
                : null;
          if (compiled && typeof compiled === "object") {
            setPipelineSpec(compiled);
          }
        });
    } else {
      const compiled =
        detail.spec && typeof detail.spec === "object"
          ? (detail.spec as Record<string, unknown>)
          : detail.algorithm_json
            ? (() => {
                try {
                  return JSON.parse(String(detail.algorithm_json)) as Record<string, unknown>;
                } catch {
                  return null;
                }
              })()
            : null;
      if (compiled && typeof compiled === "object") {
        setPipelineSpec(compiled);
      }
    }
    setComposeDirty(false);
    setPendingRemote(null);
  }

  // Hydrate from address bar `/strategies/:irId`.
  useEffect(() => {
    const id = (routeStrategyIrId || "").trim();
    if (!id) return;
    if (irId === id && loadedSpec?.ir_id === id && (loadedSpec.spec || loadedSpec.algorithm_json || loadedSpec.pipeline_document)) {
      return;
    }
    let cancelled = false;
    void fetchBacktestSpecDetail(id)
      .then((detail) => {
        if (cancelled || !detail) return;
        applyLoadedDetail(detail as unknown as BacktestSpecSummary);
      })
      .catch(() => {
        /* keep canvas if 404 */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional route-driven hydrate
  }, [routeStrategyIrId]);

  useEffect(() => {
    if (initialSpec) {
      if (initialSpec.title) setTitle(initialSpec.title);
      if (initialSpec.ir_id) setIrId(initialSpec.ir_id);
      if (initialSpec.ir_content_hash) {
        setSpecHash(String(initialSpec.ir_content_hash));
      }
      setComposeDirty(false);

      if (initialSpec.spec || initialSpec.algorithm_json) {
        setLoadedSpec(initialSpec);
      } else if (initialSpec.ir_id) {
        void fetchBacktestSpecDetail(initialSpec.ir_id)
          .then((detail) => {
            if (detail) {
              setLoadedSpec(detail as unknown as BacktestSpecSummary);
              if (detail.title) setTitle(detail.title);
              if (detail.ir_content_hash) setSpecHash(String(detail.ir_content_hash));
            } else {
              setLoadedSpec(initialSpec);
            }
          })
          .catch(() => {
            setLoadedSpec(initialSpec);
          });
      } else {
        setLoadedSpec(initialSpec);
      }
    }
  }, [initialSpec]);

  useEffect(() => {
    if (!loadedSpec) return;
    let specData: Record<string, unknown> | null = null;
    if ("spec" in loadedSpec && loadedSpec.spec && typeof loadedSpec.spec === "object") {
      specData = loadedSpec.spec as Record<string, unknown>;
    } else if (loadedSpec.algorithm_json) {
      try {
        specData = JSON.parse(loadedSpec.algorithm_json) as Record<string, unknown>;
      } catch {
        specData = null;
      }
    }
    if (!specData) return;
    const ev = readEvaluation(specData);
    if (ev.start_date || ev.end_date || ev.initial_cash != null || ev.benchmark) {
      setEvaluationConfig((prev) => ({
        ...prev,
        ...ev,
      }));
    }
    const fw = (specData.Framework || specData.framework || {}) as Record<string, unknown>;
    const uni = (fw.UniverseSelection || fw.universe || {}) as Record<string, unknown>;
    const uniType = String(uni.Type || uni.type_id || "");

    const vb = (specData.VeraBase || specData.vera_base || {}) as Record<string, unknown>;
    if (uniType !== "ManualUniverseSelectionModel" && uniType !== "CoarseFundamentalUniverseSelectionModel") {
      if (vb.Universe && typeof vb.Universe === "object") {
        const uAst = vb.Universe as UniverseQueryV1;
        setCustomInlineSpec(uAst);
        setUniverseChoice({ kind: "inline" });
      }
    }
  }, [loadedSpec]);

  const queryClient = useQueryClient();

  const healthQuery = useQuery({
    queryKey: ["execution-health"],
    queryFn: fetchExecutionHealth,
    refetchInterval: 30_000,
  });

  const specRunsQuery = useQuery({
    queryKey: ["strategy-runs-count", irId],
    queryFn: () => fetchBacktestRuns({ irId, limit: 1 }),
    enabled: Boolean(irId && !irId.startsWith("catalog:")),
    staleTime: 30_000,
  });
  // The endpoint returns { runs, total }, but the TS type models only the array.
  // We request limit:1 purely to learn whether this spec has any runs at all.
  const activeRunsCount =
    (specRunsQuery.data as unknown as { total?: number } | undefined)?.total ??
    specRunsQuery.data?.length ??
    null;


  const datesQuery = useQuery({
    queryKey: ["as-of-range-compose"],
    queryFn: () => fetchAsOfRange(10000),
    staleTime: 5 * 60_000,
  });

  const datesDesc = datesQuery.data ?? [];

  useEffect(() => {
    if (datesDesc.length === 0) return;
    const endD = datesDesc[0]!;
    const startD = yearBackStart(datesDesc);
    setEvaluationConfig((prev) => ({
      ...prev,
      start_date: prev.start_date === "2025-01-01" ? startD : prev.start_date,
      end_date: prev.end_date === "2026-01-01" ? endD : prev.end_date,
    }));
  }, [datesDesc]);

  useEffect(() => {
    if (
      backtestPrefill?.universeSource === "preset" &&
      backtestPrefill.presetId
    ) {
      setUniverseChoice({ kind: "preset", id: backtestPrefill.presetId });
      return;
    }
    if (
      backtestPrefill?.universeSource === "saved" &&
      backtestPrefill.savedScreenId != null &&
      !backtestPrefill.dirty &&
      savedScreens.some((s) => sameScreenId(s.id, backtestPrefill.savedScreenId))
    ) {
      setUniverseChoice({ kind: "saved", id: backtestPrefill.savedScreenId });
      return;
    }
    if (backtestPrefill?.universeSource === "inline" && backtestPrefill.dirty) {
      setUniverseChoice({ kind: "inline" });
      return;
    }
    setUniverseChoice((prev) => {
      if (prev.kind === "saved" && savedScreens.some((s) => sameScreenId(s.id, prev.id))) {
        return prev;
      }
      if (prev.kind === "preset") return prev;
      return initialUniverseChoice(
        savedScreens,
        savedScreenId,
        liveSpec,
        backtestPrefill,
      );
    });
  }, [savedScreens, savedScreenId, liveSpec, backtestPrefill]);

  const inlineSpec = useMemo(() => {
    if (universeChoice.kind !== "inline") return liveSpec;
    return customInlineSpec ?? liveSpec ?? backtestPrefill?.inlineSpec ?? null;
  }, [backtestPrefill?.inlineSpec, customInlineSpec, liveSpec, universeChoice.kind]);

  const selectedSavedScreen = useMemo(() => {
    if (universeChoice.kind !== "saved") return null;
    return savedScreens.find((s) => sameScreenId(s.id, universeChoice.id)) ?? null;
  }, [savedScreens, universeChoice]);

  const selectedPreset = useMemo(() => {
    if (universeChoice.kind !== "preset") return null;
    return presets.find((p) => p.id === universeChoice.id) ?? null;
  }, [presets, universeChoice]);

  const backtestablePresets = useMemo(
    () => presets.filter((p) => p.backtestable !== false),
    [presets],
  );

  const linkedScreenName = useMemo(() => {
    if (universeChoice.kind === "preset") {
      return selectedPreset?.label ?? universeChoice.id;
    }
    if (universeChoice.kind === "saved") {
      return (
        selectedSavedScreen?.name ??
        savedScreens.find((s) => sameScreenId(s.id, universeChoice.id))?.name ??
        "Saved Screen"
      );
    }
    if (universeChoice.kind === "inline") {
      return "Custom AST Screen";
    }
    if (backtestPrefill?.title) return backtestPrefill.title;
    if (savedScreenId != null) {
      return savedScreens.find((s) => sameScreenId(s.id, savedScreenId))?.name;
    }
    return null;
  }, [
    universeChoice,
    selectedPreset,
    selectedSavedScreen,
    savedScreenId,
    savedScreens,
    backtestPrefill?.title,
  ]);

  useEffect(() => {
    if (backtestPrefill?.title && !title) {
      setTitle(backtestPrefill.title);
    }
  }, [backtestPrefill?.title, title]);

  const isManualOrCoarse =
    assembledFramework?.UniverseSelection?.Type === "ManualUniverseSelectionModel" ||
    assembledFramework?.UniverseSelection?.Type === "CoarseFundamentalUniverseSelectionModel";

  const universeReady =
    isManualOrCoarse ||
    (universeChoice.kind === "inline"
      ? Boolean(inlineSpec)
      : universeChoice.kind === "preset"
        ? Boolean(universeChoice.id)
        : savedScreens.some((s) => sameScreenId(s.id, universeChoice.id)));

  const composePayload = useMemo(() => {
    if (pipelineSpec) {
      return {
        // Full VeraLabV1 from pipeline compile — no legacy template JSON.
        spec: stampEvaluation(pipelineSpec, {
          start_date: evaluationConfig.start_date,
          end_date: evaluationConfig.end_date,
          initial_cash: evaluationConfig.initial_cash,
          benchmark: evaluationConfig.benchmark,
        }),
        title: title.trim() || undefined,
      };
    }
    if (!universeReady) return null;
    // Backend requires template_id, framework, or spec. Without an assembled
    // framework (and no pipeline spec), composing would 400 — wait instead.
    if (!assembledFramework) return null;
    let universe =
      universeChoice.kind === "inline"
        ? { source: "inline" as const, inline_spec: inlineSpec! }
        : universeChoice.kind === "preset"
          ? {
              source: "screen_preset" as const,
              preset_id: universeChoice.id,
            }
          : {
              source: "saved_screen" as const,
              saved_screen_id: universeChoice.id,
            };

    if (isManualOrCoarse) {
      universe = {
        source: "inline" as const,
        inline_spec: inlineSpec ?? {
          version: 1,
          from: "daily_screener",
          select: ["ticker", "close", "closeadj"],
          where: { type: "all", items: [] },
          order_by: [{ field: "close", direction: "desc" }],
          limit_per_day: 1,
        },
      };
    }
    const lineage =
      !isManualOrCoarse && universeChoice.kind === "preset" && selectedPreset
        ? {
            studio_screen_id: `preset:${selectedPreset.id}`,
            studio_screen_name: selectedPreset.label,
          }
        : !isManualOrCoarse && universeChoice.kind === "saved" && selectedSavedScreen
          ? {
              studio_screen_id: selectedSavedScreen.id,
              studio_screen_name: selectedSavedScreen.name,
            }
          : savedScreenId != null && linkedScreenName
            ? {
                studio_screen_id: savedScreenId,
                studio_screen_name: linkedScreenName,
              }
            : undefined;
    return {
      framework: (assembledFramework as unknown as Record<string, unknown>) ?? undefined,
      universe,
      title: title.trim() || undefined,
      ...(lineage ? { lineage } : {}),
    };
  }, [
    universeReady,
    pipelineSpec,
    evaluationConfig.start_date,
    evaluationConfig.end_date,
    evaluationConfig.initial_cash,
    evaluationConfig.benchmark,
    isManualOrCoarse,
    universeChoice,
    inlineSpec,
    assembledFramework,
    title,
    selectedSavedScreen,
    selectedPreset,
    savedScreenId,
    linkedScreenName,
  ]);

  const debouncedComposePayload = useDebouncedValue(
    composePayload,
    COMPOSE_DEBOUNCE_MS,
  );
  const debouncedPayloadKey = debouncedComposePayload
    ? JSON.stringify(debouncedComposePayload)
    : "";

  useEffect(() => {
    if (!debouncedComposePayload) {
      setComposeResult(null);
      return;
    }
    let cancelled = false;
    setComposeError(null);
    void composeBacktest(debouncedComposePayload)
      .then((result) => {
        if (cancelled) return;
        setComposeResult(result);
        if (!irIdTouched && result.ir_id_suggested) {
          setIrId(result.ir_id_suggested);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setComposeResult(null);
        setComposeError(
          err instanceof Error ? err.message : "Compose failed",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedPayloadKey, debouncedComposePayload, irIdTouched]);

  // Compile VeraBase.Universe → ClickHouse SQL beside Preview JSON.
  useEffect(() => {
    const spec = composeResult?.spec as Record<string, unknown> | undefined;
    const vb = (spec?.VeraBase ?? spec?.vera_base) as
      | { Universe?: UniverseQueryV1 }
      | undefined;
    const uni = vb?.Universe;
    if (!uni || typeof uni !== "object") {
      setUniverseSql(null);
      setUniverseSqlParams(null);
      setUniverseSqlError(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void compileUniverseSql({ spec: uni })
        .then((out) => {
          if (cancelled) return;
          setUniverseSql(out.sql);
          setUniverseSqlParams(out.params);
          setUniverseSqlError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setUniverseSql(null);
          setUniverseSqlParams(null);
          setUniverseSqlError(err instanceof Error ? err.message : String(err));
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [composeResult?.spec]);

  const saveMutation = useMutation({
    mutationFn: saveBacktestSpec,
  });

  const submitMutation = useMutation({
    mutationFn: submitBacktest,
  });

  const launchOptimizerMutation = useMutation({
    mutationFn: launchOptimizerSession,
  });

  const handleLaunchSweep = useCallback(
    async (req: LaunchOptimizerRequest) => {
      setActionError(null);
      try {
        if (composeResult?.spec) {
          const sweepSpec = stampEvaluation(composeResult.spec, {
            start_date: evaluationConfig.start_date,
            end_date: evaluationConfig.end_date,
            initial_cash: evaluationConfig.initial_cash,
            benchmark: evaluationConfig.benchmark,
          });

          await saveMutation.mutateAsync({
            ir_id: irId.trim() || req.base_ir_id,
            title: title.trim() || "Optimized Strategy Spec",
            spec: sweepSpec,
            pipeline_document: (authoredPipelineRef.current ?? authoredPipeline) ?? undefined,
            expected_hash: specHash ?? undefined,
          });
          setComposeDirty(false);
        }

        await launchOptimizerMutation.mutateAsync(req);
        setSweepModalOpen(false);
        void queryClient.invalidateQueries({ queryKey: ["optimizer-sessions"] });
        onNavigateToOptimize?.();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "Sweep launch failed");
      }
    },
    [composeResult, irId, title, evaluationConfig, saveMutation, launchOptimizerMutation, queryClient, onNavigateToOptimize, authoredPipeline, specHash],
  );

  const handleRunBacktest = useCallback(async (overrides?: {
    start_date?: string;
    end_date?: string;
  }) => {
    const cfg = { ...evaluationConfig, ...(overrides ?? {}) };
    setActionError(null);
    if (!composeResult?.spec) {
      setActionError("Compose a valid spec before running.");
      return;
    }
    if (!irId.trim()) {
      setActionError("ir_id is required.");
      return;
    }
    if (!cfg.start_date || !cfg.end_date) {
      setActionError("Start and end dates are required.");
      return;
    }
    if (!composeResult.validation.ok) {
      setActionError(
        validationMessage(composeResult.validation) ?? "Spec validation failed.",
      );
      return;
    }

    // Branch 1: Optimization Sweep Strategy
    if (cfg.strategy === "optimization_sweep" && cfg.sweep) {
      const sweep = cfg.sweep;
      const xVals: number[] = [];
      let curX = sweep.param_x.min;
      while (curX <= sweep.param_x.max + 1e-6 && xVals.length < 30) {
        xVals.push(Number(curX.toFixed(4)));
        curX += sweep.param_x.step;
      }
      const yVals: number[] = [];
      if (sweep.use_param_y && sweep.param_y) {
        let curY = sweep.param_y.min;
        while (curY <= sweep.param_y.max + 1e-6 && yVals.length < 30) {
          yVals.push(Number(curY.toFixed(4)));
          curY += sweep.param_y.step;
        }
      }
      await handleLaunchSweep({
        base_ir_id: irId.trim(),
        start_date: cfg.start_date,
        end_date: cfg.end_date,
        param_x_name: sweep.param_x.name,
        param_x_values: xVals,
        param_y_name: sweep.use_param_y && sweep.param_y ? sweep.param_y.name : undefined,
        param_y_values: sweep.use_param_y && sweep.param_y ? yVals : undefined,
        title: title.trim() || undefined,
        objective: sweep.objective,
        strategy_type: sweep.strategy_type === "grid" ? "grid" : "euler",
        constraints: sweep.constraints,
        max_concurrent: sweep.max_concurrent,
        lean_project: leanProject,
      });
      return;
    }

    // Branch 2: Baseline Simulation
    try {
      const stamped = stampEvaluation(composeResult.spec, {
        start_date: cfg.start_date,
        end_date: cfg.end_date,
        initial_cash: cfg.initial_cash,
        benchmark: cfg.benchmark,
      });
      await saveMutation.mutateAsync({
        ir_id: irId.trim(),
        title: title.trim() || irId.trim(),
        spec: stamped,
        is_template: isTemplate,
        pipeline_document: (authoredPipelineRef.current ?? authoredPipeline) ?? undefined,
        expected_hash: specHash ?? undefined,
      });
      setComposeDirty(false);
      setLoadedSpec((prev) => ({
        ...(prev || {}),
        ir_id: irId.trim(),
        title: title.trim() || irId.trim(),
        is_template: isTemplate,
        spec: stamped,
        algorithm_json: JSON.stringify(stamped),
        pipeline_document:
          (authoredPipelineRef.current ?? authoredPipeline) ?? prev?.pipeline_document,
      }));
      onNavigateStrategy?.(irId.trim());
      const submitted = await submitMutation.mutateAsync({
        ir_id: irId.trim(),
        start_date: cfg.start_date,
        end_date: cfg.end_date,
        lean_project: leanProject,
        immediate: false,
        extra_env: evaluationExtraEnv(stamped),
      });
      setQueueFlash(
        `Queued job ${submitted.job_id.slice(0, 8)}… (${submitted.status})`,
      );
      void queryClient.invalidateQueries({ queryKey: ["backtest-jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["backtest-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["execution-health"] });
      onNavigateToRuns?.();
      return { job_id: submitted.job_id, status: submitted.status, ir_id: irId.trim(), start_date: cfg.start_date, end_date: cfg.end_date };
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Submit failed");
      throw err;
    }
  }, [
    composeResult,
    irId,
    title,
    evaluationConfig,
    leanProject,
    saveMutation,
    submitMutation,
    queryClient,
    onNavigateToRuns,
    handleLaunchSweep,
    authoredPipeline,
    specHash,
    isTemplate,
    onNavigateStrategy,
  ]);

  // Spec-watch: poll head; surface remote MCP updates for Accept/Dismiss (no silent overwrite).
  useEffect(() => {
    // Agent entry point (webmcp): compose the live draft and queue a backtest.
    return studioAgentBridge.registerAction(
      "submitStrategyBacktest",
      async (args: { start_date?: string; end_date?: string }) => {
        // Wait out the compose debounce so the latest draft edits are compiled.
        await new Promise((r) => setTimeout(r, 1500));
        return handleRunBacktest({
          start_date: args?.start_date,
          end_date: args?.end_date,
        });
      },
    );
  }, [handleRunBacktest]);

  useEffect(() => {
    const id = irId.trim();
    if (!id) return;
    let cancelled = false;
    const tick = () => {
      void fetchBacktestSpecHead(id)
        .then((head) => {
          if (cancelled) return;
          const next = head.ir_content_hash ?? null;
          if (!next) return;
          setSpecHash((prev) => {
            if (prev && next && prev !== next) {
              if (dismissedRemoteHash === next) return prev;
              setPendingRemote({
                hash: next,
                title: head.title,
                updated_at: head.updated_at,
              });
              return prev;
            }
            return prev ?? next;
          });
        })
        .catch(() => {
          /* ignore poll errors */
        });
    };
    tick();
    const timer = window.setInterval(tick, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [irId, dismissedRemoteHash]);

  const acceptRemoteUpdate = useCallback(async () => {
    const id = irId.trim();
    if (!id || !pendingRemote) return;
    if (composeDirty) {
      const ok = window.confirm(
        "Accepting will overwrite unsaved local edits with the remote strategy. Continue?",
      );
      if (!ok) return;
    }
    try {
      const detail = await fetchBacktestSpecDetail(id);
      applyLoadedDetail(detail as unknown as BacktestSpecSummary);
      setSpecHash(pendingRemote.hash);
      setPendingRemote(null);
      setDismissedRemoteHash(null);
      setQueueFlash("Accepted remote update (MCP/agent).");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to load remote update");
    }
  }, [irId, pendingRemote, composeDirty]);

  const dismissRemoteUpdate = useCallback(() => {
    if (pendingRemote) setDismissedRemoteHash(pendingRemote.hash);
    setPendingRemote(null);
  }, [pendingRemote]);

  const handleSaveStrategy = useCallback(
    async (options?: {
      forceNewVersion?: boolean;
      customId?: string;
      customTitle?: string;
      notes?: string;
    }) => {
      setActionError(null);
      const isFork = Boolean(options?.forceNewVersion || options?.customId);
      const id = (options?.customId || (isFork ? newStrategyIrId("strat") : irId)).trim() || newStrategyIrId();
      const saveTitle = (options?.customTitle || title).trim() || id;
      const pipelineToSave = authoredPipelineRef.current ?? authoredPipeline;
      if (!pipelineToSave?.stages?.length && !(pipelineToSave?.universe?.screen?.length)) {
        setActionError("Nothing to save — edit the pipeline (Universe/Alpha) first.");
        return;
      }
      try {
        // Compile from the live authored pipeline so AST / binding edits are what get stored.
        const compiled = await compilePipeline(pipelineToSave);
        const stamped = stampEvaluation(compiled, {
          start_date: evaluationConfig.start_date,
          end_date: evaluationConfig.end_date,
          initial_cash: evaluationConfig.initial_cash,
          benchmark: evaluationConfig.benchmark,
        });
        setPipelineSpec(compiled);
        const saved = await saveMutation.mutateAsync({
          ir_id: id,
          title: saveTitle,
          spec: stamped,
          is_template: isTemplate,
          notes: options?.notes,
          force_new_version: isFork,
          changelog_notes: options?.notes,
          pipeline_document: pipelineToSave as unknown as Record<string, unknown>,
          expected_hash: isFork ? undefined : (specHash ?? undefined),
        });
        // The server forks when the target spec already has backtest runs, so the
        // persisted id can differ from the one we asked for. Everything
        // downstream must follow what was actually written.
        const effectiveId = String(saved.ir_id || id);
        const autoForked = Boolean(saved.forked) && !isFork;
        setIrId(effectiveId);
        setIrIdTouched(true);
        setTitle(saveTitle);
        setComposeDirty(false);
        if (saved.ir_content_hash) setSpecHash(String(saved.ir_content_hash));

        // Confirm persistence from ClickHouse (not just local state).
        let confirmed: BacktestSpecSummary = {
          ir_id: effectiveId,
          title: saveTitle,
          is_template: isTemplate,
          ir_content_hash: saved.ir_content_hash ?? undefined,
          spec: stamped,
          algorithm_json: JSON.stringify(stamped),
          pipeline_document: pipelineToSave,
          has_pipeline: true,
          schema_status: "modern",
        };
        try {
          const detail = await fetchBacktestSpecDetail(effectiveId);
          if (detail) {
            confirmed = detail as unknown as BacktestSpecSummary;
            if (!detail.pipeline_document) {
              setActionError(
                "Save wrote algorithm JSON but pipeline_document is missing in ClickHouse — reload may lose AST edits.",
              );
            }
          }
        } catch {
          /* keep local confirmed */
        }
        applyLoadedDetail(confirmed);
        onNavigateStrategy?.(effectiveId);
        void queryClient.invalidateQueries({ queryKey: ["strategy-specs-library"] });
        void queryClient.invalidateQueries({ queryKey: ["strategy-runs-count", effectiveId] });
        setQueueFlash(
          autoForked
            ? `Created new version ${effectiveId} — ${id} already had backtest runs and was left untouched`
            : `Saved ${isTemplate ? "template" : "strategy"} ${effectiveId}`,
        );
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "Save failed");
        throw err;
      }
    },
    [
      irId,
      title,
      evaluationConfig,
      isTemplate,
      authoredPipeline,
      specHash,
      saveMutation,
      onNavigateStrategy,
      queryClient,
    ],
  );

  const validationOk = composeResult?.validation.ok ?? false;
  const executionReady = healthQuery.data?.ready ?? false;
  const canRunBacktest =
    Boolean(composeResult?.spec) &&
    validationOk &&
    Boolean(irId.trim()) &&
    Boolean(evaluationConfig.start_date && evaluationConfig.end_date) &&
    executionReady &&
    Boolean(healthQuery.data?.clickhouse);

  const whyCantRun = useMemo(() => {
    if (composeError) return `Compose failed: ${composeError}`;
    if (!composeResult?.spec) return "Waiting for successful compose…";
    if (!validationOk) {
      return (
        validationMessage(composeResult.validation) ?? "Spec validation failed"
      );
    }
    if (!irId.trim()) return "ir_id is required (wait for compose suggestion)";
    if (!evaluationConfig.start_date || !evaluationConfig.end_date) return "Start and end dates are required";
    if (!executionReady) {
      return (
        healthQuery.data?.messages?.join("; ") ||
        "Execution environment not ready"
      );
    }
    if (!healthQuery.data?.clickhouse) {
      return "Queue mode needs ClickHouse";
    }
    return null;
  }, [
    composeError,
    composeResult,
    validationOk,
    irId,
    evaluationConfig.start_date,
    evaluationConfig.end_date,
    executionReady,
    healthQuery.data,
  ]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto bg-surface-raised">

      <div className="mx-auto w-full max-w-7xl space-y-4 px-3 sm:px-6 py-4">





        <AlgorithmStudioView
          universeTitle={
            linkedScreenName ||
            (universeChoice.kind === "preset"
              ? selectedPreset?.label
              : selectedSavedScreen?.name) ||
            "Universe AST Screen"
          }
          universeCandidateCount={
            universeChoice.kind === "inline"
              ? (inlineSpec?.limit_per_day ?? 25)
              : undefined
          }
          universeChoice={universeChoice}
          onSelectUniverseChoice={setUniverseChoice}
          presets={backtestablePresets}
          savedScreens={savedScreens}
          // Screen AST (TT + named groups) lives on Universe; Alpha is score/signal.
          onChangeFramework={(fw) => {
            setAssembledFramework(fw);
            setActiveFrameworkSpec(fw);
            setComposeDirty(true);
          }}
          onChangeFullSpec={(spec) => {
            setPipelineSpec(spec);
            setComposeDirty(true);
          }}
          onChangeAuthoredPipeline={handleAuthoredPipelineChange}
          onSaveStrategy={() => void handleSaveStrategy()}
          onForkStrategy={async (newId, newTitle, notes) => {
            await handleSaveStrategy({
              forceNewVersion: true,
              customId: newId,
              customTitle: newTitle,
              notes,
            });
          }}
          activeRunsCount={activeRunsCount}
          saveStrategyPending={saveMutation.isPending}
          composeDirty={composeDirty}
          onLaunchBacktest={() => void handleRunBacktest()}
          onLaunchOptimizer={() => setSweepModalOpen(true)}
          evaluationConfig={evaluationConfig}
          onChangeEvaluationConfig={setEvaluationConfig}
          loadedSpec={loadedSpec}
          composeTitle={title}
          onChangeTitle={setTitle}
          onOpenSpecLibrary={() => setSpecLibraryOpen(true)}
          onOpenSaveTemplate={(fw) => {
            setActiveFrameworkSpec(fw);
            setSaveTemplateOpen(true);
          }}
        />

        <Section title="Identity">
          <div>
            <FieldLabel>Title</FieldLabel>
            <input
              type="text"
              className={textInputClassName()}
              placeholder="My screener backtest"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div>
            <FieldLabel>ir_id</FieldLabel>
            <input
              type="text"
              className={textInputClassName()}
              placeholder="Auto-filled from compose"
              value={irId}
              onChange={(e) => {
                setIrIdTouched(true);
                setIrId(e.target.value);
              }}
            />
          </div>
          <label className="flex items-center gap-2 text-[11px] text-ink-muted">
            <input
              type="checkbox"
              checked={isTemplate}
              onChange={(e) => {
                setIsTemplate(e.target.checked);
                setComposeDirty(true);
              }}
            />
            Template tag (Browse filter only — still editable)
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border border-accent bg-accent-soft px-2.5 py-1 text-[11px] font-semibold text-ink hover:opacity-90"
              onClick={() => void handleSaveStrategy()}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "Saving…" : "Save strategy"}
            </button>
          </div>
          {composeResult && !validationOk ? (
            <p className="text-[11px] text-warn">
              {validationMessage(composeResult.validation) ?? "Validation failed"}
            </p>
          ) : null}
          {composeError ? (
            <p className="text-[11px] text-danger">{composeError}</p>
          ) : null}
        </Section>

        <section className="rounded border border-line bg-surface px-3 py-3">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left"
            onClick={() => setPreviewOpen((o) => !o)}
            disabled={!composeResult?.spec}
          >
            <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
              Preview
            </span>
            <span className="text-[11px] text-ink-muted">
              {previewOpen ? "Collapse" : "Expand"}
            </span>
          </button>
          {previewOpen && composeResult?.spec ? (
            <div className="mt-2 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex gap-1">
                  <button
                    type="button"
                    className={`rounded border px-2 py-0.5 text-[10px] ${
                      previewTab === "json"
                        ? "border-accent bg-accent-soft text-ink"
                        : "border-line text-ink-muted hover:bg-surface-sunk"
                    }`}
                    onClick={() => setPreviewTab("json")}
                  >
                    JSON
                  </button>
                  <button
                    type="button"
                    className={`rounded border px-2 py-0.5 text-[10px] ${
                      previewTab === "sql"
                        ? "border-accent bg-accent-soft text-ink"
                        : "border-line text-ink-muted hover:bg-surface-sunk"
                    }`}
                    onClick={() => setPreviewTab("sql")}
                  >
                    SQL
                  </button>
                </div>
                {previewTab === "sql" && universeSql ? (
                  <button
                    type="button"
                    className="rounded border border-line px-2 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
                    onClick={() => {
                      void navigator.clipboard?.writeText(universeSql);
                    }}
                  >
                    Copy SQL
                  </button>
                ) : null}
              </div>
              {previewTab === "json" ? (
                <pre className="max-h-80 overflow-auto rounded border border-line bg-surface-sunk p-2 font-mono text-[10px] text-ink-muted">
                  {JSON.stringify(composeResult.spec, null, 2)}
                </pre>
              ) : universeSqlError ? (
                <p className="rounded border border-warn/40 bg-warn/10 px-2 py-1.5 text-[11px] text-warn">
                  {universeSqlError}
                </p>
              ) : universeSql ? (
                <>
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-line bg-surface-sunk p-2 font-mono text-[10px] leading-relaxed text-ink-muted">
                    {universeSql}
                  </pre>
                  {universeSqlParams && Object.keys(universeSqlParams).length > 0 ? (
                    <pre className="max-h-28 overflow-auto rounded border border-line/70 bg-surface p-1.5 font-mono text-[9px] text-ink-faint">
                      {JSON.stringify(universeSqlParams, null, 2)}
                    </pre>
                  ) : null}
                </>
              ) : (
                <p className="text-[11px] text-ink-muted">
                  No VeraBase.Universe on this compose result yet.
                </p>
              )}
            </div>
          ) : null}
        </section>

        {pendingRemote ? (
          <div className="rounded border border-accent/40 bg-accent-soft px-3 py-2 text-[12px] text-ink">
            <p className="font-semibold">Remote update available (MCP/agent)</p>
            <p className="mt-0.5 text-[11px] text-ink-muted">
              Hash {pendingRemote.hash.slice(0, 12)}…
              {pendingRemote.updated_at ? ` · ${pendingRemote.updated_at}` : ""}
              {composeDirty ? " · local edits will be overwritten on Accept" : ""}
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                className="rounded bg-accent px-2.5 py-1 text-[11px] font-semibold text-accent-fg"
                onClick={() => void acceptRemoteUpdate()}
              >
                Accept
              </button>
              <button
                type="button"
                className="rounded border border-line px-2.5 py-1 text-[11px] text-ink-muted hover:bg-surface-sunk"
                onClick={dismissRemoteUpdate}
              >
                Dismiss
              </button>
            </div>
          </div>
        ) : null}

        {actionError ? (
          <div className="rounded border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger">
            {actionError}
          </div>
        ) : null}

        {queueFlash ? (
          <div className="rounded border border-accent/30 bg-accent-soft px-3 py-2 text-[12px] text-ink">
            {queueFlash}
          </div>
        ) : null}

        {composeError ? (
          <div className="rounded border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger">
            Compose failed: {composeError}.
          </div>
        ) : null}

        {whyCantRun && !canRunBacktest && !composeError ? (
          <p className="text-[11px] text-ink-muted">{whyCantRun}</p>
        ) : null}
      </div>

      {/* Strategy Spec & Template Library Dialog */}
      <SpecLibraryModal
        isOpen={specLibraryOpen}
        onClose={() => setSpecLibraryOpen(false)}
        onSelectSpec={(spec) => {
          const catalogId =
            typeof spec.catalog_template_id === "string" ? spec.catalog_template_id : "";
          if (catalogId) {
            void (async () => {
              setActionError(null);
              try {
                let body: PipelineDocument | null = null;
                try {
                  const rec = await fetchCatalogTemplate(catalogId);
                  if (rec.kind === "strategy" && rec.body && typeof rec.body === "object") {
                    body = rec.body as PipelineDocument;
                  }
                } catch {
                  body = null;
                }
                if (!body) body = await fetchStrategyPreset(catalogId);
                const compiled = await compilePipeline(body);
                const newId = newStrategyIrId("strat");
                const newTitle = body.strategy_name || spec.title || catalogId;
                const stamped = stampEvaluation(compiled as Record<string, unknown>, {
                  start_date: evaluationConfig.start_date,
                  end_date: evaluationConfig.end_date,
                  initial_cash: evaluationConfig.initial_cash,
                  benchmark: evaluationConfig.benchmark,
                });
                const saved = await saveMutation.mutateAsync({
                  ir_id: newId,
                  title: newTitle,
                  spec: stamped,
                  is_template: false,
                  pipeline_document: body,
                });
                applyLoadedDetail({
                  ir_id: newId,
                  title: newTitle,
                  is_template: false,
                  algorithm_json: JSON.stringify(compiled),
                  spec: compiled,
                  pipeline_document: body,
                  ir_content_hash: saved.ir_content_hash,
                });
                setPipelineSpec(compiled as Record<string, unknown>);
                onNavigateStrategy?.(newId);
                void queryClient.invalidateQueries({ queryKey: ["strategy-specs-library"] });
              } catch (err) {
                setActionError(err instanceof Error ? err.message : "Open catalog failed");
              }
            })();
            return;
          }
          if (spec.ir_id) {
            onNavigateStrategy?.(spec.ir_id);
          }
        }}
        onDuplicateSpec={(spec) => {
          void (async () => {
            setActionError(null);
            try {
              const catalogId =
                typeof spec.catalog_template_id === "string" ? spec.catalog_template_id : "";
              let detail: BacktestSpecSummary = spec;
              let pipeline: PipelineDocument | null = null;
              let compiled: Record<string, unknown> | null = null;

              if (catalogId) {
                let body: PipelineDocument | null = null;
                try {
                  const rec = await fetchCatalogTemplate(catalogId);
                  if (rec.kind === "strategy" && rec.body && typeof rec.body === "object") {
                    body = rec.body as PipelineDocument;
                  }
                } catch {
                  body = null;
                }
                if (!body) body = await fetchStrategyPreset(catalogId);
                pipeline = body;
                compiled = (await compilePipeline(body)) as Record<string, unknown>;
              } else if (spec.ir_id) {
                detail = (await fetchBacktestSpecDetail(spec.ir_id)) as unknown as BacktestSpecSummary;
                if (detail.pipeline_document && typeof detail.pipeline_document === "object") {
                  pipeline = detail.pipeline_document as PipelineDocument;
                }
                if (detail.spec && typeof detail.spec === "object") {
                  compiled = detail.spec as Record<string, unknown>;
                } else if (detail.algorithm_json) {
                  compiled = JSON.parse(String(detail.algorithm_json)) as Record<string, unknown>;
                }
              }

              if (!compiled) {
                setActionError("Clone failed: no algorithm JSON on source");
                return;
              }
              const newId = newStrategyIrId("clone");
              const newTitle = `Copy of ${detail.title || spec.title || newId}`;
              const stamped = stampEvaluation(compiled, {
                start_date: evaluationConfig.start_date,
                end_date: evaluationConfig.end_date,
                initial_cash: evaluationConfig.initial_cash,
                benchmark: evaluationConfig.benchmark,
              });
              const saved = await saveMutation.mutateAsync({
                ir_id: newId,
                title: newTitle,
                spec: stamped,
                is_template: Boolean(detail.is_template),
                pipeline_document: pipeline ?? undefined,
              });
              applyLoadedDetail({
                ...detail,
                ir_id: newId,
                title: newTitle,
                is_template: Boolean(detail.is_template),
                spec: compiled,
                algorithm_json: JSON.stringify(compiled),
                pipeline_document: pipeline ?? detail.pipeline_document,
                ir_content_hash: saved.ir_content_hash,
              });
              onNavigateStrategy?.(newId);
              void queryClient.invalidateQueries({ queryKey: ["strategy-specs-library"] });
            } catch (err) {
              setActionError(err instanceof Error ? err.message : "Clone failed");
            }
          })();
        }}
      />

      {/* Save Strategy Template Dialog */}
      <SaveStrategyTemplateModal
        isOpen={saveTemplateOpen}
        onClose={() => setSaveTemplateOpen(false)}
        compiledSpec={pipelineSpec}
        assembledSpec={activeFrameworkSpec || assembledFramework || {
          UniverseSelection: { Type: "VeraScreenerUniverseSelectionModel", Parameters: {} },
          Alpha: { Type: "VeraPyramidAlphaModel", Parameters: {} },
          PortfolioConstruction: { Type: "RiskBudgetedPortfolioConstructionModel", Parameters: {} },
          RiskManagement: { Type: "SwingProgressiveRiskManagementModel", Parameters: {} },
          Execution: { Type: "VeraScreenerExecutionModel", Parameters: {} },
        }}
        evaluationConfig={evaluationConfig}
        currentTitle={title || loadedSpec?.title || "Custom Strategy Template"}
        pipelineDocument={authoredPipeline}
        onSaved={(newIrId, newTitle) => {
          setIrId(newIrId);
          setTitle(newTitle);
          setIsTemplate(true);
          setLoadedSpec({
            ir_id: newIrId,
            title: newTitle,
            is_template: true,
            category: "Custom Template",
          });
          onNavigateStrategy?.(newIrId);
        }}
      />

      {/* Optimization Sweep Modal */}
      <OptimizerSweepModal
        specs={loadedSpec ? [loadedSpec] : [{ ir_id: irId || "custom-spec", title: title || "Current Spec", is_template: false }]}
        isOpen={sweepModalOpen}
        onClose={() => setSweepModalOpen(false)}
        isLaunching={launchOptimizerMutation.isPending}
        initialIrId={irId || loadedSpec?.ir_id}
        initialTitle={title || loadedSpec?.title}
        initialStartDate={evaluationConfig.start_date}
        initialEndDate={evaluationConfig.end_date}
        onLaunch={handleLaunchSweep}
      />
    </div>
  );
}
