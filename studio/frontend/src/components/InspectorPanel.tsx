import { useEffect, useRef } from "react";
import { tradingViewUrl } from "../api/screens";
import { cn, formatNum, formatVol } from "../lib/utils";
import type {
  AppliedFilterRow,
  PreviewResponse,
  RankedRow,
  ScreenField,
  ScreenSource,
  UniverseQueryV1,
} from "../types";
import { AppliedFiltersPanel } from "./AppliedFiltersPanel";
import { SortPanel } from "./SortPanel";

function inspectorIrPayload(
  source: ScreenSource,
  preview: PreviewResponse | null,
  spec: UniverseQueryV1 | null,
): unknown {
  if (preview?.screen_ir !== undefined) {
    if (preview.screen_ir === "universe_query_v1" && preview.spec) {
      return preview.spec;
    }
    return preview.screen_ir;
  }
  if (source === "ir" && spec) {
    return spec;
  }
  return {
    type: "screen_stocks_preset",
    preset: preview?.preset,
    as_of: preview?.as_of,
    table: preview?.table,
    note: preview?.note,
  };
}

export function InspectorPanel({
  row,
  preview,
  source,
  filterRows,
  fields,
  spec,
  onFilterRowsChange,
  onSpecChange,
}: {
  row: RankedRow | null;
  preview: PreviewResponse | null;
  source: ScreenSource;
  filterRows: AppliedFilterRow[];
  fields: ScreenField[];
  spec: UniverseQueryV1 | null;
  onFilterRowsChange: (rows: AppliedFilterRow[]) => void;
  onSpecChange: (next: UniverseQueryV1) => void;
}) {
  const tickerSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!row) return;
    tickerSectionRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [row?.ticker]);

  const ir = inspectorIrPayload(source, preview, spec);

  return (
    <aside className="flex w-[22rem] shrink-0 flex-col border-l border-line bg-surface-raised">
      <AppliedFiltersPanel
        rows={filterRows}
        fields={fields}
        enabled={source === "ir"}
        onChange={onFilterRowsChange}
      />
      <SortPanel
        source={source}
        spec={spec}
        fields={fields}
        onSpecChange={onSpecChange}
      />
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-line px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Inspector
          </div>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-3">
          {!row ? (
            <p className="text-xs text-ink-muted">Select a row to inspect.</p>
          ) : (
            <>
              <div ref={tickerSectionRef}>
                <div className="font-mono text-lg font-semibold tracking-wide">
                  {row.ticker}
                </div>
                <div className="mt-0.5 text-[11px] text-ink-muted">
                  Rank {row.delta === "dropped" ? "—" : row.rank}
                  {row.priorRank != null ? ` · prior ${row.priorRank}` : ""}
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-2 gap-y-1.5 text-[11px]">
                <Fact label="RS" value={formatNum(row.rs_rating, 0)} />
                <Fact
                  label="TA"
                  value={formatNum(row.technical_rating, 0)}
                />
                <Fact
                  label="Setup"
                  value={formatNum(row.setup_quality_rating, 0)}
                />
                <Fact
                  label="HGM"
                  value={formatNum(row.high_growth_momentum_rating, 0)}
                />
                <Fact label="Vol50" value={formatVol(row.avg_vol_50d)} />
                <Fact label="Overall" value={formatNum(row.overall_score, 1)} />
                <Fact
                  label="Minervini"
                  value={formatNum(row.minervini_score, 1)}
                />
                <Fact label="O'Neil" value={formatNum(row.oneil_score, 1)} />
                <Fact
                  label="Close"
                  value={formatNum(row.close, 2)}
                  className="col-span-2"
                />
                <Fact
                  label="Class"
                  value={
                    row.classification ? String(row.classification) : "—"
                  }
                  className="col-span-2"
                />
              </dl>
              <button
                type="button"
                className="w-full rounded border border-line bg-surface-sunk px-2 py-1.5 text-[12px] font-medium text-ink hover:border-highlight hover:bg-highlight-soft"
                onClick={() =>
                  window.open(
                    tradingViewUrl(
                      row.ticker,
                      typeof row.exchange === "string" ? row.exchange : null,
                    ),
                    "_blank",
                    "noopener",
                  )
                }
              >
                Open in TradingView
              </button>
            </>
          )}

          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
              Screen IR
            </div>
            <pre className="max-h-48 overflow-auto rounded border border-line bg-surface-sunk p-2 font-mono text-[10px] leading-relaxed text-ink-muted">
              {JSON.stringify(ir, null, 2)}
            </pre>
            {preview?.note ? (
              <p className="mt-1.5 text-[10px] leading-snug text-ink-faint">
                {preview.note}
              </p>
            ) : null}
          </div>

          {preview?.sql ? (
            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                  Compiled SQL
                </div>
                <button
                  type="button"
                  className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
                  onClick={() => {
                    void navigator.clipboard?.writeText(preview.sql ?? "");
                  }}
                >
                  Copy
                </button>
              </div>
              <pre className="max-h-64 overflow-auto rounded border border-line bg-surface-sunk p-2 font-mono text-[10px] leading-relaxed text-ink-muted whitespace-pre-wrap">
                {preview.sql}
              </pre>
              {preview.params && Object.keys(preview.params).length > 0 ? (
                <pre className="mt-1.5 max-h-24 overflow-auto rounded border border-line/70 bg-surface p-1.5 font-mono text-[9px] text-ink-faint">
                  {JSON.stringify(preview.params, null, 2)}
                </pre>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function Fact({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded border border-line/80 px-1.5 py-1", className)}>
      <dt className="text-[9px] uppercase tracking-wider text-ink-faint">
        {label}
      </dt>
      <dd className="font-mono text-[12px] text-ink">{value}</dd>
    </div>
  );
}
