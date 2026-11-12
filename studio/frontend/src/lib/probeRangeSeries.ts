/** Map probe range JSON → lightweight-charts LineData (pure). */

export type ProbeLinePoint = { time: string; value: number };

export type ProbeRangeSeriesInput = {
  dates: string[];
  member_counts: number[];
  measure_series?: Record<string, number[]>;
  /** Max measure series to include (besides member_count). */
  maxMeasures?: number;
};

export type ProbeRangeSeriesOut = {
  memberCount: ProbeLinePoint[];
  measures: { id: string; points: ProbeLinePoint[] }[];
};

function toUtcDay(iso: string): string | null {
  const s = (iso || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  return s;
}

/** Align dates with counts; drop non-finite / mismatched lengths. */
export function buildProbeRangeSeries(input: ProbeRangeSeriesInput): ProbeRangeSeriesOut {
  const dates = input.dates || [];
  const counts = input.member_counts || [];
  const n = Math.min(dates.length, counts.length);
  const memberCount: ProbeLinePoint[] = [];
  for (let i = 0; i < n; i++) {
    const time = toUtcDay(dates[i]!);
    const value = Number(counts[i]);
    if (!time || !Number.isFinite(value)) continue;
    memberCount.push({ time, value });
  }

  const maxM = input.maxMeasures ?? 8;
  const measures: ProbeRangeSeriesOut["measures"] = [];
  const series = input.measure_series || {};
  for (const id of Object.keys(series).sort()) {
    if (measures.length >= maxM) break;
    const vals = series[id] || [];
    const points: ProbeLinePoint[] = [];
    const m = Math.min(dates.length, vals.length);
    for (let i = 0; i < m; i++) {
      const time = toUtcDay(dates[i]!);
      const value = Number(vals[i]);
      if (!time || !Number.isFinite(value)) continue;
      points.push({ time, value });
    }
    if (points.length) measures.push({ id, points });
  }

  return { memberCount, measures };
}
