import { useMemo } from "react";
import { DataTable, type GridColumn } from "./DataTable";
import { formatNum } from "../lib/utils";
import type { RankedRow, ScreenSource } from "../types";

function DeltaCell({ row }: { row: RankedRow }) {
  if (row.delta === "new") {
    return (
      <span className="rounded bg-accent-soft px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-accent">
        new
      </span>
    );
  }
  if (row.delta === "dropped") {
    return (
      <span className="rounded bg-danger-soft px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase text-danger">
        dropped
      </span>
    );
  }
  if (row.delta === "up" && row.deltaRank != null) {
    return (
      <span className="font-mono text-[11px] text-accent">
        ↑{row.deltaRank}
      </span>
    );
  }
  if (row.delta === "down" && row.deltaRank != null) {
    return (
      <span className="font-mono text-[11px] text-danger">
        ↓{Math.abs(row.deltaRank)}
      </span>
    );
  }
  if (row.delta === "same") {
    return <span className="font-mono text-[11px] text-ink-faint">—</span>;
  }
  return <span className="text-ink-faint">—</span>;
}

function numField(row: RankedRow, key: string): unknown {
  return row[key];
}

export function RankingsTable({
  rows,
  selectedTicker,
  onSelect,
  loading,
  source = "preset",
}: {
  rows: RankedRow[];
  selectedTicker: string | null;
  onSelect: (row: RankedRow) => void;
  loading?: boolean;
  source?: ScreenSource;
}) {
  const emptyLabel =
    source === "ir"
      ? "No names for this as-of / screen"
      : "No names for this as-of / preset";

  const columns = useMemo<GridColumn<RankedRow>[]>(
    () => [
      {
        id: "rank",
        label: "Rank",
        align: "left",
        always: true,
        sortable: true,
        sticky: "left",
        widthClass: "min-w-[36px]",
        accessor: (r) => r.delta === "dropped" ? null : r.rank,
        cell: (r) =>
          r.delta === "dropped" ? (
            <span className="text-ink-faint">—</span>
          ) : (
            <span className="font-mono">{r.rank}</span>
          ),
      },
      {
        id: "ticker",
        label: "Ticker",
        align: "left",
        always: true,
        sortable: true,
        sticky: "left",
        stickyOffset: "left-[36px]",
        widthClass: "min-w-[70px]",
        accessor: (r) => r.ticker,
        cell: (r) => (
          <span className="font-sans font-bold tracking-wide text-ink">
            {r.ticker}
          </span>
        ),
      },
      {
        id: "rs",
        label: "RS",
        align: "right",
        sortable: true,
        format: "int",
        accessor: (r) => r.rs_rating ?? null,
      },
      {
        id: "ta",
        label: "TA",
        align: "right",
        sortable: true,
        format: "int",
        accessor: (r) => numField(r, "technical_rating"),
      },
      {
        id: "setup",
        label: "Setup",
        align: "right",
        sortable: true,
        format: "int",
        accessor: (r) => numField(r, "setup_quality_rating"),
      },
      {
        id: "hgm",
        label: "HGM",
        align: "right",
        sortable: true,
        format: "int",
        accessor: (r) => numField(r, "high_growth_momentum_rating"),
      },
      {
        id: "vol50",
        label: "Vol50",
        align: "right",
        sortable: true,
        accessor: (r) => numField(r, "avg_vol_50d"),
        cell: (_r, v) => <span className="font-mono">{formatVol(v)}</span>,
      },
      {
        id: "overall",
        label: "Overall",
        align: "right",
        sortable: true,
        format: "num",
        accessor: (r) => r.overall_score ?? null,
        cell: (_r, v) => formatNum(v, 1),
      },
      {
        id: "classification",
        label: "Class",
        align: "left",
        sortable: false,
        accessor: (r) => r.classification ?? null,
        cell: (_r, v) => (
          <span className="font-sans text-ink-muted truncate">
            {v ? String(v) : "—"}
          </span>
        ),
      },
      {
        id: "close",
        label: "Close",
        align: "right",
        sortable: true,
        format: "price",
        accessor: (r) => r.close ?? null,
        cell: (_r, v) => formatNum(v, 2),
      },
      {
        id: "delta",
        label: "Δ vs prior",
        align: "left",
        sortable: false,
        always: true,
        accessor: (r) => r.delta,
        cell: (r) => <DeltaCell row={r} />,
      },
    ],
    [],
  );

  return (
    <DataTable<RankedRow>
      rows={rows}
      columns={columns}
      viewId="screener.rankings"
      getRowId={(r) => `${r.ticker}-${r.rank}-${r.delta}`}
      onRowClick={onSelect}
      loading={loading}
      emptyLabel={emptyLabel}
      rowClassName={(r: RankedRow) =>
        r.delta === "dropped" ? "opacity-55" : undefined
      }
      rowHighlight={(r: RankedRow) => r.ticker === selectedTicker}
      density="compact"
      height="fill"
    />
  );
}

/** Compact volume for AvgVol50 / similar (e.g. 689920 → 690k). */
function formatVol(value: unknown): string {
  let n: number | null = null;
  if (typeof value === "number" && Number.isFinite(value)) n = value;
  else if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) n = parsed;
  }
  if (n == null) return "—";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(Math.round(n));
}
