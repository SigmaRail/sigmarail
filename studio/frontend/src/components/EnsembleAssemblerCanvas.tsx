import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  deleteFrameworkTemplate,
  fetchFrameworkTemplates,
  saveFrameworkTemplate,
  updateFrameworkTemplate,
} from "../api/backtests";
import { cn } from "../lib/utils";
import type { StrategyFrameworkTemplate } from "../types";

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

interface EnsembleAssemblerCanvasProps {
  universeTitle?: string;
  universeCandidateCount?: number;
  initialFramework?: Record<string, any>;
  onChangeFramework: (framework: AssembledFrameworkSpec) => void;
}

export function EnsembleAssemblerCanvas({
  universeTitle = "Linked Screen",
  universeCandidateCount,
  onChangeFramework,
}: EnsembleAssemblerCanvasProps) {
  const queryClient = useQueryClient();

  // Active template state
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | number>("multi_alpha_ensemble");
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveCategory, setSaveCategory] = useState("Custom");
  const [saveDescription, setSaveDescription] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  // Alpha models state
  const [alphaScreener, setAlphaScreener] = useState(true);
  const [screenerMaxPositions, setScreenerMaxPositions] = useState(10);
  const [screenerStopLoss, setScreenerStopLoss] = useState(0.08);

  const [alphaRsi, setAlphaRsi] = useState(true);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [rsiResolution, setRsiResolution] = useState("Daily");

  const [alphaMacd, setAlphaMacd] = useState(false);
  const [macdFast, setMacdFast] = useState(12);
  const [macdSlow, setMacdSlow] = useState(26);
  const [macdSignal, setMacdSignal] = useState(9);

  const [alphaEmaCross, setAlphaEmaCross] = useState(false);
  const [emaFast, setEmaFast] = useState(10);
  const [emaSlow, setEmaSlow] = useState(50);

  // PCM state
  const [pcmType, setPcmType] = useState<string>(
    "ConfidenceWeightedPortfolioConstructionModel",
  );
  const [pcmMaxWeight, setPcmMaxWeight] = useState(0.15);
  const [pcmAtrRisk, setPcmAtrRisk] = useState(0.004);
  const [pcmRebalance, setPcmRebalance] = useState("Daily");

  // Risk layers state
  const [riskTrailing, setRiskTrailing] = useState(true);
  const [trailingStopPct, setTrailingStopPct] = useState(0.05);

  const [riskSectorCap, setRiskSectorCap] = useState(true);
  const [maxSectorExposure, setMaxSectorExposure] = useState(0.25);

  const [riskMaxDrawdown, setRiskMaxDrawdown] = useState(false);
  const [maxDrawdownPct, setMaxDrawdownPct] = useState(0.08);

  const [riskTakeProfit, setRiskTakeProfit] = useState(false);
  const [takeProfitPct, setTakeProfitPct] = useState(0.20);

  // Execution model state
  const [executionType, setExecutionType] = useState(
    "VolumeWeightedAveragePriceExecutionModel",
  );

  // JSON Preview Drawer
  const [isJsonDrawerOpen, setIsJsonDrawerOpen] = useState(false);

  // Fetch templates from API
  const templatesQuery = useQuery({
    queryKey: ["framework-templates"],
    queryFn: fetchFrameworkTemplates,
  });

  const templates: StrategyFrameworkTemplate[] = templatesQuery.data?.templates ?? [];

  const activeTemplate = useMemo(() => {
    return templates.find((t) => String(t.id) === String(selectedTemplateId)) ?? null;
  }, [templates, selectedTemplateId]);

  // Save template mutation
  const saveMutation = useMutation({
    mutationFn: saveFrameworkTemplate,
    onSuccess: (newTemplate) => {
      void queryClient.invalidateQueries({ queryKey: ["framework-templates"] });
      setSelectedTemplateId(newTemplate.id);
      setIsSaveModalOpen(false);
      setSaveName("");
      setSaveDescription("");
      setSaveCategory("Custom");
      setSaveError(null);
    },
    onError: (err: any) => {
      setSaveError(err?.message || "Failed to save template");
    },
  });

  // Update template mutation
  const updateMutation = useMutation({
    mutationFn: (payload: { id: string | number; framework: any }) =>
      updateFrameworkTemplate(payload.id, { framework: payload.framework }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["framework-templates"] });
    },
  });

  // Delete template mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string | number) => deleteFrameworkTemplate(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["framework-templates"] });
      setSelectedTemplateId("multi_alpha_ensemble");
    },
  });

  // Load a template into state
  const applyTemplate = (t: StrategyFrameworkTemplate) => {
    setSelectedTemplateId(t.id);
    const fw = t.framework as any;
    if (!fw) return;

    // Alpha
    if (fw.alpha) {
      setAlphaScreener(Boolean(fw.alpha.use_screener));
      if (fw.alpha.screener_max_positions != null) setScreenerMaxPositions(fw.alpha.screener_max_positions);
      if (fw.alpha.screener_stop_loss_pct != null) setScreenerStopLoss(fw.alpha.screener_stop_loss_pct);
      setAlphaRsi(Boolean(fw.alpha.use_rsi));
      if (fw.alpha.rsi_period != null) setRsiPeriod(fw.alpha.rsi_period);
      if (fw.alpha.rsi_resolution != null) setRsiResolution(fw.alpha.rsi_resolution);
      setAlphaMacd(Boolean(fw.alpha.use_macd));
      setAlphaEmaCross(Boolean(fw.alpha.use_ema));
    }

    // PCM
    if (fw.pcm) {
      if (fw.pcm.engine) setPcmType(fw.pcm.engine);
      if (fw.pcm.max_weight != null) setPcmMaxWeight(fw.pcm.max_weight);
      if (fw.pcm.target_atr_risk != null) setPcmAtrRisk(fw.pcm.target_atr_risk);
      if (fw.pcm.rebalance) setPcmRebalance(fw.pcm.rebalance);
    }

    // Risk
    if (fw.risk) {
      setRiskTrailing(Boolean(fw.risk.use_trailing_stop));
      if (fw.risk.trailing_stop_pct != null) setTrailingStopPct(fw.risk.trailing_stop_pct);
      setRiskSectorCap(Boolean(fw.risk.use_sector_cap));
      if (fw.risk.max_sector_exposure != null) setMaxSectorExposure(fw.risk.max_sector_exposure);
      setRiskMaxDrawdown(Boolean(fw.risk.use_hard_stop));
      if (fw.risk.stop_loss_pct != null) setMaxDrawdownPct(fw.risk.stop_loss_pct);
      setRiskTakeProfit(Boolean(fw.risk.use_take_profit));
      if (fw.risk.take_profit_pct != null) setTakeProfitPct(fw.risk.take_profit_pct);
    }

    // Execution
    if (fw.execution && fw.execution.engine) {
      setExecutionType(fw.execution.engine);
    }
  };

  // Serializable framework state for template saving
  const currentSerializableFramework = useMemo(() => {
    return {
      alpha: {
        use_screener: alphaScreener,
        screener_max_positions: screenerMaxPositions,
        screener_stop_loss_pct: screenerStopLoss,
        use_rsi: alphaRsi,
        rsi_period: rsiPeriod,
        rsi_resolution: rsiResolution,
        use_macd: alphaMacd,
        macd_fast: macdFast,
        macd_slow: macdSlow,
        macd_signal: macdSignal,
        use_ema: alphaEmaCross,
        ema_fast: emaFast,
        ema_slow: emaSlow,
      },
      pcm: {
        engine: pcmType,
        max_weight: pcmMaxWeight,
        target_atr_risk: pcmAtrRisk,
        rebalance: pcmRebalance,
      },
      risk: {
        use_trailing_stop: riskTrailing,
        trailing_stop_pct: trailingStopPct,
        use_sector_cap: riskSectorCap,
        max_sector_exposure: maxSectorExposure,
        use_hard_stop: riskMaxDrawdown,
        stop_loss_pct: maxDrawdownPct,
        use_take_profit: riskTakeProfit,
        take_profit_pct: takeProfitPct,
      },
      execution: {
        engine: executionType,
      },
    };
  }, [
    alphaScreener,
    screenerMaxPositions,
    screenerStopLoss,
    alphaRsi,
    rsiPeriod,
    rsiResolution,
    alphaMacd,
    macdFast,
    macdSlow,
    macdSignal,
    alphaEmaCross,
    emaFast,
    emaSlow,
    pcmType,
    pcmMaxWeight,
    pcmAtrRisk,
    pcmRebalance,
    riskTrailing,
    trailingStopPct,
    riskSectorCap,
    maxSectorExposure,
    riskMaxDrawdown,
    maxDrawdownPct,
    riskTakeProfit,
    takeProfitPct,
    executionType,
  ]);

  // Active alphas count
  const activeAlphaCount = [
    alphaScreener,
    alphaRsi,
    alphaMacd,
    alphaEmaCross,
  ].filter(Boolean).length;

  // Active risk count
  const activeRiskCount = [
    riskTrailing,
    riskSectorCap,
    riskMaxDrawdown,
    riskTakeProfit,
  ].filter(Boolean).length;

  // Synthesize Framework Spec
  const frameworkSpec = useMemo<AssembledFrameworkSpec>(() => {
    // 1. Universe
    const uni = {
      Type: "VeraScreenerUniverseSelectionModel",
      Parameters: {},
    };

    // 2. Alpha
    const alphaSubmodels: Array<{ Type: string; Parameters: Record<string, unknown> }> = [];
    if (alphaScreener) {
      alphaSubmodels.push({
        Type: "VeraScreenerAlphaModel",
        Parameters: {
          max_positions: screenerMaxPositions,
          stop_loss_pct: screenerStopLoss,
        },
      });
    }
    if (alphaRsi) {
      alphaSubmodels.push({
        Type: "RsiAlphaModel",
        Parameters: {
          period: rsiPeriod,
          resolution: rsiResolution,
        },
      });
    }
    if (alphaMacd) {
      alphaSubmodels.push({
        Type: "MacdAlphaModel",
        Parameters: {
          fast_period: macdFast,
          slow_period: macdSlow,
          signal_period: macdSignal,
        },
      });
    }
    if (alphaEmaCross) {
      alphaSubmodels.push({
        Type: "EmaCrossAlphaModel",
        Parameters: {
          fast_period: emaFast,
          slow_period: emaSlow,
        },
      });
    }

    let alphaSlot: { Type: string; Parameters: Record<string, unknown> };
    if (alphaSubmodels.length > 1) {
      alphaSlot = {
        Type: "CompositeAlphaModel",
        Parameters: { models: alphaSubmodels },
      };
    } else if (alphaSubmodels.length === 1) {
      alphaSlot = alphaSubmodels[0];
    } else {
      alphaSlot = {
        Type: "VeraScreenerAlphaModel",
        Parameters: { max_positions: 10, stop_loss_pct: 0.08 },
      };
    }

    // 3. PCM
    const pcmParams: Record<string, unknown> = {
      max_positions: screenerMaxPositions,
      max_weight: pcmMaxWeight,
    };
    if (pcmType === "VeraScreenerPortfolioConstructionModel") {
      pcmParams.target_atr_risk = pcmAtrRisk;
      pcmParams.min_weight = 0.02;
    }
    if (
      pcmType.includes("Rebalance") ||
      pcmType === "EqualWeightingPortfolioConstructionModel" ||
      pcmType === "RiskParityPortfolioConstructionModel"
    ) {
      pcmParams.rebalance = pcmRebalance;
    }

    const pcmSlot = {
      Type: pcmType,
      Parameters: pcmParams,
    };

    // 4. Risk Management
    const riskSubmodels: Array<{ Type: string; Parameters: Record<string, unknown> }> = [];
    if (riskTrailing) {
      riskSubmodels.push({
        Type: "TrailingStopRiskManagementModel",
        Parameters: { maximum_drawdown_percent: trailingStopPct },
      });
    }
    if (riskSectorCap) {
      riskSubmodels.push({
        Type: "MaximumSectorExposureRiskManagementModel",
        Parameters: { maximum_sector_exposure: maxSectorExposure },
      });
    }
    if (riskMaxDrawdown) {
      riskSubmodels.push({
        Type: "MaximumDrawdownPercentPerSecurity",
        Parameters: { maximum_drawdown_percent: maxDrawdownPct },
      });
    }
    if (riskTakeProfit) {
      riskSubmodels.push({
        Type: "MaximumUnrealizedProfitPercentPerSecurity",
        Parameters: { maximum_unrealized_profit_percent: takeProfitPct },
      });
    }

    let riskSlot: { Type: string; Parameters: Record<string, unknown> };
    if (riskSubmodels.length > 1) {
      riskSlot = {
        Type: "CompositeRiskManagementModel",
        Parameters: { models: riskSubmodels },
      };
    } else if (riskSubmodels.length === 1) {
      riskSlot = riskSubmodels[0];
    } else {
      riskSlot = {
        Type: "NullRiskManagementModel",
        Parameters: {},
      };
    }

    // 5. Execution
    const exeSlot = {
      Type: executionType,
      Parameters: {},
    };

    return {
      UniverseSelection: uni,
      Alpha: alphaSlot,
      PortfolioConstruction: pcmSlot,
      RiskManagement: riskSlot,
      Execution: exeSlot,
    };
  }, [
    alphaScreener,
    screenerMaxPositions,
    screenerStopLoss,
    alphaRsi,
    rsiPeriod,
    rsiResolution,
    alphaMacd,
    macdFast,
    macdSlow,
    macdSignal,
    alphaEmaCross,
    emaFast,
    emaSlow,
    pcmType,
    pcmMaxWeight,
    pcmAtrRisk,
    pcmRebalance,
    riskTrailing,
    trailingStopPct,
    riskSectorCap,
    maxSectorExposure,
    riskMaxDrawdown,
    maxDrawdownPct,
    riskTakeProfit,
    takeProfitPct,
    executionType,
  ]);

  useEffect(() => {
    onChangeFramework(frameworkSpec);
  }, [frameworkSpec, onChangeFramework]);

  const handleSaveSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!saveName.trim()) {
      setSaveError("Template name is required");
      return;
    }
    saveMutation.mutate({
      name: saveName.trim(),
      description: saveDescription.trim(),
      category: saveCategory.trim() || "Custom",
      framework: currentSerializableFramework as any,
    });
  };

  const handleUpdateTemplate = () => {
    if (!activeTemplate || activeTemplate.is_system) return;
    updateMutation.mutate({
      id: activeTemplate.id,
      framework: currentSerializableFramework,
    });
  };

  const handleDeleteTemplate = () => {
    if (!activeTemplate || activeTemplate.is_system) return;
    if (window.confirm(`Delete template "${activeTemplate.name}"?`)) {
      deleteMutation.mutate(activeTemplate.id);
    }
  };

  return (
    <div className="space-y-4 rounded border border-line bg-surface p-4 shadow-sm">
      {/* Header & Template Manager Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3.5">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-[13px] font-bold text-ink">
              Interactive Ensemble Strategy Assembler
            </h3>
            <span className="rounded bg-accent/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-accent-ink">
              Zero-Code Model Builder
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-ink-muted">
            Assemble multi-alpha models, insight synthesis PCM, stacked risk defense, and execution into native QuantConnect LEAN classes.
          </p>
        </div>

        {/* Template Selector & Action Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Template Select Dropdown */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
              Template:
            </span>
            <select
              value={selectedTemplateId}
              onChange={(e) => {
                const found = templates.find((t) => String(t.id) === e.target.value);
                if (found) {
                  applyTemplate(found);
                } else {
                  setSelectedTemplateId(e.target.value);
                }
              }}
              className="rounded border border-line bg-surface-raised px-2.5 py-1 text-[11.5px] font-medium text-ink focus:border-accent focus:outline-none"
            >
              <optgroup label="⚡ Built-in System Blueprints">
                {templates
                  .filter((t) => t.is_system)
                  .map((t) => (
                    <option key={String(t.id)} value={String(t.id)}>
                      {t.name}
                    </option>
                  ))}
              </optgroup>
              {templates.some((t) => !t.is_system) && (
                <optgroup label="⭐ My Saved Templates">
                  {templates
                    .filter((t) => !t.is_system)
                    .map((t) => (
                      <option key={String(t.id)} value={String(t.id)}>
                        {t.name} ({t.category || "Custom"})
                      </option>
                    ))}
                </optgroup>
              )}
            </select>
          </div>

          {/* Save As Template Button */}
          <button
            type="button"
            onClick={() => setIsSaveModalOpen(true)}
            className="flex items-center gap-1 rounded border border-accent/40 bg-accent/10 px-2.5 py-1 text-[11px] font-semibold text-accent-ink hover:bg-accent/20 transition-colors"
            title="Save current canvas settings as a reusable template"
          >
            <span>💾</span>
            <span>Save Template</span>
          </button>

          {/* Update Button (Only for Custom Templates) */}
          {activeTemplate && !activeTemplate.is_system && (
            <button
              type="button"
              onClick={handleUpdateTemplate}
              disabled={updateMutation.isPending}
              className="flex items-center gap-1 rounded border border-line bg-surface-raised px-2 py-1 text-[11px] font-medium text-ink hover:border-accent transition-colors"
              title="Overwrite template with current settings"
            >
              <span>✏️</span>
              <span>{updateMutation.isPending ? "Saving..." : "Update"}</span>
            </button>
          )}

          {/* Delete Button (Only for Custom Templates) */}
          {activeTemplate && !activeTemplate.is_system && (
            <button
              type="button"
              onClick={handleDeleteTemplate}
              disabled={deleteMutation.isPending}
              className="flex items-center gap-1 rounded border border-danger/30 bg-danger/10 px-2 py-1 text-[11px] font-medium text-danger hover:bg-danger/20 transition-colors"
              title="Delete this custom template"
            >
              <span>🗑️</span>
            </button>
          )}
        </div>
      </div>

      {/* Active Template Description Banner */}
      {activeTemplate && (
        <div className="flex items-center justify-between rounded bg-surface-sunk/60 px-3 py-1.5 text-[10.5px]">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-ink">{activeTemplate.name}:</span>
            <span className="text-ink-muted">{activeTemplate.description || "Custom configuration"}</span>
          </div>
          <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-surface border border-line text-ink-faint">
            {activeTemplate.is_system ? "System Blueprint" : activeTemplate.category || "Custom"}
          </span>
        </div>
      )}

      {/* 5-Slot Visual Pipeline Header */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 text-[11px]">
        <div className="rounded border border-line/80 bg-surface-sunk p-2 text-center">
          <span className="font-mono text-[9.5px] uppercase font-bold text-ink-faint">1. Universe</span>
          <div className="mt-0.5 font-bold text-ink truncate">{universeTitle}</div>
          <span className="text-[9.5px] text-ink-muted">
            {universeCandidateCount != null ? `${universeCandidateCount} Candidates` : "Live AST Screen"}
          </span>
        </div>
        <div className="rounded border border-accent/60 bg-accent/5 p-2 text-center">
          <span className="font-mono text-[9.5px] uppercase font-bold text-accent">2. Alpha Composite</span>
          <div className="mt-0.5 font-bold text-accent-ink truncate">
            {activeAlphaCount > 1
              ? `Composite (${activeAlphaCount} Alphas)`
              : activeAlphaCount === 1
                ? "Single Alpha"
                : "None"}
          </div>
          <span className="text-[9.5px] text-accent-ink/80">Signal Generator</span>
        </div>
        <div className="rounded border border-line/80 bg-surface-sunk p-2 text-center">
          <span className="font-mono text-[9.5px] uppercase font-bold text-ink-faint">3. Portfolio (PCM)</span>
          <div className="mt-0.5 font-bold text-ink truncate">
            {pcmType === "ConfidenceWeightedPortfolioConstructionModel"
              ? "Confidence Weighted"
              : pcmType === "VeraScreenerPortfolioConstructionModel"
                ? "ATR Volatility Risk"
                : pcmType === "RiskParityPortfolioConstructionModel"
                  ? "Risk Parity (Inv-Vol)"
                  : "Equal Weighting"}
          </div>
          <span className="text-[9.5px] text-ink-muted">Insight Reconciliation</span>
        </div>
        <div className="rounded border border-line/80 bg-surface-sunk p-2 text-center">
          <span className="font-mono text-[9.5px] uppercase font-bold text-danger">4. Risk Defense</span>
          <div className="mt-0.5 font-bold text-danger truncate">
            {activeRiskCount > 1
              ? `Composite (${activeRiskCount} Layers)`
              : activeRiskCount === 1
                ? "Single Defense Layer"
                : "Unconstrained"}
          </div>
          <span className="text-[9.5px] text-ink-muted">Stacked Circuit Breakers</span>
        </div>
        <div className="rounded border border-line/80 bg-surface-sunk p-2 text-center col-span-2 sm:col-span-1">
          <span className="font-mono text-[9.5px] uppercase font-bold text-ink-faint">5. Execution</span>
          <div className="mt-0.5 font-bold text-ink truncate">
            {executionType.includes("Volume") ? "VWAP Intraday" : "Immediate / MOO"}
          </div>
          <span className="text-[9.5px] text-ink-muted">Market Order Slicer</span>
        </div>
      </div>

      {/* Main 2-Column Canvas Layout */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* Left Column: Multi-Alpha Models */}
        <div className="space-y-3 xl:col-span-6">
          <div className="flex items-center justify-between border-b border-line pb-1.5">
            <div>
              <span className="font-mono text-[10px] font-bold uppercase text-accent">Slot 2</span>
              <h4 className="text-[12px] font-bold text-ink">Alpha Models (Multi-Model Fusion)</h4>
            </div>
            <span className="font-mono text-[10px] text-ink-muted">
              {activeAlphaCount > 1 ? "CompositeAlphaModel" : "Single Alpha"}
            </span>
          </div>

          {/* Model 1: VeraScreener Alpha */}
          <div
            className={cn(
              "rounded border p-3 transition-all",
              alphaScreener ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60",
            )}
          >
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
                <input
                  type="checkbox"
                  checked={alphaScreener}
                  onChange={(e) => setAlphaScreener(e.target.checked)}
                  className="rounded border-line"
                />
                Vera Screener Breakout Alpha
              </label>
              <span className="font-mono text-[9px] text-ink-faint">VeraScreenerAlphaModel</span>
            </div>
            <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
              Emits directional long insights for universe candidates meeting relative strength criteria.
            </p>
            {alphaScreener && (
              <div className="mt-2.5 grid grid-cols-2 gap-2 border-t border-line/60 pt-2 text-[11px]">
                <div>
                  <label className="text-[10px] text-ink-faint block">Max Positions</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={screenerMaxPositions}
                    onChange={(e) => setScreenerMaxPositions(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-ink-faint block">
                    Stop Loss % ({(screenerStopLoss * 100).toFixed(1)}%)
                  </label>
                  <input
                    type="range"
                    min={0.02}
                    max={0.20}
                    step={0.01}
                    value={screenerStopLoss}
                    onChange={(e) => setScreenerStopLoss(Number(e.target.value))}
                    className="mt-1.5 w-full"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Model 2: RSI Alpha */}
          <div
            className={cn(
              "rounded border p-3 transition-all",
              alphaRsi ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60",
            )}
          >
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
                <input
                  type="checkbox"
                  checked={alphaRsi}
                  onChange={(e) => setAlphaRsi(e.target.checked)}
                  className="rounded border-line"
                />
                RSI Mean-Reversion Alpha
              </label>
              <span className="font-mono text-[9px] text-ink-faint">RsiAlphaModel</span>
            </div>
            <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
              Emits high-confidence buy insights on oversold pullbacks and exit signals on overbought extremes.
            </p>
            {alphaRsi && (
              <div className="mt-2.5 grid grid-cols-2 gap-2 border-t border-line/60 pt-2 text-[11px]">
                <div>
                  <label className="text-[10px] text-ink-faint block">RSI Period ({rsiPeriod} bars)</label>
                  <input
                    type="number"
                    min={2}
                    max={50}
                    value={rsiPeriod}
                    onChange={(e) => setRsiPeriod(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-ink-faint block">Resolution</label>
                  <select
                    value={rsiResolution}
                    onChange={(e) => setRsiResolution(e.target.value)}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  >
                    <option value="Daily">Daily</option>
                    <option value="Hour">Hour</option>
                    <option value="Minute">Minute</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Model 3: MACD Alpha */}
          <div
            className={cn(
              "rounded border p-3 transition-all",
              alphaMacd ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60",
            )}
          >
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
                <input
                  type="checkbox"
                  checked={alphaMacd}
                  onChange={(e) => setAlphaMacd(e.target.checked)}
                  className="rounded border-line"
                />
                MACD Trend Crossover Alpha
              </label>
              <span className="font-mono text-[9px] text-ink-faint">MacdAlphaModel</span>
            </div>
            <p className="mt-1 text-[10.5px] text-ink-muted leading-tight">
              Emits trend momentum insights based on MACD signal line crossovers.
            </p>
            {alphaMacd && (
              <div className="mt-2.5 grid grid-cols-3 gap-2 border-t border-line/60 pt-2 text-[11px]">
                <div>
                  <label className="text-[10px] text-ink-faint block">Fast Period</label>
                  <input
                    type="number"
                    min={2}
                    max={50}
                    value={macdFast}
                    onChange={(e) => setMacdFast(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-ink-faint block">Slow Period</label>
                  <input
                    type="number"
                    min={5}
                    max={100}
                    value={macdSlow}
                    onChange={(e) => setMacdSlow(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-ink-faint block">Signal Period</label>
                  <input
                    type="number"
                    min={2}
                    max={50}
                    value={macdSignal}
                    onChange={(e) => setMacdSignal(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Model 4: EMA Cross Alpha */}
          <div
            className={cn(
              "rounded border p-3 transition-all",
              alphaEmaCross ? "border-accent/60 bg-accent/5" : "border-line bg-surface-raised/40 opacity-60",
            )}
          >
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer font-bold text-[12px] text-ink">
                <input
                  type="checkbox"
                  checked={alphaEmaCross}
                  onChange={(e) => setAlphaEmaCross(e.target.checked)}
                  className="rounded border-line"
                />
                EMA Moving Average Crossover
              </label>
              <span className="font-mono text-[9px] text-ink-faint">EmaCrossAlphaModel</span>
            </div>
            {alphaEmaCross && (
              <div className="mt-2.5 grid grid-cols-2 gap-2 border-t border-line/60 pt-2 text-[11px]">
                <div>
                  <label className="text-[10px] text-ink-faint block">Fast EMA ({emaFast})</label>
                  <input
                    type="number"
                    min={2}
                    max={50}
                    value={emaFast}
                    onChange={(e) => setEmaFast(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-ink-faint block">Slow EMA ({emaSlow})</label>
                  <input
                    type="number"
                    min={10}
                    max={200}
                    value={emaSlow}
                    onChange={(e) => setEmaSlow(Number(e.target.value))}
                    className="mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-ink"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: PCM & Stacked Risk Defense & Execution */}
        <div className="space-y-4 lg:col-span-6">
          {/* SLOT 3: PORTFOLIO CONSTRUCTION (PCM) */}
          <div className="space-y-2.5 rounded border border-line bg-surface-raised/50 p-3">
            <div className="flex items-center justify-between border-b border-line/60 pb-1.5">
              <div>
                <span className="font-mono text-[10px] font-bold uppercase text-ink-faint">Slot 3</span>
                <h4 className="text-[12px] font-bold text-ink">Portfolio Construction Model (PCM)</h4>
              </div>
              <span className="text-[10px] text-ink-muted">Insight Reconciliation</span>
            </div>

            <div>
              <label className="text-[10.5px] font-semibold text-ink-faint block">PCM Model Engine</label>
              <select
                value={pcmType}
                onChange={(e) => setPcmType(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-surface px-2.5 py-1.5 text-[11.5px] font-medium text-ink focus:border-accent"
              >
                <option value="ConfidenceWeightedPortfolioConstructionModel">
                  Confidence-Weighted PCM (Native Multi-Alpha Blend)
                </option>
                <option value="VeraScreenerPortfolioConstructionModel">
                  Vera Screener PCM (ATR Volatility Risk Sizing)
                </option>
                <option value="RiskParityPortfolioConstructionModel">
                  Risk Parity PCM (Inverse-Volatility Sizing)
                </option>
                <option value="EqualWeightingPortfolioConstructionModel">
                  Equal Weighting PCM
                </option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <div className="flex justify-between text-[10px] text-ink-faint">
                  <span>Max Position Weight ({(pcmMaxWeight * 100).toFixed(0)}%)</span>
                </div>
                <input
                  type="range"
                  min={0.05}
                  max={0.50}
                  step={0.01}
                  value={pcmMaxWeight}
                  onChange={(e) => setPcmMaxWeight(Number(e.target.value))}
                  className="mt-1 w-full"
                />
              </div>
              <div>
                <label className="text-[10px] text-ink-faint block">Rebalance Frequency</label>
                <select
                  value={pcmRebalance}
                  onChange={(e) => setPcmRebalance(e.target.value)}
                  className="mt-1 w-full rounded border border-line bg-surface px-2 py-1 text-[11px] text-ink"
                >
                  <option value="Daily">Daily</option>
                  <option value="Weekly">Weekly</option>
                  <option value="Monthly">Monthly</option>
                </select>
              </div>
            </div>
          </div>

          {/* SLOT 4: STACKED RISK MANAGEMENT */}
          <div className="space-y-2.5 rounded border border-line bg-surface-raised/50 p-3">
            <div className="flex items-center justify-between border-b border-line/60 pb-1.5">
              <div>
                <span className="font-mono text-[10px] font-bold uppercase text-danger">Slot 4</span>
                <h4 className="text-[12px] font-bold text-ink">Stacked Risk Management Defense</h4>
              </div>
              <span className="font-mono text-[10px] text-danger">
                {activeRiskCount > 1 ? "CompositeRiskManagementModel" : "Active Layers"}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {/* Layer 1: Trailing Stop */}
              <div
                className={cn(
                  "rounded border p-2.5 transition-all",
                  riskTrailing ? "border-rose-500/50 bg-rose-500/5" : "border-line bg-surface opacity-75",
                )}
              >
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-1.5 cursor-pointer font-bold text-[11.5px] text-ink">
                    <input
                      type="checkbox"
                      checked={riskTrailing}
                      onChange={(e) => setRiskTrailing(e.target.checked)}
                      className="rounded border-line"
                    />
                    Trailing Stop Loss
                  </label>
                </div>
                {riskTrailing && (
                  <div className="mt-2 text-[10.5px]">
                    <div className="flex justify-between text-ink-faint">
                      <span>Max Peak Drawdown</span>
                      <span className="font-mono text-ink">{(trailingStopPct * 100).toFixed(1)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.02}
                      max={0.20}
                      step={0.01}
                      value={trailingStopPct}
                      onChange={(e) => setTrailingStopPct(Number(e.target.value))}
                      className="mt-1 w-full"
                    />
                  </div>
                )}
              </div>

              {/* Layer 2: Sector Exposure */}
              <div
                className={cn(
                  "rounded border p-2.5 transition-all",
                  riskSectorCap ? "border-rose-500/50 bg-rose-500/5" : "border-line bg-surface opacity-75",
                )}
              >
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-1.5 cursor-pointer font-bold text-[11.5px] text-ink">
                    <input
                      type="checkbox"
                      checked={riskSectorCap}
                      onChange={(e) => setRiskSectorCap(e.target.checked)}
                      className="rounded border-line"
                    />
                    Max Sector Exposure
                  </label>
                </div>
                {riskSectorCap && (
                  <div className="mt-2 text-[10.5px]">
                    <div className="flex justify-between text-ink-faint">
                      <span>Sector Cap</span>
                      <span className="font-mono text-ink">{(maxSectorExposure * 100).toFixed(0)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.10}
                      max={0.50}
                      step={0.05}
                      value={maxSectorExposure}
                      onChange={(e) => setMaxSectorExposure(Number(e.target.value))}
                      className="mt-1 w-full"
                    />
                  </div>
                )}
              </div>

              {/* Layer 3: Max Drawdown Security */}
              <div
                className={cn(
                  "rounded border p-2.5 transition-all",
                  riskMaxDrawdown ? "border-rose-500/50 bg-rose-500/5" : "border-line bg-surface opacity-75",
                )}
              >
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-1.5 cursor-pointer font-bold text-[11.5px] text-ink">
                    <input
                      type="checkbox"
                      checked={riskMaxDrawdown}
                      onChange={(e) => setRiskMaxDrawdown(e.target.checked)}
                      className="rounded border-line"
                    />
                    Hard Stop Loss
                  </label>
                </div>
                {riskMaxDrawdown && (
                  <div className="mt-2 text-[10.5px]">
                    <div className="flex justify-between text-ink-faint">
                      <span>Per-Security Loss</span>
                      <span className="font-mono text-ink">{(maxDrawdownPct * 100).toFixed(1)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.03}
                      max={0.20}
                      step={0.01}
                      value={maxDrawdownPct}
                      onChange={(e) => setMaxDrawdownPct(Number(e.target.value))}
                      className="mt-1 w-full"
                    />
                  </div>
                )}
              </div>

              {/* Layer 4: Take Profit */}
              <div
                className={cn(
                  "rounded border p-2.5 transition-all",
                  riskTakeProfit ? "border-rose-500/50 bg-rose-500/5" : "border-line bg-surface opacity-75",
                )}
              >
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-1.5 cursor-pointer font-bold text-[11.5px] text-ink">
                    <input
                      type="checkbox"
                      checked={riskTakeProfit}
                      onChange={(e) => setRiskTakeProfit(e.target.checked)}
                      className="rounded border-line"
                    />
                    Take Profit Target
                  </label>
                </div>
                {riskTakeProfit && (
                  <div className="mt-2 text-[10.5px]">
                    <div className="flex justify-between text-ink-faint">
                      <span>Unrealized Gain</span>
                      <span className="font-mono text-ink">+{(takeProfitPct * 100).toFixed(0)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.05}
                      max={0.50}
                      step={0.05}
                      value={takeProfitPct}
                      onChange={(e) => setTakeProfitPct(Number(e.target.value))}
                      className="mt-1 w-full"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* SLOT 5: EXECUTION MODEL */}
          <div className="space-y-2 rounded border border-line bg-surface-raised/50 p-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] font-bold uppercase text-ink-faint">Slot 5: Execution</span>
              <span className="text-[10px] text-ink-muted">Market Impact Control</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label
                className={cn(
                  "flex items-center gap-2 rounded border p-2 text-[11px] cursor-pointer",
                  executionType.includes("Volume")
                    ? "border-accent bg-accent/10 font-semibold text-accent-ink"
                    : "border-line bg-surface text-ink",
                )}
              >
                <input
                  type="radio"
                  name="execution"
                  checked={executionType === "VolumeWeightedAveragePriceExecutionModel"}
                  onChange={() => setExecutionType("VolumeWeightedAveragePriceExecutionModel")}
                />
                VWAP Execution (Intraday)
              </label>
              <label
                className={cn(
                  "flex items-center gap-2 rounded border p-2 text-[11px] cursor-pointer",
                  executionType === "ImmediateExecutionModel"
                    ? "border-accent bg-accent/10 font-semibold text-accent-ink"
                    : "border-line bg-surface text-ink",
                )}
              >
                <input
                  type="radio"
                  name="execution"
                  checked={executionType === "ImmediateExecutionModel"}
                  onChange={() => setExecutionType("ImmediateExecutionModel")}
                />
                Immediate / MOO
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Save Template Modal */}
      {isSaveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg border border-line bg-surface p-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <h3 className="text-[14px] font-bold text-ink">💾 Save Strategy Framework Template</h3>
              <button
                type="button"
                onClick={() => setIsSaveModalOpen(false)}
                className="text-ink-muted hover:text-ink text-[14px]"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveSubmit} className="mt-4 space-y-3.5">
              {saveError && (
                <div className="rounded bg-danger/10 border border-danger/30 p-2 text-[11px] text-danger">
                  {saveError}
                </div>
              )}

              <div>
                <label className="text-[11px] font-semibold text-ink-muted block">Template Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Quad-Alpha Defensive Momentum"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  className="mt-1 w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-[12px] text-ink focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-ink-muted block">Category</label>
                <input
                  type="text"
                  placeholder="e.g. Ensemble, Momentum, Risk Defense"
                  value={saveCategory}
                  onChange={(e) => setSaveCategory(e.target.value)}
                  className="mt-1 w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-[12px] text-ink focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-ink-muted block">Description</label>
                <textarea
                  rows={2}
                  placeholder="Brief description of this strategy framework combination..."
                  value={saveDescription}
                  onChange={(e) => setSaveDescription(e.target.value)}
                  className="mt-1 w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-[12px] text-ink focus:border-accent focus:outline-none"
                />
              </div>

              <div className="mt-5 flex justify-end gap-2 border-t border-line pt-3">
                <button
                  type="button"
                  onClick={() => setIsSaveModalOpen(false)}
                  className="rounded border border-line bg-surface px-3 py-1.5 text-[11.5px] font-medium text-ink hover:bg-surface-raised"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saveMutation.isPending}
                  className="rounded bg-accent px-4 py-1.5 text-[11.5px] font-semibold text-white hover:bg-accent/90 disabled:opacity-50"
                >
                  {saveMutation.isPending ? "Saving..." : "Save Template"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Collapsible Live JSON Document Preview */}
      <div className="rounded border border-line bg-surface-raised">
        <button
          type="button"
          onClick={() => setIsJsonDrawerOpen((o) => !o)}
          className="flex w-full items-center justify-between px-3 py-2 text-left text-[11px] font-semibold text-ink-muted hover:text-ink"
        >
          <span className="flex items-center gap-2 font-mono">
            <span>{isJsonDrawerOpen ? "▼" : "▶"}</span>
            <span>Live Canonical Spec: VeraLabV1 (LeanFrameworkV1)</span>
          </span>
          <span className="text-[10px] font-normal text-ink-faint">
            {isJsonDrawerOpen ? "Click to collapse" : "Click to view synthesized JSON"}
          </span>
        </button>

        {isJsonDrawerOpen && (
          <div className="border-t border-line bg-surface-sunk p-3 font-mono text-[10.5px]">
            <pre className="max-h-60 overflow-y-auto rounded bg-surface p-3 text-ink leading-relaxed">
              {JSON.stringify(
                {
                  SchemaVersion: 2,
                  Kind: "VeraLabV1",
                  Framework: frameworkSpec,
                },
                null,
                2,
              )}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
