import { useQuery } from "@tanstack/react-query";
import { fetchLiveDeployments, fetchLocalLiveRuntime } from "../api/live";
import type { StudioMode } from "../types";

function truncateId(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

export function MonitorView({
  onModeChange,
}: {
  onModeChange: (mode: StudioMode) => void;
}) {
  const deploymentsQuery = useQuery({
    queryKey: ["live-deployments"],
    queryFn: () => fetchLiveDeployments(30),
  });
  const runtimeQuery = useQuery({
    queryKey: ["local-live-runtime"],
    queryFn: fetchLocalLiveRuntime,
    refetchInterval: (query) =>
      (query.state.data?.active_count ?? 0) > 0 || query.state.data?.status === "external_running" ? 10_000 : false,
  });

  const deployments = deploymentsQuery.data ?? [];
  const localDeployments = runtimeQuery.data?.deployments ?? [];
  const localRuntimeDeployment = runtimeQuery.data?.deployment;
  const monitoredDeployments = localDeployments.length > 0
    ? localDeployments
    : localRuntimeDeployment?.status === "external_running" ? [localRuntimeDeployment] : [];

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface">
      <div className="shrink-0 border-b border-line bg-surface-raised px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Monitor</h2>
        <p className="mt-0.5 text-[11px] text-ink-muted">
          LEAN performance by algorithm. Snapshot time is shown for every deployment.
        </p>
        <button
          type="button"
          onClick={() => onModeChange("deploy")}
          className="mt-2 rounded border border-line bg-surface-sunk px-2.5 py-1 text-[12px] font-medium text-ink hover:border-accent hover:bg-accent-soft"
        >
          Go to Deploy →
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <section className="mb-4 rounded border border-line bg-surface-raised">
          <div className="border-b border-line px-3 py-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
              Algorithm performance · local LEAN
            </h3>
          </div>
          {runtimeQuery.isLoading ? (
            <p className="px-3 py-6 text-[12px] text-ink-muted">Checking local deployments…</p>
          ) : runtimeQuery.isError ? (
            <p className="px-3 py-6 text-[12px] text-danger">
              {(runtimeQuery.error as Error).message}
            </p>
          ) : monitoredDeployments.length === 0 ? (
            <p className="px-3 py-6 text-[12px] text-ink-muted">No local LEAN deployment is being monitored.</p>
          ) : (
            <ul>
              {monitoredDeployments.map((deployment, index) => {
                const metrics = deployment.metrics;
                const runtimeStats = metrics?.runtime_statistics ?? {};
                const summaryStats = metrics?.summary_statistics ?? {};
                const headlineKeys = ["Equity", "Return", "Net Profit", "Unrealized", "Fees", "Drawdown"];
                const headline = headlineKeys
                  .map((key) => [key, runtimeStats[key] ?? summaryStats[key]] as const)
                  .filter((entry): entry is readonly [string, string] => Boolean(entry[1]));
                return (
                  <li key={deployment.deployment_id ?? `${deployment.project}-${index}`} className="border-b border-line px-3 py-3 last:border-b-0">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="text-[12px] font-medium text-ink">
                          {deployment.ir_id ?? "LEAN algorithm"}
                        </div>
                        <div className="mt-0.5 font-mono text-[10px] text-ink-faint">
                          {metrics?.algorithm_id ?? deployment.account_name ?? "Algorithm ID pending"}
                          {deployment.account_name ? ` · ${deployment.account_name}` : ""}
                        </div>
                      </div>
                      <span className="rounded bg-surface-sunk px-1.5 py-0.5 text-[10px] text-ink-muted">
                        {deployment.container_status ?? deployment.status ?? "unknown"}
                      </span>
                    </div>

                    {metrics ? (
                      <>
                        <div className="mt-2 text-[10px] text-ink-faint">
                          LEAN snapshot: {new Date(metrics.as_of).toLocaleString()}
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                          {headline.map(([label, value]) => (
                            <div key={label} className="rounded border border-line bg-surface px-2 py-1.5">
                              <div className="text-[9px] uppercase tracking-wide text-ink-faint">{label}</div>
                              <div className="mt-0.5 truncate font-mono text-[11px] text-ink" title={value}>{value}</div>
                            </div>
                          ))}
                        </div>

                        {metrics.holdings.length > 0 ? (
                          <div className="mt-3 overflow-x-auto">
                            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Holdings</div>
                            <table className="w-full text-left text-[10px]">
                              <thead className="text-ink-faint"><tr><th className="py-1 pr-3">Symbol</th><th className="py-1 pr-3">Qty</th><th className="py-1 pr-3">Market value</th><th className="py-1">Unrealized P&amp;L</th></tr></thead>
                              <tbody>{metrics.holdings.slice(0, 8).map((holding) => (
                                <tr key={holding.symbol} className="border-t border-line text-ink">
                                  <td className="py-1 pr-3 font-mono">{holding.symbol}</td><td className="py-1 pr-3">{holding.quantity ?? "—"}</td><td className="py-1 pr-3">{holding.market_value ?? "—"}</td><td className="py-1">{holding.unrealized_pnl ?? "—"}</td>
                                </tr>
                              ))}</tbody>
                            </table>
                          </div>
                        ) : null}

                        {metrics.recent_orders.length > 0 ? (
                          <div className="mt-3 text-[10px] text-ink-muted">
                            Recent orders: {metrics.recent_orders.slice(0, 5).map((order) => `${order.symbol ?? "?"} ${order.status ?? "unknown"}`).join(" · ")}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <p className="mt-2 text-[11px] text-ink-muted">LEAN has not saved a performance snapshot for this deployment yet.</p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="rounded border border-line bg-surface-raised">
          <div className="border-b border-line px-3 py-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
              Deployment registry
            </h3>
          </div>
          {deploymentsQuery.isLoading ? (
            <p className="px-3 py-6 text-[12px] text-ink-muted">Loading…</p>
          ) : deployments.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <p className="text-[12px] text-ink-muted">
                No paper deployments registered yet.
              </p>
              <button
                type="button"
                onClick={() => onModeChange("deploy")}
                className="mt-3 rounded bg-ink px-3 py-1.5 text-[12px] font-medium text-white"
              >
                Register in Deploy
              </button>
            </div>
          ) : (
            <ul>
              {deployments.map((d) => (
                <li
                  key={d.deployment_id}
                  className="border-b border-line px-3 py-2.5 last:border-b-0"
                >
                  <div className="font-mono text-[11px] font-medium text-ink">
                    {truncateId(d.deployment_id)}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-ink-faint">
                    {d.ir_id ?? "—"}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-[10px]">
                    <span className="rounded bg-surface-sunk px-1.5 py-0.5 text-ink-muted">
                      {d.status ?? "unknown"}
                    </span>
                    {d.lean_environment ? (
                      <span className="text-ink-faint">{d.lean_environment}</span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
