import { filterChipLabel } from "../lib/irFilters";
import { cn } from "../lib/utils";
import { primaryOrderBy } from "../lib/screenSpec";
import type {
  AppliedFilterRow,
  PreviewResponse,
  SavedScreen,
  ScreenPreset,
  ScreenSource,
  ScreenTemplateSummary,
  UniverseQueryV1,
} from "../types";
import { UniverseRangePanel } from "./UniverseRangePanel";

export function CriteriaStrip({
  source,
  preset,
  presets,
  templateId,
  templates,
  savedScreenId,
  savedScreens,
  preview,
  limit,
  filterRows,
  spec,
  onBacktestScreen,
  asOf,
  datesDesc,
}: {
  source: ScreenSource;
  preset: string;
  presets: ScreenPreset[];
  templateId: string | null;
  templates: ScreenTemplateSummary[];
  savedScreenId?: number | string | null;
  savedScreens?: SavedScreen[];
  preview: PreviewResponse | null;
  limit: number;
  filterRows: AppliedFilterRow[];
  spec?: UniverseQueryV1 | null;
  onBacktestScreen?: () => void;
  asOf?: string;
  datesDesc?: string[];
}) {
  const presetMeta = presets.find((p) => p.id === preset);
  const presetLabel = presetMeta?.label ?? preset;
  const templateLabel =
    templates.find((t) => t.id === templateId)?.label ?? templateId ?? "—";
  const savedScreen =
    savedScreenId != null
      ? savedScreens?.find((s) => s.id === savedScreenId)
      : null;
  const canBacktest =
    (source === "ir" && Boolean(spec)) ||
    (source === "preset" && Boolean(presetMeta?.backtestable !== false));
  const order = source === "ir" ? primaryOrderBy(spec) : null;
  const limitPerDay =
    source === "ir" ? (spec?.limit_per_day ?? preview?.limit ?? limit) : null;

  return (
    <div className="shrink-0 border-b border-line bg-surface-raised">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-[12px]">
        {source === "ir" ? (
          <>
            {savedScreen ? (
              <>
                <Chip label="Screen" value={savedScreen.name} />
                <Chip label="Id" value={String(savedScreen.id)} mono />
              </>
            ) : templateId ? (
              <>
                <Chip label="Template" value={templateLabel} />
                <Chip label="Id" value={templateId} mono />
              </>
            ) : (
              <Chip label="Source" value="Custom IR" />
            )}
            <Chip label="IR" value="universe_query_v1" mono />
            {order ? (
              <Chip
                label="Sort"
                value={`${order.field} ${order.direction.toUpperCase()}`}
                mono
              />
            ) : null}
            {limitPerDay != null ? (
              <Chip label="Limit/day" value={String(limitPerDay)} mono />
            ) : null}
          </>
        ) : (
          <>
            <Chip label="Preset" value={presetLabel} />
            <Chip label="Id" value={preset} mono />
          </>
        )}
        <Chip label="As-of" value={preview?.as_of ?? "—"} mono />
        <Chip
          label="Hits"
          value={`${preview?.count ?? 0} / lim ${preview?.limit ?? limit}`}
          mono
        />
        {preview?.table ? (
          <Chip label="Table" value={String(preview.table)} mono />
        ) : null}
        {canBacktest && onBacktestScreen ? (
          <button
            type="button"
            onClick={onBacktestScreen}
            className={cn(
              "ml-auto rounded border border-line bg-surface-sunk px-2.5 py-1 text-[12px] font-medium text-ink",
              "hover:border-accent hover:bg-accent-soft",
            )}
          >
            Research this screen
          </button>
        ) : null}
      </div>
      {source === "ir" && spec && asOf && datesDesc && datesDesc.length > 0 ? (
        <UniverseRangePanel spec={spec} endDate={asOf} datesDesc={datesDesc} />
      ) : null}
      {source === "ir" && filterRows.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 border-t border-line/70 px-3 py-1.5">
          {filterRows.slice(0, 12).map((row) => (
            <span
              key={row.id}
              className="rounded-full border border-line bg-surface-sunk px-2 py-0.5 font-mono text-[10px] text-ink-muted"
              title={filterChipLabel(row)}
            >
              {filterChipLabel(row)}
            </span>
          ))}
          {filterRows.length > 12 ? (
            <span className="px-1 text-[10px] text-ink-faint">
              +{filterRows.length - 12} more
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Chip({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
        {label}
      </span>
      <span className={mono ? "font-mono text-ink" : "font-medium text-ink"}>
        {value}
      </span>
    </div>
  );
}
