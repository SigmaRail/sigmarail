import { useQuery } from '@tanstack/react-query';
import { fetchLiveDeployments, fetchLocalLiveRuntime } from '../api/live';
import type { StudioMode } from '../types';
import { PageHeadline } from '@sb/webapp-core/components/pageHeadline';
import { Button } from '@sb/webapp-core/components/ui/button';
import { Card } from '@sb/webapp-core/components/ui/card';
import { Badge } from '@sb/webapp-core/components/ui/badge';
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@sb/webapp-core/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@sb/webapp-core/components/ui/table';

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
    queryKey: ['live-deployments'],
    queryFn: () => fetchLiveDeployments(30),
  });
  const runtimeQuery = useQuery({
    queryKey: ['local-live-runtime'],
    queryFn: fetchLocalLiveRuntime,
    refetchInterval: (query) =>
      (query.state.data?.active_count ?? 0) > 0 ||
      query.state.data?.status === 'external_running'
        ? 10_000
        : false,
  });

  const deployments = deploymentsQuery.data ?? [];
  const localDeployments = runtimeQuery.data?.deployments ?? [];
  const localRuntimeDeployment = runtimeQuery.data?.deployment;
  const monitoredDeployments =
    localDeployments.length > 0
      ? localDeployments
      : localRuntimeDeployment?.status === 'external_running'
        ? [localRuntimeDeployment]
        : [];

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="flex shrink-0 flex-wrap items-end justify-between gap-3 border-b bg-background px-3 py-3 sm:px-4">
        <PageHeadline
          header="Monitor"
          subheader="Review live runtime health, portfolio metrics, and recent deployments."
          className="space-y-1"
        />
        <Button
          type="button"
          onClick={() => onModeChange('deploy')}
          variant="outline"
          size="sm"
        >
          Deploy settings
        </Button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 sm:p-4">
        <Card className="overflow-hidden p-0 shadow-none">
          <div className="border-b px-3 py-2.5 sm:px-4">
            <h3 className="text-sm font-semibold">Runtime performance</h3>
          </div>
          {runtimeQuery.isLoading ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">
              Checking local deployments…
            </p>
          ) : runtimeQuery.isError ? (
            <div className="p-3 sm:p-4">
              <Alert variant="destructive">
                <AlertTitle>Runtime status is unavailable</AlertTitle>
                <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
                  <span>{(runtimeQuery.error as Error).message}</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void runtimeQuery.refetch()}
                    disabled={runtimeQuery.isFetching}
                  >
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            </div>
          ) : monitoredDeployments.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No runtime is active. Start one from Deploy to see live
              performance here.
            </div>
          ) : (
            <ul>
              {monitoredDeployments.map((deployment, index) => {
                const metrics = deployment.metrics;
                const runtimeStats = metrics?.runtime_statistics ?? {};
                const summaryStats = metrics?.summary_statistics ?? {};
                const headlineKeys = [
                  'Equity',
                  'Return',
                  'Net Profit',
                  'Unrealized',
                  'Fees',
                  'Drawdown',
                ];
                const headline = headlineKeys
                  .map(
                    (key) =>
                      [key, runtimeStats[key] ?? summaryStats[key]] as const,
                  )
                  .filter((entry): entry is readonly [string, string] =>
                    Boolean(entry[1]),
                  );
                return (
                  <li
                    key={
                      deployment.deployment_id ??
                      `${deployment.project}-${index}`
                    }
                    className="border-b px-3 py-3 last:border-b-0 sm:px-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium">
                          {deployment.ir_id ?? 'LEAN algorithm'}
                        </div>
                        <div className="mt-0.5 break-all font-mono text-xs text-muted-foreground">
                          {metrics?.algorithm_id ??
                            deployment.account_name ??
                            'Algorithm ID pending'}
                          {deployment.account_name
                            ? ` · ${deployment.account_name}`
                            : ''}
                        </div>
                      </div>
                      <Badge variant="muted" className="shrink-0">
                        {deployment.container_status ??
                          deployment.status ??
                          'unknown'}
                      </Badge>
                    </div>

                    {metrics ? (
                      <>
                        <div className="mt-2 text-xs text-muted-foreground">
                          LEAN snapshot:{' '}
                          {new Date(metrics.as_of).toLocaleString()}
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                          {headline.map(([label, value]) => (
                            <div
                              key={label}
                              className="rounded-md border bg-card px-2.5 py-2"
                            >
                              <div className="text-xs text-muted-foreground">
                                {label}
                              </div>
                              <div
                                className="mt-1 truncate font-mono text-sm font-medium"
                                title={value}
                              >
                                {value}
                              </div>
                            </div>
                          ))}
                        </div>

                        {metrics.holdings.length > 0 ? (
                          <div className="mt-3 overflow-x-auto">
                            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                              Holdings
                            </div>
                            <ul
                              data-testid="monitor-holdings-mobile"
                              className="grid gap-2 sm:hidden"
                            >
                              {metrics.holdings.slice(0, 8).map((holding) => (
                                <li
                                  key={holding.symbol}
                                  className="rounded-md border bg-card px-3 py-2.5"
                                >
                                  <div className="flex items-center justify-between gap-3">
                                    <span className="font-mono text-sm font-semibold">
                                      {holding.symbol}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                      Qty {holding.quantity ?? '—'}
                                    </span>
                                  </div>
                                  <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                                    <div>
                                      <dt className="text-muted-foreground">
                                        Market value
                                      </dt>
                                      <dd className="mt-0.5 font-mono tabular-nums">
                                        {holding.market_value ?? '—'}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt className="text-muted-foreground">
                                        Unrealized P&amp;L
                                      </dt>
                                      <dd className="mt-0.5 font-mono tabular-nums">
                                        {holding.unrealized_pnl ?? '—'}
                                      </dd>
                                    </div>
                                  </dl>
                                </li>
                              ))}
                            </ul>
                            <div
                              data-testid="monitor-holdings-table"
                              className="hidden sm:block"
                            >
                              <Table containerClassName="rounded-md border">
                                <TableHeader>
                                  <TableRow>
                                    <TableHead className="h-9 px-3 text-xs">
                                      Symbol
                                    </TableHead>
                                    <TableHead className="h-9 px-3 text-xs">
                                      Qty
                                    </TableHead>
                                    <TableHead className="h-9 px-3 text-xs">
                                      Market value
                                    </TableHead>
                                    <TableHead className="h-9 px-3 text-xs">
                                      Unrealized P&amp;L
                                    </TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {metrics.holdings
                                    .slice(0, 8)
                                    .map((holding) => (
                                      <TableRow key={holding.symbol}>
                                        <TableCell className="px-3 py-2 font-mono text-xs">
                                          {holding.symbol}
                                        </TableCell>
                                        <TableCell className="px-3 py-2 text-xs">
                                          {holding.quantity ?? '—'}
                                        </TableCell>
                                        <TableCell className="px-3 py-2 text-xs">
                                          {holding.market_value ?? '—'}
                                        </TableCell>
                                        <TableCell className="px-3 py-2 text-xs">
                                          {holding.unrealized_pnl ?? '—'}
                                        </TableCell>
                                      </TableRow>
                                    ))}
                                </TableBody>
                              </Table>
                            </div>
                          </div>
                        ) : null}

                        {metrics.recent_orders.length > 0 ? (
                          <div className="mt-3 text-xs text-muted-foreground">
                            Recent orders:{' '}
                            {metrics.recent_orders
                              .slice(0, 5)
                              .map(
                                (order) =>
                                  `${order.symbol ?? '?'} ${order.status ?? 'unknown'}`,
                              )
                              .join(' · ')}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <p className="mt-2 text-sm text-muted-foreground">
                        No performance snapshot is available for this deployment
                        yet.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card className="overflow-hidden p-0 shadow-none">
          <div className="border-b px-3 py-2.5 sm:px-4">
            <h3 className="text-sm font-semibold">Deployment registry</h3>
          </div>
          {deploymentsQuery.isLoading ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Loading…</p>
          ) : deploymentsQuery.isError ? (
            <div className="p-3 sm:p-4">
              <Alert variant="destructive">
                <AlertTitle>Deployment registry is unavailable</AlertTitle>
                <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
                  <span>{(deploymentsQuery.error as Error).message}</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void deploymentsQuery.refetch()}
                    disabled={deploymentsQuery.isFetching}
                  >
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            </div>
          ) : deployments.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">
                No paper deployments registered yet.
              </p>
              <Button
                type="button"
                onClick={() => onModeChange('deploy')}
                className="mt-3"
                size="sm"
              >
                Register in Deploy
              </Button>
            </div>
          ) : (
            <ul>
              {deployments.map((d) => (
                <li
                  key={d.deployment_id}
                  className="border-b px-3 py-2.5 last:border-b-0 sm:px-4"
                >
                  <div className="break-all font-mono text-sm font-medium">
                    {truncateId(d.deployment_id)}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                    {d.ir_id ?? '—'}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="muted">{d.status ?? 'unknown'}</Badge>
                    {d.is_shared ? <Badge variant="muted">Shared</Badge> : null}
                    {d.lean_environment ? (
                      <span className="text-ink-faint">
                        {d.lean_environment}
                      </span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
