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
import { Card } from "@sb/webapp-core/components/ui/card";
import { Button } from "@sb/webapp-core/components/ui/button";

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

const CANDIDATE_COLUMN_LABELS: Readonly<Record<string, string>> = {
  ticker: "Ticker",
  close: "Price",
  overall_score: "Score",
  rs_rating: "RS",
  atr_14_pct: "ATR %",
  days_in_universe: "Days in universe",
};

function formatCandidateValue(column: string, value: unknown): string {
  if (value == null || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);

  if (column === "close") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric);
  }
  if (column === "overall_score") return numeric.toFixed(1);
  if (column === "rs_rating" || column === "days_in_universe") {
    return Math.round(numeric).toLocaleString("en-US");
  }
  if (column === "atr_14_pct") return `${numeric.toFixed(1)}%`;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(numeric);
}

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

  const [historyOpen, setHistoryOpen] = useState(false);
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
    if (pinnedDate) return;
    const next = hoverDate || asOf;
    if (!next) {
      setQueryDate("");
      return;
    }
    const t = window.setTimeout(() => setQueryDate(next), 150);
    return () => window.clearTimeout(t);
  }, [hoverDate, asOf, pinnedDate]);

  useEffect(() => {
    if (asOf && !queryDate && !pinnedDate) setQueryDate(asOf);
  }, [asOf, queryDate, pinnedDate]);

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
    enabled: Boolean(tableDate),
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

  function handleOpenSortPicker() {
    openPicker({
      use: "sort",
      fields,
      title: "Sort candidate stocks",
      actionLabel: "Sort by this field",
      initialFieldName: sortField,
      onPick: (pick) => {
        if (pick.kind === "field") setSortField(pick.field.name);
      },
    });
  }

  return (
    <Card className="space-y-3.5 p-4 shadow-sm">
      <FilterTreeSlotEditor filters={screen} fields={fields} onChange={onChangeScreen} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2">
          <div className="text-[11px] text-muted-foreground">
            {asofQuery.isLoading ? "Loading…" : `${asofQuery.data?.count ?? allRows.length} matches`}
            {tableDate ? ` · ${tableDate}` : ""}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              type="button"
              onClick={handleOpenSortPicker}
              variant="ghost"
              size="sm"
              className="h-8 px-2 text-xs"
              aria-label={`Sort candidate stocks by ${sortField}`}
            >
              Sort <span className="max-w-20 truncate font-mono text-muted-foreground">{sortField}</span>
            </Button>
          </div>
        </div>
        <div className="space-y-2 pt-2">
              <div className="hidden items-center justify-between font-mono text-[10px] text-ink-muted md:flex">
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
                    <Button
                      type="button"
                      variant="link"
                      size="sm"
                      className="h-auto p-0 text-[10px]"
                      onClick={() => {
                        setPinnedDate(null);
                        setHoverDate(null);
                        setQueryDate(asOf);
                      }}
                    >
                      reset
                    </Button>
                  ) : null}
                </span>
                <span>
                  showing {shownRows.length}/
                  {asofQuery.isLoading
                    ? "…"
                    : String(asofQuery.data?.count ?? allRows.length)}
                </span>
              </div>
              <div className="hidden flex-wrap items-center gap-1 md:flex">
                {extraSelect.map((col) => (
                    <Button
                    key={col}
                    type="button"
                    onClick={() =>
                      setExtraSelect((prev) => prev.filter((c) => c !== col))
                    }
                      variant="outline"
                      size="sm"
                      className="h-7 px-2 font-mono text-[10px]"
                    title={`Remove ${col}`}
                  >
                    {col} ×
                    </Button>
                ))}
                <Button
                  type="button"
                  onClick={handleAddColumn}
                  disabled={extraSelect.length >= MAX_EXTRA_SELECT}
                  variant="outline"
                  size="sm"
                  className="h-7 border-dashed px-2 font-mono text-[10px]"
                >
                  + column
                </Button>
              </div>
              {asofQuery.error && (
                <p className="font-mono text-[10px] text-danger">
                  {(asofQuery.error as Error).message}
                </p>
              )}
              <div data-testid="universe-candidates-table" className="hidden md:block">
                <MembershipAsOfTable
                  columns={previewCols}
                  rows={shownRows}
                  columnLabels={CANDIDATE_COLUMN_LABELS}
                  formatCell={(column, value) => formatCandidateValue(column, value)}
                  density="comfortable"
                  sortField={sortField}
                  sortDir={sortDir}
                  sortableCols={sortableCols}
                  selectedTicker={chartTicker}
                  onSelectTicker={openTickerChart}
                  onSort={handleColumnHeaderClick}
                  onScroll={onTableScroll}
                  loading={asofQuery.isLoading}
                  hint={chartTicker ? undefined : "Select a ticker to view its chart."}
                />
              </div>
              <div className="grid gap-1.5 md:hidden">
                {shownRows.map((row, index) => {
                  const ticker = String(row.ticker ?? "").trim().toUpperCase();
                  const display = (value: unknown, decimals = 0) => {
                    const n = Number(value);
                    return value == null || value === "" || !Number.isFinite(n)
                      ? "—"
                      : decimals ? n.toFixed(decimals) : String(Math.round(n));
                  };
                  return (
                    <article key={`${ticker}-${index}`} className="rounded-md border border-border bg-background px-3 py-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="w-6 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">{index + 1}</span>
                          <Button
                            type="button"
                            onClick={() => openTickerChart(ticker)}
                            variant="link"
                            size="sm"
                            className="h-8 min-w-11 justify-start p-0 font-mono font-semibold text-accent"
                            title={`Open ${ticker} chart at ${tableDate}`}
                          >
                            {ticker}
                          </Button>
                        </div>
                        <span className="font-mono text-sm font-semibold tabular-nums">${display(row.close, 2)}</span>
                      </div>
                      <div className="mt-1 grid grid-cols-3 gap-2 border-t border-border/70 pt-1.5 text-[11px]">
                        <div><span className="block text-[9px] uppercase tracking-wide text-muted-foreground">Score</span><span className="font-mono tabular-nums">{display(row.overall_score)}</span></div>
                        <div><span className="block text-[9px] uppercase tracking-wide text-muted-foreground">RS</span><span className="font-mono tabular-nums">{display(row.rs_rating)}</span></div>
                        <div><span className="block text-[9px] uppercase tracking-wide text-muted-foreground">ATR</span><span className="font-mono tabular-nums">{display(row.atr_14_pct, 1)}{row.atr_14_pct == null ? "" : "%"}</span></div>
                      </div>
                    </article>
                  );
                })}
                {asofQuery.isLoading && !shownRows.length ? (
                  <p className="px-2 py-4 text-center text-xs text-muted-foreground">Loading…</p>
                ) : null}
                {!asofQuery.isLoading && !shownRows.length ? (
                  <p className="px-2 py-4 text-center text-xs text-muted-foreground">No stocks match this universe on the selected date.</p>
                ) : null}
                {hasMoreRows ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-9 w-full"
                    onClick={() => setVisibleRows((n) => Math.min(n + TABLE_PAGE, allRows.length))}
                  >
                    Show more · {allRows.length - shownRows.length} remaining
                  </Button>
                ) : null}
              </div>
              <Button
                type="button"
                onClick={() => setHistoryOpen((open) => !open)}
                variant="ghost"
                size="sm"
                className="h-8 w-full justify-between px-1 text-left text-xs text-muted-foreground"
                aria-expanded={historyOpen}
              >
                <span>Membership history</span>
                <span aria-hidden="true">{historyOpen ? "▾" : "▸"}</span>
              </Button>
              {historyOpen && (
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
              )}
              {chartTicker ? (
                <MembershipTickerInspect
                  ticker={chartTicker}
                  asOfDate={tableDate || ""}
                  onClose={() => setChartTicker(null)}
                />
              ) : null}
        </div>
      </div>
    </Card>
  );
}
