import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchAsOfRange } from "../api/screens";
import {
  fetchBacktestSpecDetail,
  fetchBacktestSpecHead,
  saveBacktestSpec,
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
  SavedScreen,
  ScreenPreset,
  UniverseQueryV1,
} from "../types";

import { AlgorithmStudioView, type AssembledFrameworkSpec } from "./workbench/AlgorithmStudioView";
import { SpecLibraryModal } from "./workbench/SpecLibraryModal";
import { SaveStrategyTemplateModal } from "./workbench/SaveStrategyTemplateModal";
import { exitRulesFromDoc, patchExitRules } from "../lib/pipelineSlotBindings";
import { parseRules } from "../lib/rulesAst";
import { Button } from "@sb/webapp-core/components/ui/button";

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

function yearBackStart(datesDesc: string[]): string {
  if (datesDesc.length === 0) return "";
  const idx = Math.min(datesDesc.length - 1, 251);
  return datesDesc[idx] ?? datesDesc[datesDesc.length - 1]!;
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

export function BacktestComposePanel({
  savedScreens,
  savedScreenId,
  liveSpec,
  backtestPrefill,
  presets = [],
  initialSpec,
  routeStrategyIrId = null,
  onNavigateStrategy,
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
}) {
  const [universeChoice, setUniverseChoice] = useState<UniverseChoice>(() =>
    initialUniverseChoice(savedScreens, savedScreenId, liveSpec, backtestPrefill),
  );
  const [title, setTitle] = useState("");
  const [strategyNotes, setStrategyNotes] = useState(initialSpec?.notes ?? "");
  const [irId, setIrId] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [queueFlash, setQueueFlash] = useState<string | null>(null);

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
    setStrategyNotes(detail.notes ?? "");
    if (detail.ir_id) {
      setIrId(detail.ir_id);
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
      setStrategyNotes(initialSpec.notes ?? "");
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
              setStrategyNotes(detail.notes ?? "");
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

  const datesQuery = useQuery({
    queryKey: ["as-of-range-compose"],
    queryFn: () => fetchAsOfRange(10000),
    staleTime: 5 * 60_000,
  });

  const datesDesc = datesQuery.data ?? [];
  const asOfDate = datesDesc[0] ?? "";
  const chartStartDate = yearBackStart(datesDesc);

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

  const saveMutation = useMutation({
    mutationFn: saveBacktestSpec,
  });

  // Spec-watch: poll head; surface remote MCP updates for Accept/Dismiss (no silent overwrite).
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
      changelogNotes?: string;
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
        setPipelineSpec(compiled);
        const saved = await saveMutation.mutateAsync({
          ir_id: id,
          title: saveTitle,
          spec: compiled,
          is_template: isTemplate,
          notes: strategyNotes,
          force_new_version: isFork,
          changelog_notes: options?.changelogNotes,
          pipeline_document: pipelineToSave as unknown as Record<string, unknown>,
          expected_hash: isFork ? undefined : (specHash ?? undefined),
        });
        // The server forks when the target spec already has backtest runs, so the
        // persisted id can differ from the one we asked for. Everything
        // downstream must follow what was actually written.
        const effectiveId = String(saved.ir_id || id);
        const autoForked = Boolean(saved.forked) && !isFork;
        setIrId(effectiveId);
        setTitle(saveTitle);
        setComposeDirty(false);
        if (saved.ir_content_hash) setSpecHash(String(saved.ir_content_hash));

        // Confirm persistence from ClickHouse (not just local state).
        let confirmed: BacktestSpecSummary = {
          ir_id: effectiveId,
          title: saveTitle,
          is_template: isTemplate,
          ir_content_hash: saved.ir_content_hash ?? undefined,
          spec: compiled,
          algorithm_json: JSON.stringify(compiled),
          pipeline_document: pipelineToSave,
          has_pipeline: true,
          schema_status: "modern",
          notes: strategyNotes,
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
      isTemplate,
      authoredPipeline,
      specHash,
      saveMutation,
      onNavigateStrategy,
      queryClient,
      strategyNotes,
    ],
  );

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
          onSelectUniverseChoice={setUniverseChoice}
          presets={backtestablePresets}
          savedScreens={savedScreens}
          asOfDate={asOfDate}
          startDate={chartStartDate}
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
              changelogNotes: notes,
            });
          }}
          saveStrategyPending={saveMutation.isPending}
          composeDirty={composeDirty}
          loadedSpec={loadedSpec}
          composeTitle={title}
          onChangeTitle={setTitle}
          strategyNotes={strategyNotes}
          onChangeStrategyNotes={(notes) => {
            setStrategyNotes(notes);
            setComposeDirty(true);
          }}
          composeIrId={irId}
          onChangeIrId={(value) => {
            setIrId(value);
            setComposeDirty(true);
          }}
          isTemplate={isTemplate}
          onChangeIsTemplate={(value) => {
            setIsTemplate(value);
            setComposeDirty(true);
          }}
          onOpenSpecLibrary={() => setSpecLibraryOpen(true)}
          onOpenSaveTemplate={(fw) => {
            setActiveFrameworkSpec(fw);
            setSaveTemplateOpen(true);
          }}
        />

        {pendingRemote ? (
          <div className="rounded border border-accent/40 bg-accent-soft px-3 py-2 text-[12px] text-ink">
            <p className="font-semibold">Remote update available (MCP/agent)</p>
            <p className="mt-0.5 text-[11px] text-ink-muted">
              Hash {pendingRemote.hash.slice(0, 12)}…
              {pendingRemote.updated_at ? ` · ${pendingRemote.updated_at}` : ""}
              {composeDirty ? " · local edits will be overwritten on Accept" : ""}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => void acceptRemoteUpdate()}
              >
                Accept
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={dismissRemoteUpdate}
              >
                Dismiss
              </Button>
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
                const saved = await saveMutation.mutateAsync({
                  ir_id: newId,
                  title: newTitle,
                  spec: compiled as Record<string, unknown>,
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
              const saved = await saveMutation.mutateAsync({
                ir_id: newId,
                title: newTitle,
                spec: compiled,
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

    </div>
  );
}
