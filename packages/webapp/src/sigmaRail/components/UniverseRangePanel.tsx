import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchUniverseRangeSummary } from "../api/screens";
import { cn } from "../lib/utils";
import type { UniverseQueryV1 } from "../types";
import { Button } from "@sb/webapp-core/components/ui/button";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

function yearBackStart(datesDesc: string[]): string {
  if (datesDesc.length === 0) return "";
  const idx = Math.min(datesDesc.length - 1, 251);
  return datesDesc[idx] ?? datesDesc[datesDesc.length - 1]!;
}

function MiniBarChart({
  dates,
  counts,
  maxCount,
}: {
  dates: string[];
  counts: number[];
  maxCount: number;
}) {
  if (counts.length === 0) return null;
  const sampleStep = counts.length > 60 ? Math.ceil(counts.length / 60) : 1;
  const sampled = counts
    .map((c, i) => ({ c, i }))
    .filter((_, i) => i % sampleStep === 0 || i === counts.length - 1);

  return (
    <div className="mt-2">
      <div
        className="flex h-16 items-end gap-px rounded border border-line bg-surface-sunk px-1 py-1"
        role="img"
        aria-label="Universe member counts over time"
      >
        {sampled.map(({ c, i }) => {
          const h = maxCount > 0 ? Math.max(2, Math.round((c / maxCount) * 100)) : 2;
          return (
            <div
              key={`${dates[i]}-${i}`}
              className="min-w-0 flex-1 rounded-sm bg-accent/70"
              style={{ height: `${h}%` }}
              title={`${dates[i]}: ${c}`}
            />
          );
        })}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-faint">
        <span>{dates[0]}</span>
        <span>{dates[dates.length - 1]}</span>
      </div>
    </div>
  );
}

export function UniverseRangePanel({
  spec,
  endDate,
  datesDesc,
}: {
  spec: UniverseQueryV1;
  endDate: string;
  datesDesc: string[];
}) {
  const [open, setOpen] = useState(false);
  const startDate = useMemo(() => yearBackStart(datesDesc), [datesDesc]);

  const rangeQuery = useQuery({
    queryKey: ["universe-range-summary", endDate, startDate, JSON.stringify(spec)],
    queryFn: () =>
      fetchUniverseRangeSummary({
        spec,
        start_date: startDate,
        end_date: endDate,
        include_weekly_samples: true,
      }),
    enabled: open && Boolean(endDate && startDate && spec),
    staleTime: 60_000,
  });

  const data = rangeQuery.data;
  const maxCount = data?.member_counts.length
    ? Math.max(...data.member_counts)
    : 0;

  return (
    <div className="border-t border-line/70">
      <Button
        type="button"
        onClick={() => setOpen((v) => !v)}
        variant="ghost"
        className="h-auto w-full justify-between rounded-none px-3 py-1.5 text-left"
        aria-expanded={open}
      >
        <span className="text-[11px] font-medium text-ink-muted">
          Universe range preview
        </span>
        <span className="font-mono text-[10px] text-ink-faint">
          {open ? "−" : "+"}
        </span>
      </Button>
      {open ? (
        <div className="border-t border-line/70 px-3 py-2">
          {rangeQuery.isLoading ? (
            <p className="text-[11px] text-ink-muted">Loading range summary…</p>
          ) : rangeQuery.isError ? (
            <p className="text-[11px] text-danger">
              {(rangeQuery.error as Error).message}
            </p>
          ) : data ? (
            <>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                <Stat label="Range" value={`${data.start_date} → ${data.end_date}`} />
                <Stat
                  label="Trading days"
                  value={String(data.summary.trading_days)}
                  mono
                />
                <Stat
                  label="Avg/day"
                  value={String(data.summary.avg_members_per_day)}
                  mono
                />
                <Stat
                  label="Min"
                  value={String(data.summary.min_members_per_day)}
                  mono
                />
                <Stat
                  label="Max"
                  value={String(data.summary.max_members_per_day)}
                  mono
                />
              </div>
              <MiniBarChart
                dates={data.dates}
                counts={data.member_counts}
                maxCount={maxCount}
              />
              {data.weekly_samples && data.weekly_samples.length > 0 ? (
                <div className="mt-2 overflow-x-auto">
                  <WorkspaceTable className="w-full text-[10px]">
                    <WorkspaceTableHeader>
                      <WorkspaceTableRow className="border-b border-line text-left text-ink-faint">
                        <WorkspaceTableHead className="h-auto py-1 pr-2 font-medium">Date</WorkspaceTableHead>
                        <WorkspaceTableHead className="h-auto py-1 font-medium">Sample tickers</WorkspaceTableHead>
                      </WorkspaceTableRow>
                    </WorkspaceTableHeader>
                    <WorkspaceTableBody>
                      {data.weekly_samples.map((row) => (
                        <WorkspaceTableRow key={row.date} className="border-b border-line/50">
                          <WorkspaceTableCell className="py-1 pr-2 font-mono text-ink-muted">
                            {row.date}
                          </WorkspaceTableCell>
                          <WorkspaceTableCell className="py-1 font-mono text-ink">
                            {row.sample_tickers.join(", ") || "—"}
                          </WorkspaceTableCell>
                        </WorkspaceTableRow>
                      ))}
                    </WorkspaceTableBody>
                  </WorkspaceTable>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-[11px] text-ink-muted">No range data.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-1">
      <span className="text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
      </span>
      <span className={cn(mono && "font-mono", "text-ink")}>{value}</span>
    </div>
  );
}
