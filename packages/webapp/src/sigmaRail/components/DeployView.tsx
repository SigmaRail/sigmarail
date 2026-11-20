import { PromotePanel } from "./PromotePanel";

export function DeployView() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-line bg-surface-raised px-4 py-2">
        <h2 className="text-sm font-semibold text-ink">Deploy</h2>
        <p className="mt-0.5 text-[11px] text-ink-muted">
          Promote backtest runs to paper and manage live deployments.
        </p>
      </div>
      <PromotePanel />
    </div>
  );
}
