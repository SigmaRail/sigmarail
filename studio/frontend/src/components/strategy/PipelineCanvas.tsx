import { useCallback, useMemo, useState } from "react";
import type { ScreenField } from "../../types";
import type {
  PipelineDocument,
  SlotExpr,
  Stage,
  StageMode,
} from "./StrategyDocument";
import type { PolicyRuleRole } from "./StrategyDocument";
import { ALPHA_ADD_MODES, CHAMPION_EXIT_TRANCHES } from "../../lib/pipelineSlotBindings";
import { StageBlock, STAGE_MODE_LABELS } from "./StageBlock";
import { AlphaMembershipProbe } from "../AlphaMembershipProbe";
import { AlphaMeasuresPanel } from "../studio/AlphaMeasuresPanel";
import { AlphaInsightsPanel } from "../studio/AlphaInsightsPanel";
import { AlphaFactorPerformancePanel } from "../studio/AlphaFactorPerformancePanel";
import { upsertPolicyRuleForBinding } from "../studio/PolicyRulesPanel";
import { insightsFieldCatalog } from "../../lib/insightsFieldCatalog";

const ALPHA_MODES: StageMode[] = [...ALPHA_ADD_MODES];
const ALL_MODES: StageMode[] = [...ALPHA_MODES, "hedge", "exit"];

const EMPTY_STAGE: Record<StageMode, Omit<Stage, "mode">> = {
  filter: { name: "Filter", filters: [], max_candidates: 101 },
  score: { name: "Rank", factors: [], selection: { method: "top_n", n: 10 } },
  signal: { name: "Entry Signal", entry_triggers: [] },
  confirm: { name: "Confirm Gate", filters: [], max_candidates: 50 },
  watch: { name: "Watchlist", factors: [], selection: { method: "top_n", n: 30 } },
  pyramid: {
    name: "Progressive Exposure",
    add_trigger_pct: 0.02,
    phases: [
      { name: "test", size_pct: 0.5 },
      { name: "add", size_pct: 0.25 },
      { name: "full", size_pct: 0.25 },
    ],
  },
  hedge: { name: "Market Hedge", instruments: [{ ticker: "SH", max_allocation: 0.25 }] },
  exit: { name: "Sell Into Strength", tranches: CHAMPION_EXIT_TRANCHES },
};

function patchAlphaBinding(
  doc: PipelineDocument,
  patch: Partial<NonNullable<PipelineDocument["bindings"]>>,
): PipelineDocument {
  let rules = doc.policy_rules ?? [];
  const roles: PolicyRuleRole[] = [
    "alpha_eligibility",
    "alpha_setup",
    "alpha_confidence",
  ];
  for (const role of roles) {
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

interface PipelineCanvasProps {
  document: PipelineDocument;
  onChange: (doc: PipelineDocument) => void;
  fields?: ScreenField[];
  /** Alpha card: Measures + Insights only (default true). */
  alphaOnly?: boolean;
  hideUniverseConfig?: boolean;
  asOf?: string;
  startDate?: string;
  /**
   * Pipeline for Membership probe (includes live Universe.screen from prepareDocument).
   * Falls back to ``document`` when omitted.
   */
  probePipeline?: PipelineDocument;
}

export function PipelineCanvas({
  document,
  onChange,
  fields,
  alphaOnly = true,
  hideUniverseConfig = true,
  asOf = "",
  startDate = "",
  probePipeline,
}: PipelineCanvasProps) {
  const membershipPipeline = probePipeline ?? document;
  const [addOpen, setAddOpen] = useState(false);
  const stages = document.stages ?? [];
  const addModes = alphaOnly ? ALPHA_MODES : ALL_MODES;
  const screenFields = fields ?? [];

  const insightFields = useMemo(
    () =>
      screenFields.length > 0
        ? screenFields
        : insightsFieldCatalog(stages),
    [screenFields, stages],
  );

  const addStage = useCallback(
    (mode: StageMode) => {
      onChange({ ...document, stages: [...stages, { ...EMPTY_STAGE[mode], mode }] });
      setAddOpen(false);
    },
    [document, stages, onChange],
  );

  const strategyName = document.strategy_name ?? "Untitled Strategy";

  if (alphaOnly) {
    return (
      <div className="space-y-4">
        <AlphaMeasuresPanel document={document} onChange={onChange} fields={screenFields} />
        <AlphaInsightsPanel
          document={document}
          onChange={onChange}
          fields={insightFields}
          onPatchBinding={(patch) => onChange(patchAlphaBinding(document, patch))}
        />
        {asOf ? (
          <AlphaMembershipProbe
            pipeline={membershipPipeline}
            asOf={asOf}
            startDate={startDate}
          />
        ) : null}
        <AlphaFactorPerformancePanel
          document={document}
          fields={screenFields}
          asOf={asOf}
          startDate={startDate}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {!hideUniverseConfig ? (
        <div className="rounded border border-line bg-surface px-3 py-2">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Strategy Name
          </label>
          <input
            type="text"
            value={strategyName}
            onChange={(e) => onChange({ ...document, strategy_name: e.target.value })}
            className="mt-1 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-[13px] text-ink"
            placeholder="Strategy name"
          />
        </div>
      ) : null}

      <AlphaMeasuresPanel document={document} onChange={onChange} fields={screenFields} />
      <AlphaInsightsPanel
        document={document}
        onChange={onChange}
        fields={insightFields}
        onPatchBinding={(patch) => onChange(patchAlphaBinding(document, patch))}
      />
      <AlphaFactorPerformancePanel
        document={document}
        fields={screenFields}
        asOf={asOf}
        startDate={startDate}
      />

      <div className="relative">
        <button
          type="button"
          onClick={() => setAddOpen((o) => !o)}
          className="w-full rounded border border-dashed border-accent/50 bg-accent/5 py-2 text-[12px] font-semibold text-accent-ink hover:bg-accent/10"
        >
          + Add Stage
        </button>
        {addOpen ? (
          <div className="absolute z-10 mt-1 w-full rounded border border-line bg-surface-raised p-2 shadow-panel">
            {addModes.map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => addStage(mode)}
                className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[12px] text-ink hover:bg-surface-sunk"
              >
                <span className="font-semibold">{STAGE_MODE_LABELS[mode]}</span>
                <span className="text-[10px] opacity-60">{EMPTY_STAGE[mode].name}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {stages
        .map((stage, i) => ({ stage, i }))
        .filter(
          ({ stage }) =>
            stage.mode === "hedge" ||
            (stage.mode === "score" && !stage.as_gate) ||
            stage.mode === "filter" ||
            stage.mode === "confirm" ||
            stage.mode === "watch",
        )
        .map(({ stage, i }) => (
          <StageBlock
            key={i}
            stage={stage}
            index={i}
            onRemove={(idx) =>
              onChange({ ...document, stages: stages.filter((_, j) => j !== idx) })
            }
            onMoveUp={() => undefined}
            onMoveDown={() => undefined}
            onChange={(idx, next) =>
              onChange({
                ...document,
                stages: stages.map((s, j) => (j === idx ? next : s)),
              })
            }
            fields={fields}
          />
        ))}
    </div>
  );
}
