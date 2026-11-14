/**
 * Membership over time — the screen's member count per day, with the from-to window.
 *
 * Extracted from the strategy card so the **screener** can show the same chart instead of only
 * the strategy view. The range summary is one server-side aggregate (`GROUP BY date, count()`),
 * so this only owns the window, the query and the chart.
 *
 * A click on the chart picks a date — the caller decides what follows it (the card pins its
 * as-of list, the screener moves its evaluation date).
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchAsOfRange, fetchUniverseRangeSummary } from "../../api/screens";
import { RANGE_PRESETS, clampWindow, presetWindow, subtractMonths } from "../../lib/rangePresets";
import type { UniverseQueryV1 } from "../../types";
import { ProbeRangeChart } from "../ProbeRangeChart";

interface MembershipOverTimeProps {
  /** The screen being charted — only its `where` matters (the summary leans the spec itself). */
  spec: UniverseQueryV1;
  /** Anchor: the latest date in the screen. */
  asOf: string;
  /** Window start to begin with (falls back to `asOf` − 1y). */
  startDate?: string;
  onHoverDate?: (date: string | null) => void;
  /** A click on the chart picks a date for the caller's list. */
  onPickDate?: (date: string) => void;
  height?: number;
}

export function MembershipOverTime({
  spec,
  asOf,
  startDate,
  onHoverDate,
  onPickDate,
  height = 140,
}: MembershipOverTimeProps) {
  // A caller may not have a strategy's evaluation start; default to the last year so the window
  // is always valid (and cheap — the full history is one click away via `Max`).
  const defaultFrom = startDate || (asOf ? subtractMonths(asOf, 12) : "");
  /** Earliest session the service can serve — what `Max` should reach for. */
  const rangeFloor = useQuery({
    queryKey: ["backtest-as-of-range-floor"],
    queryFn: () => fetchAsOfRange(10000),
    staleTime: 60 * 60_000,
  }).data?.slice(-1)[0];

  const [rangeFrom, setRangeFrom] = useState(defaultFrom);
  const [rangeTo, setRangeTo] = useState(asOf);

  useEffect(() => {
    setRangeFrom(defaultFrom);
    setRangeTo(asOf);
  }, [defaultFrom, asOf]);

  /** Normalise every window change (the only thing to fix is an inverted pair — no width cap). */
  const applyWindow = (from: string, to: string) => {
    const window = clampWindow(from, to);
    setRangeFrom(window.from);
    setRangeTo(window.to);
  };

  const liveSpecKey = JSON.stringify(spec?.where ?? null);
  const rangeQuery = useQuery({
    queryKey: ["universe-membership-range", spec?.where, rangeFrom, rangeTo],
    queryFn: () =>
      fetchUniverseRangeSummary({ spec, start_date: rangeFrom, end_date: rangeTo }),
    enabled: Boolean(spec && rangeFrom && rangeTo),
    staleTime: 0,
    placeholderData: (prev) => prev,
  });

  const dates = rangeQuery.data?.dates ?? [];
  const memberCounts = rangeQuery.data?.member_counts ?? [];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] text-ink-muted">
        <span className="inline-flex flex-wrap items-center gap-1">
          {RANGE_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => {
                const window = presetWindow(preset.id, rangeTo || asOf, rangeFloor);
                if (window) applyWindow(window.from, window.to);
              }}
              className="rounded border border-line px-1.5 py-0.5 text-ink-muted hover:border-accent hover:text-accent"
              title={`${preset.label} back from ${rangeTo || asOf}`}
            >
              {preset.label}
            </button>
          ))}
        </span>
        <label className="inline-flex items-center gap-1">
          from
          <input
            type="date"
            value={rangeFrom}
            max={rangeTo || undefined}
            onChange={(e) => applyWindow(e.target.value, rangeTo)}
            className="rounded border border-line bg-surface px-1 py-0.5 text-ink"
          />
        </label>
        <label className="inline-flex items-center gap-1">
          to
          <input
            type="date"
            value={rangeTo}
            min={rangeFrom || undefined}
            onChange={(e) => applyWindow(rangeFrom, e.target.value)}
            className="rounded border border-line bg-surface px-1 py-0.5 text-ink"
          />
        </label>
        {rangeQuery.isFetching ? <span className="text-ink-faint">loading…</span> : null}
      </div>

      {!asOf && <p className="font-mono text-[10px] text-ink-faint">Set an as-of date to load membership.</p>}
      {rangeQuery.error && (
        <p className="font-mono text-[10px] text-danger">{(rangeQuery.error as Error).message}</p>
      )}
      {rangeQuery.data && (
        <>
          <p className="font-mono text-[10px] text-ink-muted">
            points={String(rangeQuery.data.summary?.trading_days ?? dates.length)} · avg members=
            {String(rangeQuery.data.summary?.avg_members_per_day ?? "—")} ·{" "}
            {rangeFrom} → {rangeTo}
          </p>
          <ProbeRangeChart
            dates={dates}
            memberCounts={memberCounts}
            membersOnly
            height={height}
            onHoverDate={onHoverDate}
            onClickDate={(d) => onPickDate?.(d)}
          />
        </>
      )}
      {/* silence the unused-key warning without changing the query identity */}
      <span className="hidden" data-spec-key={liveSpecKey.slice(0, 0)} />
    </div>
  );
}
