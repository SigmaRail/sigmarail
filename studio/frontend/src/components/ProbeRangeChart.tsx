import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import { buildProbeRangeSeries } from "../lib/probeRangeSeries";
import { lwcTimeToIsoDate } from "../lib/lwcTime";

const MEASURE_COLORS = ["#22c55e", "#f59e0b", "#a855f7", "#22d3ee"];
/** Fire load-earlier when the left edge is within this many bars of the start. */
const EARLIER_EDGE_BARS = 8;
/** Ignore edge-load while programmatic viewport restore settles. */
const SUPPRESS_EARLIER_MS = 900;

type Props = {
  dates: string[];
  memberCounts: number[];
  measureSeries?: Record<string, number[]>;
  /** When true, skip measure pane even if measureSeries is passed. */
  membersOnly?: boolean;
  className?: string;
  height?: number;
  /** Fired on crosshair move; null when leaving the series. */
  onHoverDate?: (isoDate: string | null) => void;
  /** Fired when the user clicks a point on the chart. */
  onClickDate?: (isoDate: string) => void;
  /** When user pans near the left edge, request an earlier chunk of data. */
  onNeedEarlierData?: () => void;
  canLoadEarlier?: boolean;
};

/**
 * Strategy breadth LWC: member_count + optional measure_series from probe/range.
 * Toggle-gated parent must own fetch; this only renders.
 *
 * When earlier bars are prepended, the visible x-window is preserved (logical
 * range shifted by the added bar count) — no fitContent / scale jump.
 */
