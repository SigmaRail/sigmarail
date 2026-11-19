import { Button } from "@sb/webapp-core/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import { ExternalChartEmbed } from "../ExternalChartEmbed";
import type { RankedRow } from "../../types";

interface InlineChartDialogProps {
  row: RankedRow | null;
  onClose: () => void;
}

export function InlineChartDialog({ row, onClose }: InlineChartDialogProps) {
  return (
    <Dialog open={Boolean(row)} onOpenChange={(open) => !open && onClose()}>
      {row ? (
        <DialogContent
          size="full"
          className="grid h-[min(80dvh,640px)] max-h-[calc(100dvh-1rem)] w-[min(900px,calc(100vw-1rem))] max-w-none grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:rounded-xl"
        >
          <DialogHeader className="flex-row items-center justify-between gap-3 border-b border-border bg-card px-4 py-3 pr-14">
            <div className="min-w-0">
              <DialogTitle className="text-base">{row.ticker}</DialogTitle>
              <DialogDescription className="sr-only">
                Price chart and screening metrics for {row.ticker}.
              </DialogDescription>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                {row.close != null ? (
                  <span className="rounded bg-muted px-2 py-0.5 font-mono font-semibold">
                    ${Number(row.close).toFixed(2)}
                  </span>
                ) : null}
                {row.rs_rating != null ? (
                  <span className="rounded bg-secondary px-2 py-0.5 font-mono font-semibold text-secondary-foreground">
                    RS {Math.round(Number(row.rs_rating))}
                  </span>
                ) : null}
                {row.technical_rating != null ? (
                  <span className="rounded bg-accent/15 px-2 py-0.5 font-mono font-semibold text-accent-foreground">
                    TA {Math.round(Number(row.technical_rating))}
                  </span>
                ) : null}
                {row.sector != null ? (
                  <span className="text-muted-foreground">{String(row.sector)}</span>
                ) : null}
              </div>
            </div>
            <Button asChild variant="outline" size="sm" className="shrink-0">
              <a
                href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(row.ticker)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open chart ↗
              </a>
            </Button>
          </DialogHeader>
          <div className="min-h-0 bg-[#131722]">
            <ExternalChartEmbed
              symbol={row.ticker}
              exchange={typeof row.exchange === "string" ? row.exchange : null}
              className="h-full w-full"
            />
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}
