import type { ScreenField } from "../../types";
import type { PipelineDocument } from "../strategy/StrategyDocument";
import {
  measureAliasesForLookup,
  orderByMeasureAliases,
  patchInsightPropertyAlias,
  primaryColFromSlot,
  rankDirection,
  whereMeasureAliases,
} from "../../lib/insightMeasureBindings";

type Props = {
  document: PipelineDocument;
  /** Unused — kept so callers can pass a stable props shape. */
  onChange?: (doc: PipelineDocument) => void;
  /** Unused — property lookup is measure-alias only. */
  fields?: ScreenField[];
  onPatchBinding: (
    patch: Partial<NonNullable<PipelineDocument["bindings"]>>,
  ) => void;
};

/** Property row: fixed Insight.Price slot + measure-alias lookup. */
function InsightPropertySection({
  label,
  hint,
  value,
  aliases,
  emptyLabel,
  onPick,
}: {
  label: string;
  hint: string;
  value: string | null;
  aliases: string[];
  emptyLabel: string;
  onPick: (alias: string | null) => void;
}) {
  const selected = value && aliases.includes(value) ? value : "";
  return (
    <div className="space-y-1 rounded border border-line/60 bg-surface-raised/15 px-2.5 py-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-[10px] font-semibold text-ink">{label}</span>
        <span className="text-[9px] text-ink-faint">{hint}</span>
      </div>
      <label className="block">
        <span className="sr-only">Select measure alias for {label}</span>
        <select
          value={selected}
          onChange={(e) => {
            const v = e.target.value;
            onPick(v || null);
          }}
          className="block w-full max-w-sm rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
        >
          <option value="">{emptyLabel}</option>
          {aliases.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </label>
      {value && !aliases.includes(value) ? (
        <p className="text-[9px] text-warn">
          Bound to <span className="font-mono">{value}</span> — add it as a measure to keep.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Insights: bind Insight.Price properties via measure lookup only.
 * Emit gates (eligibility / setup / timing) live on Measures — not here.
 */
export function AlphaInsightsPanel({ document, onPatchBinding }: Props) {
  const measureAliases = measureAliasesForLookup(document.stages ?? []);
  const dirCol = primaryColFromSlot(document.bindings?.alpha_direction);
  const magCol = primaryColFromSlot(document.bindings?.alpha_magnitude);
  const weightCol = primaryColFromSlot(document.bindings?.alpha_weight);
  const confCol = primaryColFromSlot(document.bindings?.alpha_confidence);
  const periodDays = document.bindings?.alpha_insight_period_days ?? 1;
  const orderBy = orderByMeasureAliases(document);
  const where = whereMeasureAliases(document);
  const whereParts = [
    ...where.setup.map((a) => `setup:${a}=1`),
    ...where.eligibility.map((a) => `${a}=1`),
  ];

  function patchProp(
    key: "alpha_direction" | "alpha_magnitude" | "alpha_weight" | "alpha_confidence",
    alias: string | null,
  ): void {
    onPatchBinding(patchInsightPropertyAlias(document.bindings, key, alias));
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-3">
      <div className="flex items-center justify-between border-b border-line/60 pb-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          Insights
        </span>
        <span className="font-mono text-[10px] text-ink-faint">Insight.Price ← measure lookup</span>
      </div>

      <p className="text-[10px] text-ink-faint leading-tight">
        Alpha binds each Insight.Price field to a measure alias. Bool measures with Insight ✓
        become WHERE (setup / eligibility); number / field measures become ORDER BY. Stops and
        sizing live on PCM / Risk.
      </p>

      <div className="space-y-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
          Insight.Price properties
        </div>

        <InsightPropertySection
          label="Direction"
          hint="Int8: 1 Up · −1 Down · 0 Flat (unbound → Up)"
          value={dirCol}
          aliases={measureAliases}
          emptyLabel="Select measure alias…"
          onPick={(a) => patchProp("alpha_direction", a)}
        />
        <InsightPropertySection
          label="Magnitude"
          hint="Signed accel / thrust (clamped ±0.25)"
          value={magCol}
          aliases={measureAliases}
          emptyLabel="Select measure alias…"
          onPick={(a) => patchProp("alpha_magnitude", a)}
        />
        <InsightPropertySection
          label="Weight"
          hint="0–1 portfolio hint (PCM caps by max weight)"
          value={weightCol}
          aliases={measureAliases}
          emptyLabel="Select measure alias…"
          onPick={(a) => patchProp("alpha_weight", a)}
        />
        <InsightPropertySection
          label="Confidence"
          hint="Signal quality [0.1, 1]"
          value={confCol}
          aliases={measureAliases}
          emptyLabel="Select measure alias…"
          onPick={(a) => patchProp("alpha_confidence", a)}
        />

        <label className="block space-y-0.5 rounded border border-line/60 bg-surface-raised/15 px-2.5 py-2">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-[10px] font-semibold text-ink">Period</span>
            <span className="text-[9px] text-ink-faint">days (not a measure)</span>
          </div>
          <input
            type="number"
            min={1}
            step={1}
            value={periodDays}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              onPatchBinding({
                alpha_insight_period_days: Number.isFinite(n) && n >= 1 ? n : 1,
              });
            }}
            className="w-20 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
          />
        </label>
      </div>

      <div className="rounded border border-line/50 bg-surface-raised/20 px-2 py-1.5 space-y-1.5 text-[10px] text-ink-muted">
        <div className="space-y-0.5">
          <div className="font-semibold text-ink-muted">
            WHERE (bool measures with Insight ✓)
          </div>
          <p className="font-mono text-ink">
            {whereParts.length
              ? whereParts.join(" AND ")
              : "(none — Insight ✓ on setup / filter measures)"}
          </p>
        </div>
        <div className="space-y-0.5 border-t border-line/40 pt-1.5">
          <div className="font-semibold text-ink-muted">
            ORDER BY (number / field measures with Insight ✓)
          </div>
          <p className="font-mono text-ink">
            {orderBy.length
              ? orderBy
                  .map((c) => `${c} ${rankDirection(document, c).toUpperCase()}`)
                  .join(", ")
              : "(none — Insight ✓ on expr / field measures)"}
          </p>
        </div>
      </div>
    </div>
  );
}
