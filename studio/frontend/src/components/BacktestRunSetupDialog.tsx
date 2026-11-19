import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBacktestSpecs, submitBacktest } from "../api/backtests";
import { fetchAsOfRange } from "../api/screens";
import type { EvaluationConfig } from "../types";
import { INITIAL_EVALUATION_CONFIG, EvaluationSettingsPanel } from "./studio/EvaluationSettingsPanel";
import { evaluationExtraEnv, stampEvaluation } from "../lib/evaluationSpec";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@sb/webapp-core/components/ui/dialog";

export function BacktestRunSetupDialog({
  open,
  onOpenChange,
  initialIrId,
  onQueued,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialIrId?: string;
  onQueued?: (irId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [irId, setIrId] = useState(initialIrId ?? "");
  const [config, setConfig] = useState<EvaluationConfig>(INITIAL_EVALUATION_CONFIG);
  const specsQuery = useQuery({
    queryKey: ["strategy-specs-library", "backtest-setup"],
    queryFn: () => fetchBacktestSpecs({ limit: 200, is_template: false }),
    enabled: open,
  });
  const datesQuery = useQuery({
    queryKey: ["as-of-range-compose"],
    queryFn: () => fetchAsOfRange(10000),
    staleTime: 5 * 60_000,
    enabled: open,
  });

  useEffect(() => {
    const datesDesc = datesQuery.data ?? [];
    if (datesDesc.length === 0) return;
    setConfig((current) => {
      if (current.start_date !== INITIAL_EVALUATION_CONFIG.start_date || current.end_date !== INITIAL_EVALUATION_CONFIG.end_date) {
        return current;
      }
      const startIndex = Math.min(datesDesc.length - 1, 251);
      return {
        ...current,
        start_date: datesDesc[startIndex] ?? datesDesc[datesDesc.length - 1]!,
        end_date: datesDesc[0]!,
      };
    });
  }, [datesQuery.data]);

  useEffect(() => {
    if (open && initialIrId) setIrId(initialIrId);
  }, [open, initialIrId]);

  const queueMutation = useMutation({
    mutationFn: () => {
      if (!irId) throw new Error("Choose a saved strategy.");
      if (!config.start_date || !config.end_date) throw new Error("Choose a date range.");
      return submitBacktest({
        ir_id: irId,
        start_date: config.start_date,
        end_date: config.end_date,
        extra_env: evaluationExtraEnv(stampEvaluation({}, config)),
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["backtest-jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["backtest-runs"] }),
      ]);
      onQueued?.(irId);
      onOpenChange(false);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader><DialogTitle>New backtest</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <label className="block space-y-1 text-xs font-medium">
            <span>Strategy</span>
            <Select value={irId} onValueChange={setIrId}>
              <SelectTrigger><SelectValue placeholder={specsQuery.isLoading ? "Loading strategies…" : "Choose a saved strategy"} /></SelectTrigger>
              <SelectContent>
                {(specsQuery.data ?? []).map((spec) => (
                  <SelectItem key={spec.ir_id} value={spec.ir_id}>{spec.title} · {spec.ir_id}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          {specsQuery.isError ? <p role="alert" className="text-xs text-danger">Could not load saved strategies: {(specsQuery.error as Error).message}</p> : null}
          {specsQuery.data?.length === 0 && !specsQuery.isLoading ? <p className="text-xs text-ink-muted">Save a strategy before starting a backtest.</p> : null}
          <EvaluationSettingsPanel config={config} onChangeConfig={setConfig} compact baselineOnly />
          {queueMutation.isError ? <p role="alert" className="text-xs text-danger">{(queueMutation.error as Error).message}</p> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="button" disabled={!irId || queueMutation.isPending || specsQuery.isError} onClick={() => queueMutation.mutate()}>
              {queueMutation.isPending ? "Queuing…" : "Queue backtest"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
