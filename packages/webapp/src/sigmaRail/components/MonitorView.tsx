import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchLiveDeploymentStatus, fetchLiveDeployments, fetchLocalLiveRuntime } from '../api/live';
import type { LiveDeploymentStatus, StrategyDecisionEvent, StudioMode } from '../types';
import { PageHeadline } from '@sb/webapp-core/components/pageHeadline';
import { Button } from '@sb/webapp-core/components/ui/button';
import { StockIntrospectionPanel } from './workbench/StockIntrospectionPanel';
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

function snapshotAgeLabel(timestamp: string): string {
  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) return 'age unavailable';
  const ageMs = Math.max(0, Date.now() - parsed);
  const minutes = Math.floor(ageMs / 60_000);
  if (minutes < 60) return `${minutes}m old`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h old`;
  return `${Math.floor(hours / 24)}d old`;
}

function truncateId(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

export function MonitorView({
  onModeChange,
}: {
  onModeChange: (mode: StudioMode) => void;
}) {
  const [selectedHolding, setSelectedHolding] = useState<{
    deploymentId: string;
    ticker: string;
    marketPrice?: number | string;
    snapshotAt: string;
    asOfDate: string;
  } | null>(null);
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
  const selectedStatusQuery = useQuery<LiveDeploymentStatus>({
    queryKey: ['live-deployment-status', selectedHolding?.deploymentId],
    queryFn: () => fetchLiveDeploymentStatus(selectedHolding!.deploymentId),
    enabled: Boolean(selectedHolding?.deploymentId),
  });
  const selectedSnapshot = selectedStatusQuery.data?.latest_snapshot ?? {};
  const selectedDecisionEvents = Array.isArray(selectedSnapshot.decision_events)
    ? selectedSnapshot.decision_events as StrategyDecisionEvent[]
    : [];
  const selectedStrategyHash = typeof selectedSnapshot.strategy_content_hash === 'string'
    ? selectedSnapshot.strategy_content_hash
    : typeof selectedStatusQuery.data?.spec_summary?.ir_content_hash === 'string'
      ? selectedStatusQuery.data.spec_summary.ir_content_hash
      : null;
  const selectedAsOf = typeof selectedSnapshot.as_of === 'string'
    ? selectedSnapshot.as_of.slice(0, 10)
    : selectedHolding?.asOfDate ?? new Date().toISOString().slice(0, 10);
  const decisionStartDate = new Date(`${selectedAsOf}T00:00:00Z`);
  decisionStartDate.setUTCDate(decisionStartDate.getUTCDate() - 30);
  const selectedDecisionStart = decisionStartDate.toISOString().slice(0, 10);
  const snapshotAge = selectedHolding ? snapshotAgeLabel(selectedHolding.snapshotAt) : 'age unavailable';

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
                                    <button type="button" className="font-mono text-sm font-semibold underline-offset-2 hover:underline" onClick={() => {
                                      const snapshotAt = metrics.as_of;
                                      setSelectedHolding({
                                        deploymentId: deployment.deployment_id ?? '',
                                        ticker: holding.symbol,
                                        marketPrice: holding.market_price,
                                        snapshotAt,
                                        asOfDate: snapshotAt.slice(0, 10),
                                      });
                                    }}>
                                      {holding.symbol} <span aria-hidden="true">↗</span>
                                    </button>
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
                                        <button type="button" className="font-mono underline-offset-2 hover:underline" onClick={() => {
                                          const snapshotAt = metrics.as_of;
                                          setSelectedHolding({
                                            deploymentId: deployment.deployment_id ?? '',
                                            ticker: holding.symbol,
                                            marketPrice: holding.market_price,
                                            snapshotAt,
                                            asOfDate: snapshotAt.slice(0, 10),
                                          });
                                        }}>{holding.symbol}</button>
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

      {selectedHolding ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedHolding(null);
        }}>
          <aside className="h-[100dvh] w-full border-l border-line bg-surface shadow-2xl sm:w-[min(92vw,42rem)] lg:w-[min(58vw,52rem)]" aria-label={`${selectedHolding.ticker} live stock review`}>
            {selectedStatusQuery.isLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading strategy evidence…</div>
            ) : selectedStatusQuery.isError ? (
              <div className="p-5 text-sm text-destructive">Could not load deployment evidence: {(selectedStatusQuery.error as Error).message}</div>
            ) : (
              <StockIntrospectionPanel
                ticker={selectedHolding.ticker}
                asOfDate={selectedAsOf}
                onClose={() => setSelectedHolding(null)}
                decisionEvents={selectedDecisionEvents.filter((event) => event.ticker.toUpperCase() === selectedHolding.ticker.toUpperCase())}
                decisionStart={selectedDecisionStart}
                decisionEnd={selectedAsOf}
                strategyHash={selectedStrategyHash}
                sourceLabel="Live deployment evidence"
                contextLabel={`ClickHouse daily research context · as of ${selectedAsOf}`}
                markContext={{
                  label: `LEAN broker mark · ${snapshotAge}`,
                  value: selectedHolding.marketPrice == null ? '—' : String(selectedHolding.marketPrice),
                  timestamp: selectedHolding.snapshotAt,
                }}
              />
            )}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
