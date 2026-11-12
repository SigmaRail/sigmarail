import { cn } from "../lib/utils";
import type { TurnoverResponse } from "../types";

export function TimeBar({
  datesDesc,
  asOf,
  onAsOfChange,
  turnover,
  loading,
}: {
  datesDesc: string[];
  asOf: string;
  onAsOfChange: (d: string) => void;
  turnover: TurnoverResponse | null;
  loading?: boolean;
}) {
  const idx = datesDesc.indexOf(asOf);
  const canNewer = idx > 0;
  const canOlder = idx >= 0 && idx < datesDesc.length - 1;

  const goNewer = () => {
    if (canNewer) onAsOfChange(datesDesc[idx - 1]!);
  };
  const goOlder = () => {
    if (canOlder) onAsOfChange(datesDesc[idx + 1]!);
  };

  const added = turnover?.added.length ?? 0;
  const removed = turnover?.removed.length ?? 0;

  return (
    <footer className="flex h-12 shrink-0 items-center gap-4 border-t border-line bg-surface-raised px-3 shadow-[0_-1px_0_rgba(26,35,50,0.06)]">
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          As-of
        </span>
        <button
          type="button"
          aria-label="Previous trading day"
          disabled={!canOlder}
          onClick={goOlder}
          className={cn(
            "rounded border border-line px-2 py-1 font-mono text-xs",
            canOlder
              ? "bg-surface-sunk text-ink hover:border-ink-muted"
              : "cursor-not-allowed text-ink-faint opacity-50",
          )}
        >
          ←
        </button>
        <div className="min-w-[7.5rem] rounded border border-line bg-white px-2 py-1 text-center font-mono text-[13px] font-medium tabular-nums">
          {asOf || "—"}
        </div>
        <button
          type="button"
          aria-label="Next trading day"
          disabled={!canNewer}
          onClick={goNewer}
          className={cn(
            "rounded border border-line px-2 py-1 font-mono text-xs",
            canNewer
              ? "bg-surface-sunk text-ink hover:border-ink-muted"
              : "cursor-not-allowed text-ink-faint opacity-50",
          )}
        >
          →
        </button>
        {loading ? (
          <span className="ml-1 text-[11px] text-ink-faint">updating…</span>
        ) : null}
      </div>

      <div className="h-5 w-px bg-line" />

      <div className="flex items-center gap-3 text-[12px]">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          Turnover
        </span>
        <span className="font-mono tabular-nums">
          <span className="font-semibold text-accent">{added}</span>
          <span className="text-ink-muted"> in</span>
          <span className="mx-1.5 text-ink-faint">/</span>
          <span className="font-semibold text-danger">{removed}</span>
          <span className="text-ink-muted"> out</span>
        </span>
        {turnover?.prior ? (
          <span className="text-[11px] text-ink-faint">
            vs {turnover.prior} · retained {turnover.retained_count}
          </span>
        ) : (
          <span className="text-[11px] text-ink-faint">no prior session</span>
        )}
      </div>

      <div className="ml-auto font-mono text-[10px] text-ink-faint">
        {datesDesc.length} sessions loaded
      </div>
    </footer>
  );
}
