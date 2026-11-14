import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { cancelBacktestJob } from "../api/backtests";
import type { BacktestJobListItem } from "../types";

function formatSeconds(sec: number | null | undefined): string {
  if (sec == null || sec <= 0) return "0s";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

export function ActiveBacktestBanner({
  jobs,
  onViewLog,
}: {
  jobs: BacktestJobListItem[];
  onViewLog: (jobId: string, irId?: string | null, status?: string) => void;
}) {
  const queryClient = useQueryClient();
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const activeJobs = jobs.filter(
    (j) => j.status === "running" || j.status === "pending",
  );

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => cancelBacktestJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["backtest-jobs"] });
      setCancellingId(null);
    },
    onError: () => {
      setCancellingId(null);
    },
  });

  if (activeJobs.length === 0) return null;

  return (
    <div className="space-y-2 border-b border-line bg-surface-sunk/70 p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent" />
          </span>
          <h3 className="text-[12px] font-bold text-ink">
            Active Backtest Execution ({activeJobs.length} in progress)
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
        {activeJobs.map((job) => {
          const isRunning = job.status === "running";
          const pct = Math.min(100, Math.max(0, Math.round((job.progress_pct ?? 0) * 100)));

          return (
            <div
              key={job.job_id}
              className="flex flex-col justify-between rounded border border-line bg-surface p-3 shadow-sm"
            >
              <div>
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] font-bold text-ink truncate">
                        {job.job_id.slice(0, 8)}…{job.job_id.slice(-4)}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[9.5px] font-semibold uppercase font-mono ${
                          isRunning
                            ? "bg-accent/20 text-accent-ink"
                            : "bg-warn/20 text-warn"
                        }`}
                      >
                        {job.status}
                      </span>
                    </div>
                    {job.ir_id ? (
                      <p
                        className="mt-0.5 truncate font-mono text-[10px] text-ink-muted"
                        title={job.ir_id}
                      >
                        {job.ir_id}
                      </p>
                    ) : null}
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => onViewLog(job.job_id, job.ir_id, job.status)}
                      className="rounded border border-line bg-surface-sunk px-2 py-1 text-[10.5px] font-medium text-ink hover:bg-surface-raised transition-colors"
                      title="View live container log"
                    >
                      📜 Live Log
                    </button>
                    <button
                      type="button"
                      disabled={cancellingId === job.job_id}
                      onClick={() => {
                        if (window.confirm(`Are you sure you want to abort backtest ${job.job_id.slice(0, 8)}?`)) {
                          setCancellingId(job.job_id);
                          cancelMutation.mutate(job.job_id);
                        }
                      }}
                      className="rounded border border-danger/40 bg-danger-soft/60 px-2 py-1 text-[10.5px] font-medium text-danger hover:bg-danger-soft transition-colors disabled:opacity-50"
                      title="Abort this backtest"
                    >
                      {cancellingId === job.job_id ? "Aborting…" : "⏹ Abort"}
                    </button>
                  </div>
                </div>

                {/* Progress Bar & Details */}
                {isRunning ? (
                  <div className="mt-3 space-y-1.5">
                    <div className="flex items-baseline justify-between text-[10.5px]">
                      <span className="font-mono text-ink">
                        {pct > 0 ? `${pct}% complete` : "Starting engine…"}
                      </span>
                      {job.current_sim_date ? (
                        <span className="font-mono text-[10px] text-ink-muted">
                          Simulating:{" "}
                          <span className="font-semibold text-accent-ink">
                            {job.current_sim_date}
                          </span>{" "}
                          / {job.end_date ?? ""}
                        </span>
                      ) : (
                        <span className="font-mono text-[10px] text-ink-faint">
                          Period: {job.start_date} → {job.end_date}
                        </span>
                      )}
                    </div>

                    {/* Progress track */}
                    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunk border border-line/60">
                      <div
                        className="h-full bg-accent transition-all duration-500 ease-out"
                        style={{ width: `${Math.max(pct, isRunning ? 5 : 0)}%` }}
                      />
                    </div>

                    {/* Timers & Log snippet */}
                    <div className="flex items-center justify-between text-[10px] text-ink-faint">
                      <span>
                        Elapsed:{" "}
                        <span className="font-mono text-ink-muted">
                          {formatSeconds(job.elapsed_seconds)}
                        </span>
                      </span>
                      {job.estimated_remaining_seconds != null && job.estimated_remaining_seconds > 0 ? (
                        <span>
                          Est. Remaining:{" "}
                          <span className="font-mono text-accent-ink font-semibold">
                            ~{formatSeconds(job.estimated_remaining_seconds)}
                          </span>
                        </span>
                      ) : null}
                    </div>

                    {job.last_log_line ? (
                      <p className="truncate font-mono text-[9.5px] text-ink-faint bg-surface-sunk/60 rounded px-1.5 py-0.5 mt-1 border border-line/40">
                        {job.last_log_line}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <div className="mt-2.5 rounded bg-surface-sunk px-2.5 py-2 text-[10.5px] text-ink-muted">
                    Waiting in ClickHouse queue for an available worker slot…
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
