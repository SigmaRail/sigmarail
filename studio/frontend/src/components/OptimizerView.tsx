import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  fetchBacktestSpecs,
  fetchOptimizerSessionHeatmap,
  fetchOptimizerSessions,
  launchOptimizerSession,
} from "../api/backtests";
import { OptimizerScatterChart } from "./OptimizerScatterChart";
import { OptimizerRunInspector } from "./OptimizerRunInspector";
import { OptimizerRunsTable } from "./OptimizerRunsTable";
import { OptimizerSweepModal } from "./OptimizerSweepModal";
import { studioAgentBridge } from "../lib/studioAgentBridge";
import type {
  BacktestSpecSummary,
  LaunchOptimizerRequest,
  OptimizerRunPoint,
  OptimizerSessionSummary,
} from "../types";

export function OptimizerView({
  onJumpToRun,
  onPromoteRun,
  onCompareRuns,
  onEditInComposer,
}: {
  onJumpToRun?: (runId: string) => void;
  onPromoteRun?: (runId: string) => void;
  onCompareRuns?: (runIds: string[]) => void;
  onEditInComposer?: (irId: string, runPoint: OptimizerRunPoint) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Specs Query for modal
  const specsQuery = useQuery({
    queryKey: ["backtest-specs"],
    queryFn: () => fetchBacktestSpecs(50),
  });
  const specs: BacktestSpecSummary[] = specsQuery.data ?? [];

  // Sessions Query
  const sessionsQuery = useQuery({
    queryKey: ["optimizer-sessions"],
    queryFn: () => fetchOptimizerSessions(20),
    refetchInterval: 5000,
  });
  const sessions: OptimizerSessionSummary[] = sessionsQuery.data?.sessions ?? [];

  // Active Session Heatmap / Surface Query
  const activeSessionId = selectedSessionId || (sessions[0]?.session_id ?? null);
  const heatmapQuery = useQuery({
    queryKey: ["optimizer-session-heatmap", activeSessionId],
    queryFn: () => (activeSessionId ? fetchOptimizerSessionHeatmap(activeSessionId) : null),
    enabled: Boolean(activeSessionId),
    refetchInterval: (query) => {
      const isDone = query.state.data?.is_done;
      return isDone ? false : 3000;
    },
  });

  const heatmapData = heatmapQuery.data;

  // --- WebMCP action bindings (Component 3: agent control of the workbench) ---
  useEffect(() => {
    const unregSession = studioAgentBridge.registerAction(
      "optimizerSelectSession",
      ({ session_id }: { session_id: string }) => {
        setSelectedSessionId(session_id);
        setSelectedRunId(null);
        return { selected_session_id: session_id };
      }
    );
    const unregPoint = studioAgentBridge.registerAction(
      "optimizerSelectPoint",
      ({ run_id }: { run_id: string }) => {
        setSelectedRunId(run_id);
        return { selected_run_id: run_id };
      }
    );
    const unregLaunch = studioAgentBridge.registerAction(
      "optimizerLaunchSweep",
      async (req: {
        base_ir_id: string;
        param_x_name: string;
        param_x_values: number[];
        param_y_name?: string;
        param_y_values?: number[];
        strategy_type?: string;
      }) => {
        const res = await launchOptimizerSession(req as LaunchOptimizerRequest);
        await queryClient.invalidateQueries({ queryKey: ["optimizer-sessions"] });
        setSelectedSessionId(res.session_id);
        setIsModalOpen(false);
        return res;
      }
    );
    return () => {
      unregSession();
      unregPoint();
      unregLaunch();
    };
  }, [queryClient]);

  // Selected Run Point calculation
  const selectedPoint: OptimizerRunPoint | null = useMemo(() => {
    if (!heatmapData) return null;
    if (selectedRunId) {
      const found = heatmapData.all_points.find((p) => p.run_id === selectedRunId);
      if (found) return found;
    }
    return heatmapData.best_run ?? heatmapData.all_points[0] ?? null;
  }, [heatmapData, selectedRunId]);

  useEffect(() => {
    studioAgentBridge.updateState({
      activeOptimizerSessionId: activeSessionId,
      selectedOptimizerPoint: selectedPoint,
    });
  }, [activeSessionId, selectedPoint]);

  // Launch Mutation
  const launchMutation = useMutation({
    mutationFn: (req: LaunchOptimizerRequest) => launchOptimizerSession(req),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["optimizer-sessions"] });
      setSelectedSessionId(data.session_id);
      setIsModalOpen(false);
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-3.5 pb-6">
      {/* Top Header & Session Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3.5 shadow-sm">
        <div className="flex items-center gap-3">
          <div>
            <span className="text-sm font-bold text-ink">Quant Optimization Workbench</span>
            <span className="ml-2 font-mono text-xs text-ink-muted">
              {sessions.length} studies
            </span>
          </div>

          {/* Session Selector Pills */}
          <div className="flex max-w-xl items-center gap-1.5 overflow-x-auto pb-0.5">
            {sessions.map((s) => {
              const isSelected = (selectedSessionId || sessions[0]?.session_id) === s.session_id;
              return (
                <button
                  key={s.session_id}
                  type="button"
                  onClick={() => {
                    setSelectedSessionId(s.session_id);
                    setSelectedRunId(null);
                  }}
                  className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                    isSelected
                      ? "bg-accent text-accent-ink shadow-sm"
                      : "bg-surface-raised text-ink-muted hover:text-ink border border-line"
                  }`}
                >
                  {s.title || s.session_id}
                  <span className="ml-1.5 opacity-75 font-mono text-[10px]">
                    ({s.strategy_type || "euler"})
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Launch New Sweep Button */}
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-xs font-bold text-accent-ink shadow-sm hover:opacity-90 transition-opacity"
        >
          <span>+</span> Launch New Sweep
        </button>
      </div>

      {/* Main Three-Zone Quant Workspace */}
      {heatmapData && !heatmapData.error ? (
        <div className="flex flex-col space-y-3.5">
          {/* Top Row: Zone A (Scatter / Sensitivity / Pareto) & Zone B (Always-mounted Inspector) */}
          <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-12 min-h-[480px]">
            {/* Zone A: Response Surface */}
            <div className="xl:col-span-7 h-full min-h-[380px]">
              <OptimizerScatterChart
                heatmap={heatmapData.heatmap}
                allPoints={heatmapData.all_points}
                paretoFrontier={heatmapData.pareto_frontier}
                selectedRunId={selectedPoint?.run_id}
                onSelectRunId={(runId) => setSelectedRunId(runId)}
                strategyType={heatmapData.session.strategy_type || "euler"}
              />
            </div>

            {/* Zone B: Run Inspector */}
            <div className="xl:col-span-5 h-full min-h-[380px]">
              <OptimizerRunInspector
                runPoint={selectedPoint}
                onOpenInRunsTab={(runId) => onJumpToRun?.(runId)}
                onPromoteRun={onPromoteRun}
                onEditInComposer={onEditInComposer}
                oosDays={heatmapData.session.oos_days}
              />
            </div>
          </div>

          {/* Bottom Row: Zone C (Leaderboard & Multi-Run Compare Selection Table) */}
          <div className="w-full">
            <OptimizerRunsTable
              points={heatmapData.all_points}
              selectedRunId={selectedPoint?.run_id}
              onSelectRunId={(runId) => setSelectedRunId(runId)}
              onCompareRuns={onCompareRuns}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-xl border border-line bg-surface p-12 text-center text-ink-muted">
          <p className="text-base font-bold text-ink">No Active Optimization Study</p>
          <p className="mt-1.5 max-w-md text-xs text-ink-faint">
            Launch a LEAN Native EulerSearch or GridSearch hyperparameter sweep to generate interactive parameter response surfaces, detect plateau vs needle stability, and inspect out-of-sample forward tests.
          </p>
          <button
            type="button"
            onClick={() => setIsModalOpen(true)}
            className="mt-4 rounded-lg bg-accent px-4 py-2 text-xs font-bold text-accent-ink hover:opacity-90 transition-opacity"
          >
            🚀 Launch First Sweep
          </button>
        </div>
      )}

      {/* Sweep Launch Modal */}
      <OptimizerSweepModal
        specs={specs}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onLaunch={(req) => launchMutation.mutate(req)}
        isLaunching={launchMutation.isPending}
      />
    </div>
  );
}
