import { PromotePanel } from "./PromotePanel";
import { PageHeader } from "./ui/primitives";

export function DeployView() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader title="Deploy" description="Promote backtest runs to paper and manage live deployments." />
      <PromotePanel />
    </div>
  );
}
