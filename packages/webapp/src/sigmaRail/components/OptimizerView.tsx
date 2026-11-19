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
import { PageHeadline } from "@sb/webapp-core/components/pageHeadline";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@sb/webapp-core/components/ui/alert";

function OptimizerQueryError({
  title,
  message,
  onRetry,
  isRetrying,
}: {
  title: string;
  message: string;
  onRetry: () => void;
  isRetrying: boolean;
}) {
  return (
    <Alert variant="destructive" className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{message}</AlertDescription>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={onRetry} disabled={isRetrying}>
        Retry
      </Button>
    </Alert>
  );
}

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
    <div className="flex min-h-0 flex-1 flex-col gap-3 pb-6">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b pb-3">
        <PageHeadline
          header="Parameter sweeps"
          subheader="Explore how strategy parameters affect backtest performance."
          className="space-y-1"
        />

        <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2 lg:flex-none">
          {!sessionsQuery.isError ? (
            <Badge variant="muted">{sessions.length} {sessions.length === 1 ? "study" : "studies"}</Badge>
          ) : null}
          <div className="flex max-w-full items-center gap-1.5 overflow-x-auto pb-0.5">
            {sessions.map((s) => {
              const isSelected = (selectedSessionId || sessions[0]?.session_id) === s.session_id;
              return (
                <Button
                  key={s.session_id}
                  type="button"
                  onClick={() => {
                    setSelectedSessionId(s.session_id);
                    setSelectedRunId(null);
                  }}
                  variant={isSelected ? "secondary" : "outline"}
                  size="sm"
                  className="h-8 shrink-0"
                >
                  {s.title || s.session_id}
                  {s.is_shared ? <Badge variant="muted" className="ml-2 px-1.5 py-0 text-[9px]">Shared</Badge> : null}
                </Button>
              );
            })}
          </div>

        <Button
          type="button"
          onClick={() => setIsModalOpen(true)}
          size="sm"
        >
          New sweep
        </Button>
        </div>
      </header>

      {/* Main Three-Zone Quant Workspace */}
      {sessionsQuery.isLoading ? (
        <Card className="p-6 text-sm text-muted-foreground shadow-none">
          Loading optimization studies…
        </Card>
      ) : sessionsQuery.isError ? (
        <OptimizerQueryError
          title="Optimization studies could not be loaded"
          message={(sessionsQuery.error as Error).message}
          onRetry={() => void sessionsQuery.refetch()}
          isRetrying={sessionsQuery.isFetching}
        />
      ) : sessions.length === 0 ? (
        <Card className="flex flex-col items-center justify-center p-8 text-center shadow-none sm:p-12">
          <p className="text-base font-semibold">No optimization studies yet</p>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            Start a sweep to compare parameter ranges, review performance surfaces, and inspect the strongest candidates.
          </p>
          <Button
            type="button"
            onClick={() => setIsModalOpen(true)}
            className="mt-4"
            size="sm"
          >
            Create sweep
          </Button>
        </Card>
      ) : heatmapQuery.isLoading ? (
        <Card className="p-6 text-sm text-muted-foreground shadow-none">
          Loading sweep results…
        </Card>
      ) : heatmapQuery.isError || heatmapData?.error ? (
        <OptimizerQueryError
          title="Sweep results could not be loaded"
          message={heatmapData?.error || (heatmapQuery.error as Error).message}
          onRetry={() => void heatmapQuery.refetch()}
          isRetrying={heatmapQuery.isFetching}
        />
      ) : heatmapData ? (
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
        <Card className="p-6 text-sm text-muted-foreground shadow-none">
          Sweep results are not available yet. Retry to load the selected study.
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => void heatmapQuery.refetch()}
            disabled={heatmapQuery.isFetching}
          >
            Retry
          </Button>
        </Card>
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
