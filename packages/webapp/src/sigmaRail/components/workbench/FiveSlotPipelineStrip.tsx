import { cn } from "../../lib/utils";

interface FiveSlotPipelineStripProps {
  universeTitle: string;
  universeCount?: number;
  universeType?: string;
  activeAlphaCount: number;
  alphaSummary: string;
  alphaType?: string;
  pcmType: string;
  activeRiskCount: number;
  riskSummary: string;
  riskType?: string;
  executionType: string;
  activeSlotIndex?: number;
  onSelectSlot?: (index: number) => void;
}

export function FiveSlotPipelineStrip({
  universeTitle,
  universeCount,
  universeType = "VeraScreenerUniverseSelectionModel",
  activeAlphaCount,
  alphaSummary,
  alphaType,
  pcmType,
  activeRiskCount,
  riskSummary,
  riskType = "NullRiskManagementModel",
  executionType,
  activeSlotIndex,
  onSelectSlot,
}: FiveSlotPipelineStripProps) {
  const resolvedAlphaType =
    alphaType ??
    (activeAlphaCount > 1
      ? "CompositeAlphaModel"
      : activeAlphaCount === 1
        ? alphaSummary
        : "None");

  const slots = [
    {
      idx: 0,
      title: "1. UniverseSelection",
      main: universeType,
      sub:
        universeCount != null
          ? `${universeTitle} · ${universeCount} candidates`
          : universeTitle,
      accent: "border-line/80 bg-surface-sunk text-ink",
    },
    {
      idx: 1,
      title: "2. Alpha",
      main: resolvedAlphaType,
      sub:
        activeAlphaCount > 1
          ? `Composite (${activeAlphaCount}) · ${alphaSummary}`
          : alphaSummary || "Scores / signals / pyramid",
      accent: "border-accent/60 bg-accent/5 text-accent-ink",
    },
    {
      idx: 2,
      title: "3. PortfolioConstruction",
      main: pcmType,
      sub: "Insight sizing / exposure",
      accent: "border-line/80 bg-surface-sunk text-ink",
    },
    {
      idx: 3,
      title: "4. RiskManagement",
      main: riskType,
      sub:
        activeRiskCount > 1
          ? `Stacked (${activeRiskCount}) · ${riskSummary}`
          : riskSummary || "Unconstrained",
      accent:
        activeRiskCount > 0
          ? "border-danger/40 bg-danger/5 text-danger"
          : "border-line/80 bg-surface-sunk text-ink-muted",
    },
    {
      idx: 4,
      title: "5. Execution",
      main: executionType,
      sub: "Order slicer",
      accent: "border-line/80 bg-surface-sunk text-ink",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 text-[11px]">
      {slots.map((s) => {
        const isSelected = activeSlotIndex === s.idx;
        return (
          <button
            key={s.idx}
            type="button"
            onClick={() => onSelectSlot?.(s.idx)}
            className={cn(
              "rounded border p-2 text-center transition-all cursor-pointer text-left sm:text-center",
              s.accent,
              isSelected ? "ring-2 ring-accent shadow-md" : "hover:border-accent/40",
              s.idx === 4 && "col-span-2 sm:col-span-1"
            )}
          >
            <span className="font-mono text-[9px] uppercase font-bold text-ink-faint block">
              {s.title}
            </span>
            <div className="mt-0.5 font-bold truncate text-[11.5px]">
              {s.main}
            </div>
            <span className="text-[9.5px] opacity-75 block truncate">
              {s.sub}
            </span>
          </button>
        );
      })}
    </div>
  );
}
