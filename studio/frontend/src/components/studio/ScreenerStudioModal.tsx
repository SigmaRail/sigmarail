import { LeftRail } from "../LeftRail";
import { RankingsTable } from "../RankingsTable";
import { ResultsGrid } from "../ResultsGrid";
import { InspectorPanel } from "../InspectorPanel";
import { TimeBar } from "../TimeBar";
import { TradingViewEmbed } from "../TradingViewEmbed";
import { cn } from "../../lib/utils";
import type {
  RankedRow,
  ScreenPreset,
  ScreenTemplateSummary,
  SavedScreen,
  ScreenSource,
  ViewMode,
  AppliedFilterRow,
  ScreenField,
  UniverseQueryV1,
  PreviewResponse,
  TurnoverResponse,
} from "../../types";

interface ScreenerStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyToStrategy?: () => void;
  presets: ScreenPreset[];
  templates: ScreenTemplateSummary[];
  savedScreens: SavedScreen[];
  source: ScreenSource;
  preset: string;
  templateId: string | null;
  savedScreenId: number | string | null;
  onSelectPreset: (id: string) => void;
  onSelectTemplate: (id: string) => void;
  onSelectSaved: (screen: SavedScreen) => void;
  onRenameSaved?: (screen: SavedScreen) => void;
  onDeleteSaved?: (screen: SavedScreen) => void;
  rankedRows: RankedRow[];
  selected: RankedRow | null;
  onSelectRow: (row: RankedRow) => void;
  loading: boolean;
  viewMode: ViewMode;
  onViewModeChange: (m: ViewMode) => void;
  gridVisibleCount: number;
  onLoadMoreGrid: () => void;
  filterRows: AppliedFilterRow[];
  fields: ScreenField[];
  spec: UniverseQueryV1 | null;
  onFilterRowsChange: (rows: AppliedFilterRow[]) => void;
  onSpecChange: (spec: UniverseQueryV1) => void;
  previewData: PreviewResponse | null;
  datesDesc: string[];
  asOf: string;
  onAsOfChange: (d: string) => void;
  turnover: TurnoverResponse | null;
  turnoverLoading: boolean;
}

export function ScreenerStudioModal({
  isOpen,
  onClose,
  onApplyToStrategy,
  presets,
  templates,
  savedScreens,
  source,
  preset,
  templateId,
  savedScreenId,
  onSelectPreset,
  onSelectTemplate,
  onSelectSaved,
  onRenameSaved,
  onDeleteSaved,
  rankedRows,
  selected,
  onSelectRow,
  loading,
  viewMode,
  onViewModeChange,
  gridVisibleCount,
  onLoadMoreGrid,
  filterRows,
  fields,
  spec,
  onFilterRowsChange,
  onSpecChange,
  previewData,
  datesDesc,
  asOf,
  onAsOfChange,
  turnover,
  turnoverLoading,
}: ScreenerStudioModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 backdrop-blur-sm">
      <div className="flex h-[94vh] w-[96vw] max-w-[1700px] flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-4 py-2.5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-ink">
                Screener Studio & Universe Lab
              </span>
              <span className="rounded bg-accent/15 px-2 py-0.5 font-mono text-[10.5px] font-bold text-accent-ink">
                Slot 1 Universe Builder
              </span>
            </div>
            <span className="text-xs text-ink-muted hidden sm:inline">
              Author AST boolean criteria, test fundamental presets, and preview candidate universe.
            </span>
          </div>

          <div className="flex items-center gap-2">
            {onApplyToStrategy && (
              <button
                type="button"
                onClick={() => {
                  onApplyToStrategy();
                  onClose();
                }}
                className="flex items-center gap-1.5 rounded bg-accent px-3.5 py-1.5 text-xs font-bold text-accent-ink shadow-sm hover:opacity-90 transition-opacity"
              >
                <span>✓</span>
                <span>Apply & Link to Strategy</span>
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-xs font-semibold text-ink-muted hover:text-ink hover:bg-surface-raised transition-colors"
            >
              ✕ Close
            </button>
          </div>
        </div>

        {/* Modal Body: Full Screener Workbench */}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Left Rail */}
          <LeftRail
            presets={presets}
            templates={templates}
            savedScreens={savedScreens}
            source={source}
            selectedPresetId={preset}
            selectedTemplateId={templateId}
            selectedSavedScreenId={savedScreenId}
            onSelectPreset={onSelectPreset}
            onSelectTemplate={onSelectTemplate}
            onSelectSaved={onSelectSaved}
            onRenameSaved={onRenameSaved}
            onDeleteSaved={onDeleteSaved}
          />

          {/* Main Results Table & Chart */}
          <main className="flex min-w-0 flex-1 flex-col border-r border-line bg-surface">
            {/* View Mode & Sorter Strip */}
            <div className="flex shrink-0 items-center justify-between border-b border-line px-3 py-1.5">
              <div
                className="inline-flex rounded border border-line bg-surface-sunk p-0.5"
                role="group"
                aria-label="Results view"
              >
                {(["list", "grid"] as ViewMode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => onViewModeChange(m)}
                    className={cn(
                      "rounded px-2.5 py-0.5 text-[11px] font-semibold capitalize transition-colors",
                      viewMode === m
                        ? "bg-ink text-white shadow-sm"
                        : "text-ink-muted hover:text-ink"
                    )}
                  >
                    {m}
                  </button>
                ))}
              </div>

              <span className="font-mono text-[11px] text-ink-muted">
                {rankedRows.length} Candidate Tickers
              </span>
            </div>

            {/* Content Area */}
            <div className="flex min-h-0 flex-1 flex-col">
              {viewMode === "list" ? (
                <>
                  <div className="flex min-h-0 flex-[1.1] flex-col overflow-hidden">
                    <RankingsTable
                      rows={rankedRows}
                      selectedTicker={selected?.ticker ?? null}
                      onSelect={onSelectRow}
                      loading={loading}
                      source={source}
                    />
                  </div>
                  <TradingViewEmbed
                    symbol={selected?.ticker ?? null}
                    exchange={
                      typeof selected?.exchange === "string"
                        ? selected.exchange
                        : null
                    }
                    className="min-h-[220px] flex-[0.9] border-t border-line bg-[#131722]"
                  />
                </>
              ) : (
                <>
                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                    <ResultsGrid
                      rows={rankedRows}
                      selectedTicker={selected?.ticker ?? null}
                      onSelect={onSelectRow}
                      visibleCount={gridVisibleCount}
                      onLoadMore={onLoadMoreGrid}
                      loading={loading}
                    />
                  </div>
                  {selected ? (
                    <TradingViewEmbed
                      symbol={selected.ticker}
                      exchange={
                        typeof selected.exchange === "string"
                          ? selected.exchange
                          : null
                      }
                      compact
                      height={180}
                      className="shrink-0 border-t border-line bg-[#131722]"
                    />
                  ) : null}
                </>
              )}
            </div>
          </main>

          {/* Right Inspector Panel */}
          <InspectorPanel
            row={selected}
            preview={previewData}
            source={source}
            filterRows={filterRows}
            fields={fields}
            spec={spec}
            onFilterRowsChange={onFilterRowsChange}
            onSpecChange={onSpecChange}
          />
        </div>

        {/* Bottom TimeBar */}
        <TimeBar
          datesDesc={datesDesc}
          asOf={asOf}
          onAsOfChange={onAsOfChange}
          turnover={turnover}
          loading={turnoverLoading}
        />
      </div>
    </div>
  );
}
