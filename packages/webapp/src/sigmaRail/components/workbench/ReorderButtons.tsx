import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";

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
      <Button
        type="button"
        disabled={!canUp}
        onClick={onUp}
        variant="outline"
        size="icon"
        title="Move up"
        aria-label="Move up"
        className="h-8 w-8 text-ink-muted disabled:opacity-30"
      >
        ▲
      </Button>
      <Button
        type="button"
        disabled={!canDown}
        onClick={onDown}
        variant="outline"
        size="icon"
        title="Move down"
        aria-label="Move down"
        className="h-8 w-8 text-ink-muted disabled:opacity-30"
      >
        ▼
      </Button>
    </span>
  );
}
