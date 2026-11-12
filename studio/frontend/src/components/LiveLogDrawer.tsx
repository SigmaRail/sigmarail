import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchBacktestJobLog } from "../api/backtests";

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
    return raw.filter((l) => l.toLowerCase().includes(lower));
  }, [logQuery.data?.lines, filterText]);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="flex h-full w-full max-w-3xl flex-col border-l border-line bg-slate-950 text-slate-100 shadow-2xl">
        {/* Terminal Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/80 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <h3 className="text-[13px] font-bold text-white font-mono">
                LEAN Execution Log · {jobId.slice(0, 8)}…{jobId.slice(-4)}
              </h3>
              <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">
                {status || "running"}
              </span>
            </div>
            {irId ? (
              <p className="mt-0.5 truncate text-[11px] text-slate-400 font-mono">
                model: {irId}
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1 text-[11px] text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-accent focus:ring-accent"
              />
              <span>Auto-scroll</span>
            </label>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-700 transition-colors"
            >
              Close Log ✕
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/40 px-4 py-2 text-[11px]">
          <div className="flex flex-1 items-center gap-2">
            <span className="text-slate-400">Filter:</span>
            <input
              type="text"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Search output (e.g. Universe, Error, Order)..."
              className="flex-1 rounded border border-slate-800 bg-slate-950 px-2.5 py-1 font-mono text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none"
            />
            {filterText ? (
              <button
                type="button"
                onClick={() => setFilterText("")}
                className="text-[10px] text-slate-400 hover:text-slate-200"
              >
                Clear
              </button>
            ) : null}
          </div>
          <div className="ml-3 font-mono text-[10px] text-slate-500">
            {lines.length} lines
          </div>
        </div>

        {/* Console Body */}
        <div
          ref={logContainerRef}
          className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed select-text"
        >
          {logQuery.isLoading && lines.length === 0 ? (
            <div className="text-slate-500">Connecting to LEAN container stream…</div>
          ) : lines.length === 0 ? (
            <div className="text-slate-500">
              {filterText ? "No log lines match the filter query." : "Waiting for initial engine logs…"}
            </div>
          ) : (
            lines.map((line, idx) => {
              let colorClass = "text-slate-300";
              if (line.includes("ERROR") || line.includes("Exception") || line.includes("failed")) {
                colorClass = "text-rose-400 font-semibold";
              } else if (line.includes("Universe") || line.includes("symbols")) {
                colorClass = "text-sky-300 font-semibold";
              } else if (line.includes("Order:") || line.includes("Filled")) {
                colorClass = "text-emerald-300";
              } else if (line.includes("ClickHouseDataProvider")) {
                colorClass = "text-slate-400";
              } else if (line.includes("TRACE:: Debug:")) {
                colorClass = "text-amber-300";
              }

              return (
                <div key={idx} className={`py-0.5 hover:bg-slate-900/60 ${colorClass}`}>
                  {line}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 bg-slate-900/80 px-4 py-2 text-[10px] font-mono text-slate-500">
          <div>
            Output path: {logQuery.data?.log_path || "results/" + jobId + "/lean-backtest.log"}
          </div>
          <div>{isLive ? "● Streaming live output" : "✓ Run finished"}</div>
        </div>
      </div>
    </div>
  );
}
