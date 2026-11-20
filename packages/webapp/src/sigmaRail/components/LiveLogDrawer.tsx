import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchBacktestJobLog } from "../api/backtests";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";

export function LiveLogDrawer({
  jobId,
  irId,
  status,
  onClose,
}: {
  jobId: string;
  irId?: string | null;
  status?: string;
  onClose: () => void;
}) {
  const [filterText, setFilterText] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const isLive = status === "running" || status === "pending";

  const logQuery = useQuery({
    queryKey: ["backtest-job-log", jobId],
    queryFn: () => fetchBacktestJobLog(jobId, 600),
    refetchInterval: isLive ? 1500 : false,
  });

  const lines = useMemo(() => {
    const raw = logQuery.data?.lines ?? [];
    if (!filterText.trim()) return raw;
    const lower = filterText.toLowerCase();
    return raw.filter((line) => line.toLowerCase().includes(lower));
  }, [logQuery.data?.lines, filterText]);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        size="xl"
        className="flex h-[calc(100dvh-1rem)] max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-5xl flex-col gap-0 overflow-hidden rounded-xl p-0 sm:h-[88dvh] sm:max-h-[88dvh]"
      >
        <DialogHeader className="flex flex-col gap-2 border-b px-4 py-3 pr-12 sm:flex-row sm:items-start sm:justify-between sm:px-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                aria-hidden="true"
                className={isLive ? "h-2.5 w-2.5 rounded-full bg-emerald-500" : "h-2.5 w-2.5 rounded-full bg-muted-foreground"}
              />
              <DialogTitle className="text-sm font-semibold">
                Execution log · {jobId.slice(0, 8)}…{jobId.slice(-4)}
              </DialogTitle>
              <Badge variant={isLive ? "success" : "muted"} className="font-mono text-[10px]">
                {status || "running"}
              </Badge>
            </div>
            {irId ? (
              <DialogDescription className="mt-1 truncate font-mono text-xs">
                Strategy: {irId}
              </DialogDescription>
            ) : null}
          </div>
          <Checkbox
            checked={autoScroll}
            onCheckedChange={(checked) => setAutoScroll(checked === true)}
            label="Auto-scroll"
            className="shrink-0"
          />
        </DialogHeader>

        <div className="flex flex-col gap-2 border-b bg-muted/30 px-4 py-3 sm:flex-row sm:items-center">
          <Input
            type="search"
            value={filterText}
            onChange={(event) => setFilterText(event.target.value)}
            aria-label="Filter log output"
            placeholder="Filter output by text…"
            className="h-9 min-w-0 flex-1 font-mono text-xs"
          />
          {filterText ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setFilterText("")}>
              Clear filter
            </Button>
          ) : null}
          <Badge variant="muted" className="shrink-0 self-start font-mono text-[10px] sm:self-auto">
            {lines.length} lines
          </Badge>
        </div>

        <div
          ref={logContainerRef}
          aria-live={isLive ? "polite" : undefined}
          className="min-h-0 flex-1 overflow-y-auto bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-slate-200 select-text sm:p-4"
        >
          {logQuery.isLoading && lines.length === 0 ? (
            <div className="text-slate-400">Connecting to execution output…</div>
          ) : lines.length === 0 ? (
            <div className="text-slate-400">
              {filterText ? "No log lines match this filter." : "Waiting for initial engine logs…"}
            </div>
          ) : (
            lines.map((line, index) => {
              let colorClass = "text-slate-200";
              if (line.includes("ERROR") || line.includes("Exception") || line.includes("failed")) {
                colorClass = "font-semibold text-rose-300";
              } else if (line.includes("Universe") || line.includes("symbols")) {
                colorClass = "font-semibold text-sky-300";
              } else if (line.includes("Order:") || line.includes("Filled")) {
                colorClass = "text-emerald-300";
              } else if (line.includes("TRACE:: Debug:")) {
                colorClass = "text-amber-300";
              }

              return (
                <div key={index} className={`break-words py-0.5 ${colorClass}`}>
                  {line}
                </div>
              );
            })
          )}
        </div>

        <div className="flex flex-col gap-1 border-t px-4 py-2 text-[10px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <span className="min-w-0 break-all font-mono">
            Output: {logQuery.data?.log_path || `results/${jobId}/lean-backtest.log`}
          </span>
          <span className="shrink-0">{isLive ? "Streaming live output" : "Run finished"}</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
