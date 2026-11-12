import { useEffect, useMemo, useState, type UIEvent } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchScreenProbe } from "../api/screens";
import type { OrderDirection } from "../types";
import { cn } from "../lib/utils";
import { useProgressiveProbeRange } from "../lib/useProgressiveProbeRange";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { ProbeRangeChart } from "./ProbeRangeChart";
import {
  MembershipAsOfTable,
  MembershipTickerInspect,
} from "./MembershipWorkbench";
import type { PipelineDocument } from "./strategy/StrategyDocument";
import { useFieldPicker } from "./studio/FieldPickerProvider";
import {
  REQUIRED_MEMBERSHIP_SELECT,
} from "./studio/UniverseSlotCard";

const TABLE_PAGE = 10;
const ASOF_FETCH_LIMIT = 5000;
const MAX_EXTRA_SELECT = 8;
const ENRICH_ONLY = new Set(["exchange"]);

function yearBackStart(endDate: string): string {
  if (!endDate) return "";
  const d = new Date(`${endDate}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

/**
 * Alpha-bottom membership probe: universe members line + stage toggles + cumulative,
 * chart and sortable asof table together (C-SCREEN-PROBE-V1 SPA surface).
 */
export function AlphaMembershipProbe({
  pipeline,
  asOf,
  startDate: startDateProp,
}: {
  pipeline: PipelineDocument;
  asOf: string;
  /** Backtest/evaluation start. Falls back to asOf−1y if omitted. */
  startDate?: string;
}) {
  const { openPicker, fields } = useFieldPicker();
  const [open, setOpen] = useState(false);
  const [cumulative, setCumulative] = useState(false);
  const [enabled, setEnabled] = useState<string[]>([]);
  const [enabledInit, setEnabledInit] = useState(false);
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [pinnedDate, setPinnedDate] = useState<string | null>(null);
  const [queryDate, setQueryDate] = useState("");
  const [visibleRows, setVisibleRows] = useState(TABLE_PAGE);
  const gateRankKeys = useMemo(() => {
    const rank = pipeline.bindings?.alpha_rank;
    if (rank && rank.length >= 1) return rank.filter(Boolean);
    return [] as string[];
  }, [pipeline.bindings?.alpha_rank]);
  const [sortField, setSortField] = useState(() => gateRankKeys[0] || "rs_rating");
  const [sortDir, setSortDir] = useState<OrderDirection>("desc");
  const [sortKeys, setSortKeys] = useState<string[]>(() =>
    gateRankKeys.length ? [...gateRankKeys] : [],
  );
  const [extraSelect, setExtraSelect] = useState<string[]>([]);
  /** Ticker opened for chart + as-of conditions rail (below the membership table). */
  const [chartTicker, setChartTicker] = useState<string | null>(null);

  const tenureStart = useMemo(() => {
    const explicit = (startDateProp || "").trim();
    if (explicit) return explicit;
    return yearBackStart(asOf);
  }, [startDateProp, asOf]);

  /** Fingerprint so UI edits and MCP Accept both reset + refetch the probe. */
  const pipelineKey = useMemo(() => JSON.stringify(pipeline), [pipeline]);
  /** Debounce so measure/universe edits refetch once after typing settles. */
  const livePipelineKey = useDebouncedValue(pipelineKey, 350);
  const {
    rangeStart,
    canExtend,
    extendEarlier,
    chunkDays,
  } = useProgressiveProbeRange(asOf, tenureStart, livePipelineKey);

  const tableDate = pinnedDate ?? (queryDate || asOf);

  const layersQuery = useQuery({
    queryKey: ["alpha-membership-layers", livePipelineKey],
    queryFn: () =>
      fetchScreenProbe({
        view: "layers",
        pipeline,
        probe_mode: "measures",
      }),
    enabled: open,
    staleTime: 0,
  });

  const toggleAliases = useMemo(() => {
    const aliases = (layersQuery.data?.computed_aliases as string[] | undefined) ?? [];
    // Bool/gate toggles for the funnel — exclude number rank measures.
    const rank = new Set(gateRankKeys);
    return aliases.filter((a) => a && !rank.has(a));
  }, [layersQuery.data?.computed_aliases, gateRankKeys]);

  // Default: all stage toggles on once layers settle (including zero-stage pipelines).
  useEffect(() => {
    if (!open || enabledInit || !layersQuery.isFetched) return;
    if (toggleAliases.length) setEnabled(toggleAliases);
    setEnabledInit(true);
  }, [open, enabledInit, toggleAliases, layersQuery.isFetched]);

  useEffect(() => {
    setEnabledInit(false);
    setEnabled([]);
    setPinnedDate(null);
    setChartTicker(null);
  }, [livePipelineKey]);

  useEffect(() => {
    setSortKeys([...gateRankKeys]);
    setSortField(gateRankKeys[0] || "rs_rating");
    setSortDir("desc");
  }, [livePipelineKey, gateRankKeys]);

  function applyGateRanking() {
    const keys = [...gateRankKeys];
    setSortKeys(keys);
    setSortField(keys[0] || "rs_rating");
    setSortDir("desc");
  }
  useEffect(() => {
    if (!open || pinnedDate) return;
    const next = hoverDate || asOf;
    if (!next) {
      setQueryDate("");
      return;
    }
    const t = window.setTimeout(() => setQueryDate(next), 150);
    return () => window.clearTimeout(t);
  }, [hoverDate, asOf, open, pinnedDate]);

  useEffect(() => {
    if (open && asOf && !queryDate && !pinnedDate) setQueryDate(asOf);
  }, [open, asOf, queryDate, pinnedDate]);

  useEffect(() => {
    setPinnedDate(null);
  }, [asOf]);

  useEffect(() => {
    setVisibleRows(TABLE_PAGE);
  }, [tableDate, sortField, sortDir, cumulative, enabled]);

  const rangeQuery = useQuery({
    queryKey: [
      "alpha-membership-range",
      asOf,
      rangeStart,
      livePipelineKey,
      cumulative,
      enabled.join(","),
    ],
    queryFn: () =>
      fetchScreenProbe({
        view: "range",
        pipeline,
        probe_mode: "measures",
        start_date: rangeStart,
        end_date: asOf,
        enabled_bindings: enabled,
        cumulative,
      }),
    // Wait for stage toggles so we don't fire an empty-enabled fetch then a second full one.
    enabled: open && enabledInit && Boolean(asOf && rangeStart),
    staleTime: 0,
    placeholderData: keepPreviousData,
  });

  // Tenure only on pinned date or evaluation end (not crosshair hover).
  const includeTenure =
    Boolean(pinnedDate) || (Boolean(tableDate) && tableDate === asOf && !hoverDate);

  const asofQuery = useQuery({
    queryKey: [
      "alpha-membership-asof",
      tableDate,
      livePipelineKey,
      sortKeys.join(","),
      sortDir,
      extraSelect.join(","),
      includeTenure,
      tenureStart,
      ((layersQuery.data?.computed_aliases as string[] | undefined) ?? []).join(","),
    ],
    queryFn: () => {
      const computed = new Set(
        (layersQuery.data?.computed_aliases as string[] | undefined) ?? [],
      );
      // Never put computed / rank aliases into extra_select (L7-only).
      // Server keeps order_by fields that exist in select ∪ computed.
      const selectOnly = extraSelect.filter((k) => k && !computed.has(k));
      const keys = sortKeys.length ? sortKeys : [sortField || "rs_rating"];
      return fetchScreenProbe({
        view: "asof",
        pipeline,
        probe_mode: "measures",
        as_of: tableDate,
        limit: ASOF_FETCH_LIMIT,
        extra_select: [...new Set(selectOnly)],
        order_by: keys.filter(Boolean).map((field) => ({
          field,
          direction: sortDir,
        })),
        include_tenure: includeTenure,
        tenure_start: includeTenure ? tenureStart : undefined,
      });
    },
    enabled: open && Boolean(tableDate) && layersQuery.isFetched,
    staleTime: 0,
    placeholderData: keepPreviousData,
  });
  const dates = (rangeQuery.data?.dates as string[]) ?? [];
  const memberCounts = (rangeQuery.data?.member_counts as number[]) ?? [];
  const rawMeasures =
    (rangeQuery.data?.measure_series as Record<string, number[]>) ?? {};

  const chartMeasures = useMemo(() => {
    if (cumulative) {
      if (enabled.length && rawMeasures.funnel) {
        return { funnel: rawMeasures.funnel };
      }
      return {};
    }
    const out: Record<string, number[]> = {};
    for (const id of enabled) {
      if (rawMeasures[id]) out[id] = rawMeasures[id]!;
    }
    return out;
  }, [cumulative, enabled, rawMeasures]);

  const allRows = useMemo(() => {
    const rows = (asofQuery.data?.rows as Array<Record<string, unknown>>) ?? [];
    if (!cumulative || !enabled.length) return rows;
    return rows.filter((row) => enabled.every((a) => Number(row[a] ?? 0) >= 1));
  }, [asofQuery.data?.rows, cumulative, enabled]);

  const sortedRows = useMemo(() => {
    const rows = [...allRows];
    const keys =
      sortKeys.length > 0 ? sortKeys : [sortField].filter(Boolean);
    const dir = sortDir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      for (const key of keys) {
        const av = a[key];
        const bv = b[key];
        if (av == null && bv == null) continue;
        if (av == null) return 1;
        if (bv == null) return -1;
        let cmp = 0;
        if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
        else cmp = String(av).localeCompare(String(bv));
        if (cmp !== 0) return cmp * dir;
      }
      return 0;
    });
    return rows;
  }, [allRows, sortField, sortDir, sortKeys]);

  const shownRows = sortedRows.slice(0, visibleRows);
  const hasMoreRows = visibleRows < sortedRows.length;

  const previewCols = useMemo(() => {
    const preferred = [
      "ticker",
      ...gateRankKeys,
      ...toggleAliases,
      ...REQUIRED_MEMBERSHIP_SELECT.filter(
        (k) => k !== "ticker" && !gateRankKeys.includes(k),
      ),
      ...extraSelect,
      ...(includeTenure ? ["days_in_universe"] : []),
    ];
    if (sortField && !preferred.includes(sortField)) preferred.push(sortField);
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const k of preferred) {
      if (seen.has(k)) continue;
      seen.add(k);
      ordered.push(k);
    }
    if (!sortedRows.length) return ordered.slice(0, 12);
    const keys = new Set(Object.keys(sortedRows[0]!).filter((k) => k !== "date"));
    return ordered.filter((k) => keys.has(k)).slice(0, 14);
  }, [
    sortedRows,
    toggleAliases,
    extraSelect,
    sortField,
    includeTenure,
    gateRankKeys,
  ]);

  function openTickerChart(tickerRaw: string) {
    const ticker = String(tickerRaw || "")
      .trim()
      .toUpperCase();
    if (!ticker) return;
    setChartTicker(ticker);
    // Pin the probe date so hover scrubbing does not move the time slice mid-inspect.
    if (tableDate) {
      setPinnedDate(tableDate);
      setQueryDate(tableDate);
    }
  }

  function toggleBinding(id: string) {
    setEnabled((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function handleAddColumn() {
    openPicker({
      use: "column",
      fields,
      title: "Add return field",
      actionLabel: "Add column",
      mode: "fields",
      onPick: (pick) => {
        if (pick.kind !== "field") return;
        const name = pick.field.name;
        if (
          ENRICH_ONLY.has(name) ||
          (REQUIRED_MEMBERSHIP_SELECT as readonly string[]).includes(name)
        ) {
          return;
        }
        setExtraSelect((prev) => {
          if (prev.includes(name) || prev.length >= MAX_EXTRA_SELECT) return prev;
          return [...prev, name];
        });
      },
    });
  }

  function onTableScroll(e: UIEvent<HTMLDivElement>) {
    if (!hasMoreRows) return;
    const el = e.currentTarget;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
      setVisibleRows((n) => Math.min(n + TABLE_PAGE, sortedRows.length));
    }
  }

  function handleColumnHeaderClick(col: string) {
    if (sortField === col && sortKeys.length <= 1) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKeys([col]);
      setSortField(col);
      setSortDir(col === "ticker" ? "asc" : "desc");
    }
  }

  const layerLabels = useMemo(() => {
    const layers =
      (layersQuery.data?.layers as Array<{ binding_id: string; stage_name: string }>) ||
      [];
    const map = new Map(layers.map((l) => [l.binding_id, l.stage_name]));
    return map;
  }, [layersQuery.data?.layers]);

  return (
    <div className="rounded border border-line bg-surface-sunk/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-[10.5px] font-semibold uppercase tracking-wide text-ink-muted hover:bg-surface-raised/50"
      >
        <span>Membership probe</span>
        <span className="font-mono text-[10px]">{open ? "▼" : "▶"}</span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-line px-2.5 py-2">
          {!asOf && (
            <p className="font-mono text-[10px] text-ink-faint">
              Set evaluation end date to load membership.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-1">
            <button
              type="button"
              onClick={() => setCumulative((v) => !v)}
              className={cn(
                "rounded border px-1.5 py-0.5 text-[10px] font-mono",
                cumulative
                  ? "border-accent bg-accent/15 text-accent-ink"
                  : "border-line text-ink-muted hover:bg-surface",
              )}
              title="ON: AND enabled stages (funnel). OFF: one line per enabled stage; full universe table."
            >
              cumulative {cumulative ? "on" : "off"}
            </button>
            {toggleAliases.map((id) => {
              const on = enabled.includes(id);
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleBinding(id)}
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[10px] font-mono",
                    on
                      ? "border-accent bg-accent/15 text-accent-ink"
                      : "border-line text-ink-muted hover:bg-surface",
                  )}
                  title={layerLabels.get(id) || id}
                >
                  {id}
                </button>
              );
            })}
            {(layersQuery.isLoading || (!enabledInit && open)) && (
              <span className="font-mono text-[10px] text-ink-faint">loading stages…</span>
            )}
          </div>

          {(rangeQuery.isLoading || (rangeQuery.isFetching && !rangeQuery.data)) && (
            <p className="font-mono text-[10px] text-ink-muted">Querying range…</p>
          )}
          {rangeQuery.isFetching && rangeQuery.data ? (
            <p className="font-mono text-[10px] text-ink-faint">Updating range…</p>
          ) : null}
          {rangeQuery.error && (
            <p className="font-mono text-[10px] text-danger">
              {(rangeQuery.error as Error).message}
            </p>
          )}
          {rangeQuery.data && (
            <>
              <p className="font-mono text-[10px] text-ink-muted">
                days=
                {String(
                  (rangeQuery.data.summary as { trading_days?: number })?.trading_days ??
                    dates.length,
                )}{" "}
                · avg members=
                {String(
                  (rangeQuery.data.summary as { avg_members_per_day?: number })
                    ?.avg_members_per_day ?? "—",
                )}
                {cumulative ? " · funnel=AND(enabled)" : " · overlays=pass counts"}
              </p>
              <ProbeRangeChart
                dates={dates}
                memberCounts={memberCounts}
                measureSeries={chartMeasures}
                height={160}
                onHoverDate={setHoverDate}
                onClickDate={(d) => {
                  setPinnedDate(d);
                  setQueryDate(d);
                }}
                canLoadEarlier={canExtend}
                onNeedEarlierData={extendEarlier}
              />
              {canExtend ? (
                <button
                  type="button"
                  onClick={extendEarlier}
                  disabled={rangeQuery.isFetching}
                  className="font-mono text-[10px] text-accent hover:underline disabled:opacity-50"
                >
                  {rangeQuery.isFetching ? "Loading…" : `Load earlier (+${chunkDays}d)`}
                </button>
              ) : null}
            </>
          )}

          <div className="space-y-1">
            <div className="flex items-center justify-between font-mono text-[10px] text-ink-muted">
              <span className="inline-flex items-center gap-1.5">
                <span>
                  as of <span className="text-ink">{tableDate || "—"}</span>
                  {pinnedDate ? (
                    <span className="text-ink-faint"> (pinned)</span>
                  ) : hoverDate && hoverDate !== asOf ? (
                    <span className="text-ink-faint"> (hover)</span>
                  ) : null}
                </span>
                {pinnedDate && pinnedDate !== asOf ? (
                  <button
                    type="button"
                    className="text-accent underline-offset-2 hover:underline"
                    onClick={() => {
                      setPinnedDate(null);
                      setHoverDate(null);
                      setQueryDate(asOf);
                    }}
                  >
                    reset
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={applyGateRanking}
                  className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:border-accent hover:text-accent"
                  title={`Sort by ${gateRankKeys.join(" → ")}`}
                >
                  Use gate ranking
                </button>
              </span>
              <span>
                sort: {sortKeys.join(" → ") || sortField} {sortDir === "desc" ? "↓" : "↑"} ·
                showing {shownRows.length}/
                {asofQuery.isLoading ? "…" : String(sortedRows.length)}
                {cumulative ? " (funnel)" : " (universe)"}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              {extraSelect.map((col) => (
                <button
                  key={col}
                  type="button"
                  onClick={() =>
                    setExtraSelect((prev) => prev.filter((c) => c !== col))
                  }
                  className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-danger hover:text-danger"
                  title={`Remove ${col}`}
                >
                  {col} ×
                </button>
              ))}
              <button
                type="button"
                onClick={handleAddColumn}
                disabled={extraSelect.length >= MAX_EXTRA_SELECT}
                className="rounded border border-dashed border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:border-accent hover:text-accent disabled:opacity-40"
              >
                + column
              </button>
            </div>
            {asofQuery.error && (
              <p className="font-mono text-[10px] text-danger">
                {(asofQuery.error as Error).message}
              </p>
            )}
            <MembershipAsOfTable
              columns={previewCols}
              rows={shownRows}
              sortField={sortField}
              sortDir={sortDir}
              selectedTicker={chartTicker}
              onSelectTicker={openTickerChart}
              onSort={handleColumnHeaderClick}
              onScroll={onTableScroll}
              loading={asofQuery.isLoading}
              hint={
                chartTicker
                  ? undefined
                  : "Click a ticker to open chart + conditions at the as-of date."
              }
            />
            {hasMoreRows ? (
              <p className="font-mono text-[10px] text-ink-faint text-center">
                Scroll for more…
              </p>
            ) : null}

            {chartTicker ? (
              <MembershipTickerInspect
                ticker={chartTicker}
                asOfDate={tableDate || ""}
                onClose={() => setChartTicker(null)}
              />
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