export function ProbeRangeChart({
  dates,
  memberCounts,
  measureSeries,
  membersOnly = false,
  className,
  height = 180,
  onHoverDate,
  onClickDate,
  onNeedEarlierData,
  canLoadEarlier = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const memberSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const measureSeriesRefs = useRef<ISeriesApi<"Line">[]>([]);
  const hoverRef = useRef(onHoverDate);
  hoverRef.current = onHoverDate;
  const clickRef = useRef(onClickDate);
  clickRef.current = onClickDate;
  const needEarlierRef = useRef(onNeedEarlierData);
  needEarlierRef.current = onNeedEarlierData;
  const canLoadEarlierRef = useRef(canLoadEarlier);
  canLoadEarlierRef.current = canLoadEarlier;
  const datesLenRef = useRef(0);
  const loadingEarlierRef = useRef(false);
  const suppressEarlierUntilRef = useRef(0);
  const lastLogicalFromRef = useRef<number | null>(null);

  // Create chart once.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#64748b",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.15)" },
        horzLines: { color: "rgba(148,163,184,0.15)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: false },
      crosshair: { mode: 1 },
    });
    chartRef.current = chart;

    const memberSeries = chart.addSeries(LineSeries, {
      color: "#3b82f6",
      lineWidth: 2,
      title: "members",
      priceScaleId: "right",
    });
    memberSeriesRef.current = memberSeries;

    const onMove = (param: MouseEventParams) => {
      const cb = hoverRef.current;
      if (!cb) return;
      if (!param.point || param.time === undefined) {
        cb(null);
        return;
      }
      cb(lwcTimeToIsoDate(param.time));
    };
    chart.subscribeCrosshairMove(onMove);

    const onClick = (param: MouseEventParams) => {
      const cb = clickRef.current;
      if (!cb || param.time === undefined || param.time === null) return;
      const iso = lwcTimeToIsoDate(param.time);
      if (!iso) return;
      cb(iso);
    };
    chart.subscribeClick(onClick);

    const onRange = (range: LogicalRange | null) => {
      if (!range) return;
      const prevFrom = lastLogicalFromRef.current;
      lastLogicalFromRef.current = range.from;

      if (!canLoadEarlierRef.current || loadingEarlierRef.current) return;
      if (performance.now() < suppressEarlierUntilRef.current) return;
      // Only react to the user panning left (from decreases), never programmatic restore.
      if (prevFrom == null || range.from >= prevFrom - 0.01) return;
      if (range.from > EARLIER_EDGE_BARS) return;

      const cb = needEarlierRef.current;
      if (!cb) return;
      loadingEarlierRef.current = true;
      cb();
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(container);
    chart.applyOptions({ width: container.clientWidth });

    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.unsubscribeClick(onClick);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      memberSeriesRef.current = null;
      measureSeriesRefs.current = [];
    };
  }, [height]);

  // Push series data when the parent range changes.
  useEffect(() => {
    const chart = chartRef.current;
    const memberSeries = memberSeriesRef.current;
    if (!chart || !memberSeries) return;

    const mapped = buildProbeRangeSeries({
      dates,
      member_counts: memberCounts,
      measure_series: membersOnly ? undefined : measureSeries,
    });
    if (mapped.memberCount.length === 0 && mapped.measures.every((m) => m.points.length === 0)) {
      return;
    }

    const prevLen = datesLenRef.current;
    const grewLeft = dates.length > prevLen && prevLen > 0;
    const shrunk = dates.length < prevLen;

    // Capture viewport against the *current* series before replacing data.
    const savedLogical = chart.timeScale().getVisibleLogicalRange();
    const savedTime = chart.timeScale().getVisibleRange();

    suppressEarlierUntilRef.current = performance.now() + SUPPRESS_EARLIER_MS;

    memberSeries.setData(
      mapped.memberCount.map((p) => ({ time: p.time as Time, value: p.value })),
    );

    for (const s of measureSeriesRefs.current) {
      try {
        chart.removeSeries(s);
      } catch {
        /* already gone */
      }
    }
    measureSeriesRefs.current = [];
    if (!membersOnly && mapped.measures.length) {
      mapped.measures.forEach((m, i) => {
        const s = chart.addSeries(LineSeries, {
          color: MEASURE_COLORS[i % MEASURE_COLORS.length]!,
          lineWidth: 1,
          title: m.id,
          priceScaleId: "right",
        });
        s.setData(m.points.map((p) => ({ time: p.time as Time, value: p.value })));
        measureSeriesRefs.current.push(s);
      });
    }

    datesLenRef.current = dates.length;

    if (prevLen === 0 || shrunk) {
      // First paint or pipeline/window reset — show the full loaded chunk.
      chart.timeScale().fitContent();
      loadingEarlierRef.current = false;
      lastLogicalFromRef.current = null;
    } else if (grewLeft && savedLogical) {
      // Bars prepended: shift logical window so the same dates stay on screen
      // at the same zoom (no fitContent / no stretch-to-end).
      const added = dates.length - prevLen;
      chart.timeScale().setVisibleLogicalRange({
        from: savedLogical.from + added,
        to: savedLogical.to + added,
      });
      loadingEarlierRef.current = false;
    } else if (savedTime) {
      // Same bar count (e.g. measure toggles) — keep the time window.
      chart.timeScale().setVisibleRange(savedTime);
      loadingEarlierRef.current = false;
    } else {
      chart.timeScale().fitContent();
      loadingEarlierRef.current = false;
    }

    const logical = chart.timeScale().getVisibleLogicalRange();
    if (logical) lastLogicalFromRef.current = logical.from;

    // LWC sometimes needs a layout pass before the first paint is visible.
    requestAnimationFrame(() => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
    });
  }, [dates, memberCounts, measureSeries, membersOnly]);

  useEffect(() => {
    if (!canLoadEarlier) loadingEarlierRef.current = false;
  }, [canLoadEarlier]);

  const empty =
    (!dates?.length || !memberCounts?.length) &&
    (membersOnly || !Object.keys(measureSeries || {}).length);

  if (empty) {
    return (
      <p className="font-mono text-[10px] text-ink-faint">No range series to chart.</p>
    );
  }

  return (
    <div
      ref={containerRef}
      className={className ?? "mt-1 w-full rounded border border-line bg-surface"}
      style={{ height }}
      role="img"
      aria-label="Universe member count over time"
    />
  );
}
