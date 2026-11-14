import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { fetchScreenProbe } from "../api/screens";
import { cn } from "../lib/utils";
import type { PipelineDocument } from "./strategy/StrategyDocument";
import { ProbeRangeChart } from "./ProbeRangeChart";

type ProbeMode = "measures" | "members";

const TABLE_PAGE = 10;
const ASOF_FETCH_LIMIT = 5000;

function yearBackStart(endDate: string): string {
  if (!endDate) return "";
  const d = new Date(`${endDate}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

/**
 * Toggle-gated stage-prefix probe (C-SCREEN-PROBE-V1).
 * Closed by default — no compile / CH until opened.
 */
export function ScreenerProbe({
  pipeline,
  throughStageIndex,
  throughBindingId,
  asOf,
  startDate: startDateProp,
  open,
  onOpenChange,
}: {
  pipeline: PipelineDocument;
  throughStageIndex?: number;
  throughBindingId?: string | null;
  asOf: string;
  /** Backtest/evaluation start. Falls back to asOf−1y if omitted. */
  startDate?: string;
  /** Controlled open state so parent can enforce one-open-at-a-time. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [mode, setMode] = useState<ProbeMode>("measures");
  const [pane, setPane] = useState<"layers" | "asof" | "range">("layers");
  const [visibleRows, setVisibleRows] = useState(TABLE_PAGE);
  const startDate = useMemo(() => {
    const explicit = (startDateProp || "").trim();
    if (explicit) return explicit;
    return yearBackStart(asOf);
  }, [startDateProp, asOf]);

  const through = throughBindingId
    ? { binding_id: throughBindingId }
    : throughStageIndex != null
      ? { stage_index: throughStageIndex }
      : undefined;

  useEffect(() => {
    setVisibleRows(TABLE_PAGE);
  }, [asOf, pane, throughBindingId, throughStageIndex]);

  const layersQuery = useQuery({
    queryKey: ["screen-probe-layers", JSON.stringify(pipeline), through, mode],
    queryFn: () =>
      fetchScreenProbe({
        view: "layers",
        pipeline,
        through,
        probe_mode: mode,
      }),
    enabled: open,
    staleTime: 60_000,
  });

  const asofQuery = useQuery({
    queryKey: ["screen-probe-asof", asOf, JSON.stringify(pipeline), through, mode],
    queryFn: () =>
      fetchScreenProbe({
        view: "asof",
        pipeline,
        through,
        probe_mode: mode,
        as_of: asOf,
        limit: ASOF_FETCH_LIMIT,
      }),
    enabled: open && pane === "asof" && Boolean(asOf),
    staleTime: 60_000,
  });

  const rangeQuery = useQuery({
    queryKey: [
      "screen-probe-range",
      asOf,
      startDate,
      JSON.stringify(pipeline),
      through,
      mode,
    ],
    queryFn: () =>
      fetchScreenProbe({
        view: "range",
        pipeline,
        through,
        probe_mode: mode,
        start_date: startDate,
        end_date: asOf,
      }),
    enabled: open && pane === "range" && Boolean(asOf && startDate),
    staleTime: 60_000,
  });

  const layers = layersQuery.data;
  const aliases = (layers?.computed_aliases as string[] | undefined) ?? [];

  return (
    <div className="mt-2 rounded border border-line bg-surface-sunk/40">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className="flex w-full items-center justify-between px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-sunk"
      >
        <span>Probe {throughBindingId ? `(${throughBindingId})` : `stage ${((throughStageIndex ?? 0) + 1)}`}</span>
        <span className="font-mono normal-case">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-line px-2 py-2">
          <div className="flex flex-wrap gap-1">
            {(["measures", "members"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={cn(
                  "rounded border px-1.5 py-0.5 text-[10px] font-mono",
                  mode === m
                    ? "border-accent bg-accent/15 text-accent-ink"
                    : "border-line text-ink-muted hover:bg-surface",
                )}
              >
                {m}
              </button>
            ))}
            {(["layers", "asof", "range"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPane(p)}
                className={cn(
                  "rounded border px-1.5 py-0.5 text-[10px] font-mono",
                  pane === p
                    ? "border-accent bg-accent/15 text-accent-ink"
                    : "border-line text-ink-muted hover:bg-surface",
                )}
              >
                {p}
              </button>
            ))}
          </div>

          {pane === "layers" && (
            <div className="font-mono text-[10px] text-ink-muted">
              {layersQuery.isLoading && <p>Loading layers…</p>}
              {layersQuery.error && (
                <p className="text-danger">{(layersQuery.error as Error).message}</p>
              )}
              {layers && (
                <>
                  <p>
                    aliases: {aliases.join(", ") || "(none)"}
                    {layers.combinator_present ? " · screens_hit" : ""}
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {((layers.layers as Array<{ binding_id: string; stage_name: string }>) || []).map(
                      (l) => (
                        <li key={l.binding_id}>
                          <span className="text-ink">{l.binding_id}</span> — {l.stage_name}
                        </li>
                      ),
                    )}
                  </ul>
                </>
              )}
            </div>
          )}

          {pane === "asof" && (
            <div className="font-mono text-[10px] text-ink-muted">
              {!asOf && <p>Set as-of date to run asof probe.</p>}
              {asofQuery.isLoading && <p>Querying…</p>}
              {asofQuery.error && (
                <p className="text-danger">{(asofQuery.error as Error).message}</p>
              )}
              {asofQuery.data && (
                <>
                  <p>
                    showing {Math.min(visibleRows, (asofQuery.data.rows as unknown[])?.length ?? 0)}/
                    {String(asofQuery.data.count)} · hit_rate{" "}
                    {JSON.stringify(
                      (asofQuery.data.diagnostics as { hit_rate?: Record<string, number> })
                        ?.hit_rate ?? {},
                    )}
                  </p>
                  <div
                    className="mt-1 max-h-40 overflow-auto rounded border border-line bg-surface"
                    onScroll={(e) => {
                      const rows =
                        (asofQuery.data?.rows as Array<Record<string, unknown>>) || [];
                      if (visibleRows >= rows.length) return;
                      const el = e.currentTarget;
                      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
                        setVisibleRows((n) => Math.min(n + TABLE_PAGE, rows.length));
                      }
                    }}
                  >
                    <table className="w-full text-left">
                      <thead>
                        <tr>
                          {((asofQuery.data.columns as string[]) || ["ticker"])
                            .slice(0, 8)
                            .map((col) => (
                              <th key={col} className="px-1 py-0.5 font-normal text-ink-faint">
                                {col}
                              </th>
                            ))}
                        </tr>
                      </thead>
                      <tbody>
                        {((asofQuery.data.rows as Array<Record<string, unknown>>) || [])
                          .slice(0, visibleRows)
                          .map((row, i) => (
                            <tr key={i} className="border-t border-line/60">
                              {((asofQuery.data!.columns as string[]) || ["ticker"])
                                .slice(0, 8)
                                .map((col) => (
                                  <td key={col} className="px-1 py-0.5 text-ink">
                                    {String(row[col] ?? "")}
                                  </td>
                                ))}
                            </tr>
                          ))}
                        {visibleRows <
                          ((asofQuery.data.rows as unknown[]) || []).length && (
                          <tr>
                            <td
                              colSpan={8}
                              className="px-1 py-1 text-center text-ink-faint"
                            >
                              Scroll for more…
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}

          {pane === "range" && (
            <div className="font-mono text-[10px] text-ink-muted">
              {!asOf && <p>Set as-of date to run range probe.</p>}
              {rangeQuery.isLoading && <p>Querying…</p>}
              {rangeQuery.error && (
                <p className="text-danger">{(rangeQuery.error as Error).message}</p>
              )}
              {rangeQuery.data && (
                <>
                  <p>
                    days=
                    {String(
                      (rangeQuery.data.summary as { trading_days?: number })?.trading_days ??
                        (rangeQuery.data.dates as string[] | undefined)?.length ??
                        0,
                    )}{" "}
                    · avg members=
                    {String(
                      (rangeQuery.data.summary as { avg_members_per_day?: number })
                        ?.avg_members_per_day ?? "—",
                    )}
                  </p>
                  <ProbeRangeChart
                    dates={(rangeQuery.data.dates as string[]) || []}
                    memberCounts={(rangeQuery.data.member_counts as number[]) || []}
                    measureSeries={
                      (rangeQuery.data.measure_series as Record<string, number[]>) || undefined
                    }
                  />
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
