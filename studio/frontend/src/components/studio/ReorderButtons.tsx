import { cn } from "../../lib/utils";

/** Compact ▲/▼ controls for list reordering. */
export function ReorderButtons({
  canUp,
  canDown,
  onUp,
  onDown,
  className,
}: {
  canUp: boolean;
  canDown: boolean;
  onUp: () => void;
  onDown: () => void;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)}>
      <button
        type="button"
        disabled={!canUp}
        onClick={onUp}
        title="Move up"
        className="rounded border border-line px-1 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk disabled:opacity-30 disabled:hover:bg-transparent"
      >
        ▲
      </button>
      <button
        type="button"
        disabled={!canDown}
        onClick={onDown}
        title="Move down"
        className="rounded border border-line px-1 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk disabled:opacity-30 disabled:hover:bg-transparent"
      >
        ▼
      </button>
    </span>
  );
}
