import { useEffect, useMemo, useState, type UIEvent } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchFields, previewIr } from "../../api/screens";
import type { OrderDirection, ScreenField, UniverseQueryV1 } from "../../types";
import type { FilterTree } from "../strategy/StrategyDocument";
import { FilterTreeSlotEditor } from "./FilterTreeSlotEditor";
import {
  filterTreesToIr,
} from "../../lib/filterTreeChips";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import {
  MembershipAsOfTable,
  MembershipTickerInspect,
} from "../MembershipWorkbench";
import { MembershipOverTime } from "./MembershipOverTime";
import { useFieldPicker } from "./FieldPickerProvider";

export type UniverseChoice =
  | { kind: "inline" }
  | { kind: "saved"; id: number | string }
  | { kind: "preset"; id: string };

/** Required asof columns — authors cannot remove these (NTH-1). */
export const REQUIRED_MEMBERSHIP_SELECT = [
  "ticker",
  "close",
  "overall_score",
  "rs_rating",
  "atr_14_pct",
] as const;

/** Enrich-only display cols — not IR-selectable / not sortable via order_by. */
const ENRICH_ONLY_COLS = new Set(["exchange"]);

const MAX_EXTRA_SELECT = 8;

/** Table shows first page; scroll loads more from the cached preview. */
const TABLE_PAGE = 10;
/** Asof preview fetch — schema max; chart counts are uncapped server-side. */
const ASOF_FETCH_LIMIT = 5000;
const DEFAULT_SORT_FIELD = "overall_score";
const DEFAULT_SORT_DIR: OrderDirection = "desc";

function yearBackFrom(endDate: string): string {
  if (!endDate) return "";
  const d = new Date(`${endDate}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

function mergeMembershipSelect(
  extraSelect: string[],
  sortField: string,
): string[] {
  const select: string[] = [...REQUIRED_MEMBERSHIP_SELECT];
  for (const col of extraSelect) {
    const name = col.trim();
    if (
      !name ||
      ENRICH_ONLY_COLS.has(name) ||
      select.includes(name) ||
      select.length >= REQUIRED_MEMBERSHIP_SELECT.length + MAX_EXTRA_SELECT
    ) {
      continue;
    }
    select.push(name);
  }
  if (!select.includes(sortField) && !ENRICH_ONLY_COLS.has(sortField)) {
    select.push(sortField);
  }
  return select;
}

/** Hygiene screen FilterTree[] → UniverseQueryV1 for range/asof. */
export function screenTreesToUniverseSpec(
  screen: FilterTree[],
  opts?: {
    sortField?: string;
    sortDir?: OrderDirection;
    /** Optional allowlisted L7 columns beyond required (NTH-1). */
    extraSelect?: string[];
  },
): UniverseQueryV1 {
  const sortField = opts?.sortField ?? DEFAULT_SORT_FIELD;
  const sortDir = opts?.sortDir ?? DEFAULT_SORT_DIR;
  const select = mergeMembershipSelect(opts?.extraSelect ?? [], sortField);
  return {
    version: 1,
    from: "screener",
    select,
    where: filterTreesToIr(screen),
    order_by: [{ field: sortField, direction: sortDir }],
    limit_per_day: ASOF_FETCH_LIMIT,
  };
}

interface UniverseSlotCardProps {
  screen: FilterTree[];
  onChangeScreen: (screen: FilterTree[]) => void;
  /** Evaluation end date (as-of / range end). */
  asOf?: string;
  /** Evaluation start date (range start). Falls back to asOf−1y if omitted. */
  startDate?: string;
}

export function UniverseSlotCard({
  screen,
  onChangeScreen,
  asOf = "",
  startDate: startDateProp = "",
}: UniverseSlotCardProps) {
  const { openPicker } = useFieldPicker();
  const fieldsQuery = useQuery({
    queryKey: ["screen-fields"],
    queryFn: fetchFields,
    staleTime: 5 * 60_000,
  });
  const fields: ScreenField[] = fieldsQuery.data ?? [];

  const [membershipOpen, setMembershipOpen] = useState(false);
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [pinnedDate, setPinnedDate] = useState<string | null>(null);
  const [queryDate, setQueryDate] = useState<string>("");
  const [visibleRows, setVisibleRows] = useState(TABLE_PAGE);
  const [sortField, setSortField] = useState(DEFAULT_SORT_FIELD);
  const [sortDir, setSortDir] = useState<OrderDirection>(DEFAULT_SORT_DIR);
  const [extraSelect, setExtraSelect] = useState<string[]>([]);
  const [chartTicker, setChartTicker] = useState<string | null>(null);

  // Range chart is membership counts — sort / extra cols do not affect the line.
  const rangeSpec = useMemo(() => screenTreesToUniverseSpec(screen), [screen]);
  const asofSpec = useMemo(
    () =>
      screenTreesToUniverseSpec(screen, {
        sortField,
        sortDir,
        extraSelect,
      }),
    [screen, sortField, sortDir, extraSelect],
  );
  const tenureStart = useMemo(() => {
    const explicit = (startDateProp || "").trim();
    if (explicit) return explicit;
    return yearBackFrom(asOf);
  }, [startDateProp, asOf]);

  /** Fingerprint so filter edits (and MCP-driven screen updates) refetch the probe. */
  const screenKey = useMemo(() => JSON.stringify(screen), [screen]);
  const liveScreenKey = useDebouncedValue(screenKey, 350);
  /**
   * The chart's from-to window. `to` defaults to the latest date in the screen and both ends
   * are editable — by the fields below or by dragging the chart itself.
   */

  // Click pins; hover only previews when nothing is pinned.
  const tableDate = pinnedDate ?? (queryDate || asOf);

  // Debounce hover → asof query date (~150ms). Ignored while a click pin is active.
  useEffect(() => {
    if (!membershipOpen || pinnedDate) return;
    const next = hoverDate || asOf;
    if (!next) {
      setQueryDate("");
      return;
    }
    const t = window.setTimeout(() => setQueryDate(next), 150);
    return () => window.clearTimeout(t);
  }, [hoverDate, asOf, membershipOpen, pinnedDate]);

  useEffect(() => {
    if (membershipOpen && asOf && !queryDate && !pinnedDate) setQueryDate(asOf);
  }, [membershipOpen, asOf, queryDate, pinnedDate]);

  // Clear pin / chart when evaluation end date or screen changes.
  useEffect(() => {
    setPinnedDate(null);
    setChartTicker(null);
  }, [asOf, liveScreenKey]);

  // Reset visible window when the asof date, screen, or sort changes.
  useEffect(() => {
    setVisibleRows(TABLE_PAGE);
  }, [tableDate, liveScreenKey, sortField, sortDir]);


  // Tenure only on pinned date or evaluation end (not crosshair hover).
  const includeTenure =
    Boolean(pinnedDate) || (Boolean(tableDate) && tableDate === asOf && !hoverDate);

  const asofQuery = useQuery({
    queryKey: [
      "universe-membership-asof",
      tableDate,
      sortField,
      sortDir,
      liveScreenKey,
      JSON.stringify(extraSelect),
      includeTenure,
      tenureStart,
    ],
    queryFn: () =>
      previewIr({
        as_of: tableDate,
        spec: asofSpec,
        include_tenure: includeTenure,
        tenure_start: includeTenure ? tenureStart : undefined,
      }),
    enabled: membershipOpen && Boolean(tableDate),
    staleTime: 0,
    placeholderData: keepPreviousData,
  });

  const allRows = asofQuery.data?.rows ?? [];
  const shownRows = allRows.slice(0, visibleRows);
  const hasMoreRows = visibleRows < allRows.length;

  const previewCols = useMemo(() => {
    const preferred = [
      ...mergeMembershipSelect(extraSelect, sortField),
      ...(includeTenure ? ["days_in_universe"] : []),
    ];
    if (!allRows.length) return preferred;
    const keys = new Set(Object.keys(allRows[0]!).filter((k) => k !== "date"));
    // Keep required even if row sparse; drop optional missing from this page.
    return preferred.filter(
      (k) =>
        keys.has(k) ||
        (REQUIRED_MEMBERSHIP_SELECT as readonly string[]).includes(k) ||
        k === "days_in_universe",
    );
  }, [allRows, extraSelect, sortField, includeTenure]);

  // Only IR select columns can drive server-side order_by (skip enrich-only cols like exchange).
  const sortableCols = useMemo(
    () => new Set(asofSpec.select ?? [...REQUIRED_MEMBERSHIP_SELECT]),
    [asofSpec.select],
  );

  function openTickerChart(ticker: string) {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setChartTicker(t);
    if (tableDate) {
      setPinnedDate(tableDate);
      setQueryDate(tableDate);
    }
  }

  function onTableScroll(e: UIEvent<HTMLDivElement>) {
    if (!hasMoreRows) return;
    const el = e.currentTarget;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
      setVisibleRows((n) => Math.min(n + TABLE_PAGE, allRows.length));
    }
  }

  function handleColumnHeaderClick(col: string) {
    if (!sortableCols.has(col)) return;
    if (sortField === col) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortField(col);
      setSortDir(col === "ticker" ? "asc" : "desc");
    }
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
          ENRICH_ONLY_COLS.has(name) ||
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

  return (
    <div className="space-y-3.5 rounded-lg border border-line bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-2.5">
        <h4 className="text-[13px] font-bold text-ink">1. Universe Selection</h4>
      </div>

      {/* No tinted inner box: the top level *is* the screen, so the clauses sit on the card. */}
      <div className="space-y-3 text-[11px]">
        <FilterTreeSlotEditor filters={screen} fields={fields} onChange={onChangeScreen} />
      </div>

      <div className="rounded border border-line bg-surface-sunk/40">
        <button
          type="button"
          onClick={() => setMembershipOpen((v) => !v)}
          className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-[10.5px] font-semibold uppercase tracking-wide text-ink-muted hover:bg-surface-raised/50"
        >
          <span>Membership over time</span>
          <span className="font-mono text-[10px]">{membershipOpen ? "▼" : "▶"}</span>
        </button>

        {membershipOpen && (
          <div className="space-y-2 border-t border-line px-2.5 py-2">
            <MembershipOverTime
              spec={rangeSpec}
              asOf={asOf}
              startDate={tenureStart}
              onHoverDate={setHoverDate}
              onPickDate={(date) => {
                setPinnedDate(date);
                setQueryDate(date);
              }}
            />

            <div className="space-y-1">
              <div className="flex items-center justify-between font-mono text-[10px] text-ink-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span>
                    as of{" "}
                    <span className="text-ink">{tableDate || "—"}</span>
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
                </span>
                <span>
                  showing {shownRows.length}/
                  {asofQuery.isLoading
                    ? "…"
                    : String(asofQuery.data?.count ?? allRows.length)}
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
                sortableCols={sortableCols}
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
                <p className="font-mono text-[10px] text-center text-ink-faint">
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
    </div>
  );
}
