import { expect, test, type Page } from '@playwright/test';

const marketPoint = {
  date: '2026-11-12',
  spy_close: 680,
  vix_close: 18,
  breadth_200d: 0.62,
  breadth_50d: 0.55,
  weekly_allocation_tier: 67,
  composite_score_normalized: 71,
  ma_stack_score: 4,
  vix_contango_proxy: 1,
  vix_vs_sma20d_pct: -0.04,
  weekly_allocation_fraction: 0.67,
  market_regime_signal: 70,
  is_bear_market_active: 0,
  spy_above200d: 1,
  spy_below200d_3d: 0,
  risk_on_fast_flags: 3,
  risk_off_fast_flags: 0,
  clamp_risk_off: 0,
  distribution_count_25d: 2,
  trend_score: 5,
  vix_spike_flag: 0,
};

async function installApplicationMocks(
  page: Page,
  stallLocaleLookup = false,
  permissions: string[] = [],
  includeBacktestFixture = false,
  includeMonitorFixture = false,
  includeFailedBacktestFixture = false,
  legacyWatchlists?: unknown,
  includeCandidateSnapshot = false,
  includeBenchmarkFixture = false,
  includeForecastChartFixture = false,
  includeResponsiveScreenerRow = false,
) {
  let stalledLocaleRequestObserved = false;
  let persistedChartPreferences: string | null = null;
  let persistedWatchlistPreferences: string | null = null;
  let persistedTablePreferences: string | null = null;
  let persistedBenchmarkPreferences: string | null = null;
  let savedScreensTenantId: string | null = null;
  await page.addInitScript((watchlists) => {
    localStorage.setItem('token', 'playwright-e2e-placeholder-token');
    localStorage.setItem('LOCALES_LANGUAGE', 'en');
    if (watchlists) {
      localStorage.setItem(
        'sigmarail_screening_studio_watchlists_v1',
        JSON.stringify(watchlists),
      );
    }
  }, legacyWatchlists);

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith('/screens/saved')) {
      savedScreensTenantId = route.request().headers()['x-tenant-id'] ?? null;
    }
    if (path.endsWith('/backtests/compose')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          spec: {},
          ir_id_suggested: null,
          validation: { ok: false, message: 'Fixture is not runnable.' },
        }),
      });
    }
    if (
      includeBacktestFixture &&
      includeCandidateSnapshot &&
      path.endsWith('/backtests/runs/responsive-e2e-run/day-snapshots')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'responsive-e2e-run',
          count: 1,
          snapshots: [
            {
              date: '2025-06-30',
              as_of: '2025-06-30',
              equity: 104_500,
              holdings: ['ACME'],
              candidates: [
                {
                  ticker: 'ACME',
                  price: 101.25,
                  rs_rating: 82,
                  technical_rating: 74,
                  sector: 'Technology',
                },
                {
                  ticker: 'BETA',
                  price: 56.4,
                  rs_rating: 76,
                  technical_rating: 68,
                  sector: 'Healthcare',
                },
              ],
            },
          ],
        }),
      });
    }
    if (
      includeBacktestFixture &&
      includeBenchmarkFixture &&
      path.endsWith('/backtests/runs/responsive-e2e-run/benchmark-comparison')
    ) {
      const symbol = url.searchParams.get('benchmark') || 'SPY';
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'responsive-e2e-run',
          benchmark: symbol,
          count: 3,
          series: [
            {
              date: '2025-01-31',
              strategy_equity: 100000,
              strategy_normalized: 100,
              benchmark_price: 500,
              benchmark_normalized: 100,
            },
            {
              date: '2025-02-28',
              strategy_equity: 103000,
              strategy_normalized: 103,
              benchmark_price: 510,
              benchmark_normalized: 102,
            },
            {
              date: '2025-03-31',
              strategy_equity: 105000,
              strategy_normalized: 105,
              benchmark_price: 515,
              benchmark_normalized: 103,
            },
          ],
          metrics: {
            strategy_total_return: 0.05,
            benchmark_total_return: 0.03,
            beta: 1.1,
            alpha_annualized: 0.02,
            correlation: 0.84,
            up_market_capture: 112,
            down_market_capture: 82,
            tracking_error: 0.06,
            information_ratio: 0.7,
            var_95: -0.02,
            cvar_95: -0.03,
          },
        }),
      });
    }
    if (
      includeBacktestFixture &&
      path.endsWith('/backtests/jobs/responsive-e2e-failed/log')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'responsive-e2e-failed',
          lines: ['Starting run', 'ERROR fixture failure'],
          log_path: 'results/responsive-e2e-failed/lean-backtest.log',
        }),
      });
    }
    if (includeBacktestFixture && path.endsWith('/backtests/runs')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runs: [
            {
              run_id: 'responsive-e2e-run',
              status: 'done',
              spec_title: 'Responsive test strategy',
              ir_id: 'responsive-e2e-strategy',
              period_start: '2025-01-01',
              period_end: '2025-12-31',
              total_return: 0.12,
              sharpe_ratio: 1.1,
              max_drawdown: -0.08,
              total_orders: 4,
            },
            {
              run_id: 'responsive-e2e-run-2',
              status: 'done',
              spec_title: 'Second responsive strategy',
              ir_id: 'responsive-e2e-strategy-2',
              period_start: '2025-01-01',
              period_end: '2025-12-31',
              total_return: 0.08,
              sharpe_ratio: 0.9,
              max_drawdown: -0.1,
              total_orders: 3,
            },
            ...(includeFailedBacktestFixture
              ? [
                  {
                    run_id: 'responsive-e2e-failed',
                    status: 'failed',
                    spec_title: 'Failed responsive strategy',
                    ir_id: 'responsive-e2e-strategy-failed',
                    period_start: '2025-01-01',
                    period_end: '2025-12-31',
                    total_return: 0,
                    sharpe_ratio: 0,
                    max_drawdown: 0,
                    total_orders: 0,
                  },
                ]
              : []),
          ],
        }),
      });
    }
    if (
      includeBacktestFixture &&
      path.endsWith('/backtests/runs/responsive-e2e-run/report')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'responsive-e2e-run',
          ir_id: 'responsive-e2e-strategy',
          period: { start: '2025-01-01', end: '2025-12-31' },
          metrics: {
            total_return: 0.12,
            sharpe_ratio: 1.1,
            max_drawdown: -0.08,
            total_orders: 4,
          },
        }),
      });
    }
    if (
      includeBacktestFixture &&
      path.endsWith('/backtests/runs/responsive-e2e-run/orders')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'responsive-e2e-run',
          orders: [
            {
              id: 'responsive-e2e-order',
              time: Date.parse('2025-03-03T14:30:00Z') / 1000,
              symbol: 'ACME',
              direction: 'buy',
              quantity: 10,
              fillPrice: 101.25,
              status: 'filled',
            },
          ],
          count: 1,
          total: 1,
          truncated: false,
        }),
      });
    }
    if (
      includeBacktestFixture &&
      path.endsWith('/backtests/runs/responsive-e2e-run/asset-allocation')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'responsive-e2e-run',
          total_volume: 0,
          total_pnl: 0,
          symbol_count: 0,
          items: [],
        }),
      });
    }
    if (
      includeBacktestFixture &&
      path.endsWith('/backtests/runs/responsive-e2e-run/closed-trades')
    ) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'responsive-e2e-run',
          trades: [
            {
              id: 'responsive-e2e-trade-closed',
              symbol: 'ACME',
              entry_time: '2025-02-03T14:30:00Z',
              exit_time: '2025-02-14T14:30:00Z',
              entry_price: 100,
              exit_price: 112,
              direction: 'buy',
              quantity: 10,
              profit_loss: 120,
              return_pct: 0.12,
              is_win: true,
              duration: '11.00:00:00',
              mae: -20,
              mfe: 140,
            },
          ],
          open_trades: [
            {
              id: 'responsive-e2e-trade-open',
              symbol: 'OPENX',
              entry_time: '2025-02-17T14:30:00Z',
              entry_price: 100,
              current_price: 103,
              direction: 'buy',
              quantity: 5,
              profit_loss: 15,
              return_pct: 0.03,
              is_win: true,
              status: 'OPEN',
            },
          ],
          count: 1,
          open_count: 1,
          total: 1,
          truncated: false,
        }),
      });
    }
    if (includeBacktestFixture && path.endsWith('/backtests/compare')) {
      const metrics = {
        total_return: 0.12,
        annual_return: 0.1,
        sharpe_ratio: 1.1,
        sortino_ratio: 1.3,
        max_drawdown: -0.08,
        win_rate: 0.6,
        profit_factor: 1.4,
        expectancy: 0.2,
        total_orders: 4,
        total_trades: 4,
        total_fees: 25,
        max_consecutive_wins: 3,
        max_consecutive_losses: 1,
      };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          runs: [
            {
              run_id: 'responsive-e2e-run',
              ir_id: 'responsive-e2e-strategy',
              period_start: '2025-01-01',
              period_end: '2025-12-31',
              metrics,
              points: [],
              point_count: 0,
            },
            {
              run_id: 'responsive-e2e-run-2',
              ir_id: 'responsive-e2e-strategy-2',
              period_start: '2025-01-01',
              period_end: '2025-12-31',
              metrics: { ...metrics, total_return: 0.08, sharpe_ratio: 0.9 },
              points: [],
              point_count: 0,
            },
          ],
          count: 2,
        }),
      });
    }
    if (includeMonitorFixture && path.endsWith('/live/local-runtime')) {
      const deployment = {
        deployment_id: 'monitor-responsive-deployment',
        ir_id: 'monitor-responsive-strategy',
        project: 'SigmaRail',
        mode: 'paper',
        status: 'running',
        container_status: 'running',
        account_name: 'Paper account',
        metrics: {
          as_of: '2026-11-14T20:00:00Z',
          algorithm_id: 'monitor-responsive-algorithm',
          runtime_statistics: {
            Equity: '$105,400',
            Return: '5.4%',
            Drawdown: '1.2%',
          },
          summary_statistics: {},
          holdings: [
            {
              symbol: 'AAPL',
              quantity: 10,
              market_value: '$2,250',
              unrealized_pnl: '$125',
            },
            {
              symbol: 'MSFT',
              quantity: 4,
              market_value: '$1,720',
              unrealized_pnl: '$80',
            },
          ],
          recent_orders: [{ id: 'order-01', symbol: 'AAPL', status: 'filled' }],
        },
      };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: true,
          mode: 'paper',
          project: 'SigmaRail',
          status: 'running',
          active_count: 1,
          max_concurrent: 1,
          deployments: [deployment],
          deployment,
        }),
      });
    }
    if (includeMonitorFixture && path.endsWith('/live/deployments')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          deployments: [
            {
              deployment_id: 'monitor-responsive-deployment',
              ir_id: 'monitor-responsive-strategy',
              status: 'running',
              lean_environment: 'paper',
            },
          ],
        }),
      });
    }
    if (stallLocaleLookup && path.includes('/translations/locales')) {
      stalledLocaleRequestObserved = true;
      await new Promise((resolve) => setTimeout(resolve, 6000));
      if (!route.request().failure()) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      }
      return;
    }
    const body = path.endsWith('/stock-overview')
      ? {
          ticker: url.searchParams.get('ticker')?.toUpperCase() || 'UBER',
          as_of: url.searchParams.get('as_of') || '2026-11-12',
          company_name:
            url.searchParams.get('ticker')?.toUpperCase() === 'UBER'
              ? 'Uber Technologies'
              : url.searchParams.get('ticker')?.toUpperCase() || 'UBER',
          sector: 'Technology',
          industry: 'Software',
          exchange: 'NYSE',
          as_of_kpis: {},
          trend_template: {},
          forward_stats: {},
          quarterly_growth: [
            {
              report_date: '2026-09-30',
              revenue_m: 5000,
              eps: 1.2,
              gross_margin_pct: 0.62,
              net_margin_pct: 0.18,
              revenue_growth_yoy: 8.4,
              eps_growth_yoy: 12.3,
              is_estimate: false,
              eps_actual: 1.2,
              eps_estimate: 1.1,
              eps_surprise_pct: 9.1,
              eps_beat_miss: 'beat',
              revenue_actual: 5000,
              revenue_estimate: 4800,
              revenue_surprise_pct: 4.2,
              revenue_beat_miss: 'beat',
            },
          ],
          annual_growth: [
            {
              year: '2025',
              eps: 3.4,
              eps_actual: 3.4,
              eps_estimate: 3.2,
              eps_chg_pct: 12,
              sales_m: 12000,
              sales_actual: 12000,
              sales_estimate: 11800,
              sales_chg_pct: 8,
              is_estimate: false,
            },
          ],
          chart_series: [
            ...(includeForecastChartFixture
              ? [
                  {
                    time: '2026-11-13',
                    open: 80,
                    high: 82,
                    low: 79,
                    close: 81,
                    volume: 1000000,
                  },
                  {
                    time: '2026-11-16',
                    open: 0,
                    high: 0,
                    low: 0,
                    close: 0,
                    volume: 0,
                    is_forecast: true,
                    is_future: true,
                  },
                ]
              : [
                  {
                    time: url.searchParams.get('as_of') || '2026-11-12',
                    open: 80,
                    high: 82,
                    low: 79,
                    close: 81,
                    volume: 1000000,
                  },
                ]),
          ],
        }
      : path.endsWith('/market-context')
        ? [marketPoint]
        : path.endsWith('/fields')
          ? {
              fields: [
                {
                  name: 'close',
                  label: 'Closing Price',
                  category: 'Price',
                  category_label: 'Price Data',
                  type: 'number',
                  table: 'prices_daily',
                  description:
                    'Point-in-time closing price for the trading session.',
                },
              ],
            }
          : path.endsWith('/saved')
            ? {
                screens: [
                  {
                    id: 'market-leaders',
                    name: 'Market Leaders',
                    description:
                      'High relative strength and top industry rank.',
                    is_system: true,
                    is_shared: false,
                    spec: { version: 1, from: 'daily_screener' },
                  },
                ],
                count: 1,
                shared_catalog_available: true,
              }
            : path.endsWith('/templates')
              ? { templates: [] }
              : path.endsWith('/as-of-range')
                ? { dates: ['2026-11-12'] }
                : path.endsWith('/preview-ir')
                  ? includeResponsiveScreenerRow
                    ? {
                      as_of: '2026-11-12',
                      count: 1,
                      rows: [
                        {
                          ticker: 'ANF',
                          close: 154.25,
                          overall_score: 82,
                          rs_rating: 91,
                          technical_rating: 78,
                          setup_quality_rating: 74,
                          atr_14_pct: 3.2,
                        },
                      ],
                    }
                    : { rows: [] }
                  : [];
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });

  await page.route('**/api/graphql/**', async (route) => {
    const body = route.request().postDataJSON() as { query?: string };
    if (body.query?.includes('currentUser {')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            currentUser: {
              __typename: 'CurrentUserType',
              id: 'e2e-user',
              email: 'responsive.e2e@example.test',
              firstName: 'Responsive',
              lastName: 'E2E',
              language: 'en',
              appearance: 'system',
              chartPreferences: persistedChartPreferences,
              watchlistPreferences: persistedWatchlistPreferences,
              tablePreferences: persistedTablePreferences,
              benchmarkPreferences: persistedBenchmarkPreferences,
              roles: ['admin', 'user'],
              avatar: null,
              otpVerified: false,
              otpEnabled: false,
              tenants: [
                {
                  __typename: 'TenantType',
                  id: 'e2e-organization',
                  name: 'E2E organization',
                  type: 'default',
                  actionLoggingEnabled: false,
                  membership: {
                    __typename: 'TenantMembershipType',
                    id: 'e2e-membership',
                    role: 'OWNER',
                    invitationAccepted: true,
                    inviteeEmailAddress: null,
                    invitationToken: null,
                    userId: 'e2e-user',
                    firstName: 'Responsive',
                    lastName: 'E2E',
                    userEmail: 'responsive.e2e@example.test',
                    avatar: null,
                  },
                },
              ],
            },
          },
        }),
      });
    }

    if (body.query?.includes('currentUserPermissions')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { currentUserPermissions: permissions } }),
      });
    }

    const input = (
      body.variables as
        | {
            input?: {
              chartPreferences?: string;
              watchlistPreferences?: string;
              tablePreferences?: string;
              benchmarkPreferences?: string;
            };
          }
        | undefined
    )?.input;
    if (body.query?.includes('updateCurrentUser') && input?.chartPreferences) {
      persistedChartPreferences = input.chartPreferences;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { updateCurrentUser: { userProfile: { id: 'e2e-profile' } } },
        }),
      });
    }
    if (
      body.query?.includes('updateCurrentUser') &&
      input?.watchlistPreferences
    ) {
      persistedWatchlistPreferences = input.watchlistPreferences;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { updateCurrentUser: { userProfile: { id: 'e2e-profile' } } },
        }),
      });
    }
    if (body.query?.includes('updateCurrentUser') && input?.tablePreferences) {
      persistedTablePreferences = input.tablePreferences;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { updateCurrentUser: { userProfile: { id: 'e2e-profile' } } },
        }),
      });
    }
    if (
      body.query?.includes('updateCurrentUser') &&
      input?.benchmarkPreferences
    ) {
      persistedBenchmarkPreferences = input.benchmarkPreferences;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { updateCurrentUser: { userProfile: { id: 'e2e-profile' } } },
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: {} }),
    });
  });

  return {
    stalledLocaleRequestObserved: () => stalledLocaleRequestObserved,
    persistedChartPreferences: () => persistedChartPreferences,
    persistedWatchlistPreferences: () => persistedWatchlistPreferences,
    persistedTablePreferences: () => persistedTablePreferences,
    persistedBenchmarkPreferences: () => persistedBenchmarkPreferences,
    savedScreensTenantId: () => savedScreensTenantId,
  };
}

test('application shell startup leaves the loading screen when locale lookup stalls', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let localeRequestSeen = false;
  page.on('request', (request) => {
    if (request.url().includes('/translations/locales'))
      localeRequestSeen = true;
  });
  const mocks = await installApplicationMocks(page, true);
  await page.goto('/');

  await expect(
    page.getByRole('heading', { name: 'Stock screener' }),
  ).toBeVisible({ timeout: 10_000 });
  expect(mocks.stalledLocaleRequestObserved()).toBe(true);
  expect(localeRequestSeen).toBe(true);
  await expectResponsiveLayoutBounds(page);
});

test('authentication pages use SigmaRail product branding', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/en/auth/login');

  await expect(page.getByText('Welcome back', { exact: true })).toBeVisible();
  await expect(page.getByText('SigmaRail', { exact: true })).toBeVisible();
  await expect(page.getByText('apptension', { exact: true })).toHaveCount(0);
  await expectResponsiveLayoutBounds(page);
});

test.describe('touch-device application shell', () => {
  test.use({ isMobile: true, hasTouch: true, deviceScaleFactor: 3 });

  const touchViewports = [
    { name: 'phone', width: 390, height: 844 },
    { name: 'tablet portrait', width: 768, height: 1024 },
    { name: 'tablet landscape', width: 1024, height: 768 },
  ];

  for (const viewport of touchViewports) {
    test(`authenticated ${viewport.name} navigation keeps every Studio page visible after switching routes`, async ({
      page,
    }) => {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await installApplicationMocks(page);
      const runtimeErrors: string[] = [];
      page.on('pageerror', (error) => runtimeErrors.push(error.message));
      await page.goto('/en/strategies');
      const shellHeight = await page
        .getByTestId('application-layout-shell')
        .evaluate((element) =>
          Number.parseFloat(getComputedStyle(element).height),
        );
      const viewportHeight = await page.evaluate(() => window.innerHeight);
      expect(shellHeight).toBeGreaterThanOrEqual(viewportHeight - 1);
      expect(shellHeight).toBeLessThanOrEqual(viewportHeight + 1);

      const destinations = [
        { label: 'Screener', path: '/en/screens', heading: 'Stock screener' },
        {
          label: 'Charts',
          path: '/en/charts',
          heading: '',
          testId: 'charts-workspace',
        },
        { label: 'Watchlists', path: '/en/watchlists', heading: 'Watchlists' },
        { label: 'Market', path: '/en/market', heading: 'Market context' },
        {
          label: 'Strategies',
          path: '/en/strategies',
          heading: 'Strategy editor',
        },
        { label: 'Runs', path: '/en/backtests', heading: 'Backtest runs' },
        {
          label: 'Optimize',
          path: '/en/optimize',
          heading: 'Parameter sweeps',
        },
        { label: 'Deploy', path: '/en/deploy', heading: 'Deploy' },
        { label: 'Monitor', path: '/en/monitor', heading: 'Monitor' },
      ];

      for (const destination of destinations) {
        await page.getByRole('button', { name: 'Open menu' }).click();
        await page
          .getByRole('link', { name: destination.label, exact: true })
          .click();
        await expect
          .poll(() => new URL(page.url()).pathname)
          .toBe(destination.path);
        if (destination.testId) {
          await expect(page.getByTestId(destination.testId)).toBeVisible();
        } else {
          await expect(
            page.getByRole('heading', {
              name: destination.heading,
              exact: true,
            }),
          ).toBeVisible();
        }
        await expectResponsiveLayoutBounds(page);
      }

      expect(runtimeErrors).toEqual([]);
    });
  }
});

async function expectResponsiveLayoutBounds(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    viewportHeight:
      window.visualViewport?.height ?? document.documentElement.clientHeight,
    documentHeight: document.documentElement.scrollHeight,
    routeFrame: (() => {
      const frame = document.querySelector(
        '[data-testid="workbench-route-frame"]',
      );
      if (!frame) return null;
      const rect = frame.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom, height: rect.height };
    })(),
  }));
  expect(
    dimensions.content,
    `page content width ${dimensions.content}px exceeds viewport ${dimensions.viewport}px`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
  if (dimensions.routeFrame) {
    expect(dimensions.routeFrame.top).toBeGreaterThanOrEqual(0);
    expect(
      dimensions.routeFrame.bottom,
      'workbench route should end within the visible viewport',
    ).toBeLessThanOrEqual(dimensions.viewportHeight + 1);
    expect(
      dimensions.routeFrame.bottom,
      'workbench route should fill the space below the app header',
    ).toBeGreaterThanOrEqual(dimensions.viewportHeight - 1);
    expect(
      dimensions.documentHeight,
      'the document should not become a second vertical scroll container',
    ).toBeLessThanOrEqual(dimensions.viewportHeight + 1);
  }
}

const viewports = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet portrait', width: 768, height: 1024 },
  { name: 'tablet landscape', width: 1024, height: 768 },
  { name: 'desktop', width: 1440, height: 960 },
];

async function openScreenPicker(page: Page) {
  await page.getByRole('button', { name: 'Actions' }).click();
  await page.getByRole('menuitem', { name: 'Load screen' }).click();
}

for (const viewport of viewports) {
  test(`application shell Screener reaches usable content at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    const mocks = await installApplicationMocks(
      page,
      false,
      [],
      false,
      false,
      false,
      undefined,
      false,
      false,
      false,
      true,
    );
    await page.goto('/en/screens');

    await expect(
      page.getByRole('heading', { name: 'Stock screener' }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Candidate stocks' }),
    ).toBeVisible();
    const criteriaToggle = page.getByRole('button', { name: /Filters/ });
    await expect(criteriaToggle).toHaveAttribute('aria-expanded', 'false');
    await criteriaToggle.click();
    const filterDialog = page.getByRole('dialog', { name: 'Screen filters' });
    await expect(filterDialog).toBeVisible();
    await expect(
      filterDialog.getByRole('button', { name: /add filter/i }),
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(filterDialog).toBeHidden();
    await page.getByRole('button', { name: /choose as-of date/i }).click();
    const datePicker = page.getByRole('dialog');
    await expect(
      datePicker.getByText('As-of date', { exact: true }),
    ).toBeVisible();
    await expect(datePicker.getByText('Quick jumps')).toBeVisible();
    await datePicker
      .getByRole('button', { name: 'Latest', exact: true })
      .click();
    await expect(datePicker).toBeHidden();
    if (viewport.width < 1024) {
      await expect(page.getByRole('table')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'ANF' }).first()).toBeVisible();
    } else {
      await page.getByRole('button', { name: 'Columns' }).click();
      await expect(page.getByRole('menu')).toBeVisible();
      await expect(page.getByRole('menuitemcheckbox').first()).toBeVisible();
      const fieldInfoButton = page.getByRole('button', {
        name: 'Field info: Closing Price',
      });
      await expect(fieldInfoButton).toBeVisible();
      await expect
        .poll(async () => (await fieldInfoButton.boundingBox())?.height ?? 0)
        .toBeGreaterThanOrEqual(32);
      await fieldInfoButton.click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.keyboard.press('Escape');
    }
    await expect
      .poll(() => mocks.savedScreensTenantId())
      .toBe('e2e-organization');
    await openScreenPicker(page);
    await expect(
      page
        .getByRole('dialog')
        .getByRole('heading', { name: 'Load universe screen' }),
    ).toBeVisible();
    await expect(
      page.getByRole('searchbox', { name: 'Search screens' }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'System (1)' }),
    ).toBeVisible();
    await expect(page.getByText('Market Leaders')).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Actions' }).click();
    await page.getByRole('menuitem', { name: 'Save screen' }).click();
    await expect(
      page
        .getByRole('dialog')
        .getByRole('heading', { name: 'Save universe screen' }),
    ).toBeVisible();
    await expect(
      page.getByRole('dialog').getByRole('textbox', { name: 'Screen name' }),
    ).toBeVisible();
    await expectResponsiveLayoutBounds(page);
  });

  test(`field picker adapts its list and detail view at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/screens');

    await page.getByRole('button', { name: /Filters/ }).click();
    const filters = page.getByRole('dialog', { name: 'Screen filters' });
    await expect(filters).toBeVisible();
    await filters.getByRole('button', { name: /add filter/i }).click();
    const picker = page.getByRole('dialog', { name: 'Add Filter' });
    await expect(picker).toBeVisible();
    await expect(
      picker.getByRole('textbox', { name: /search fields/i }),
    ).toBeVisible();
    await picker.getByText('Closing Price', { exact: true }).first().click();

    if (viewport.width < 768) {
      await expect(
        picker.getByRole('button', { name: 'Back to results' }),
      ).toBeVisible();
      await picker.getByRole('button', { name: 'Back to results' }).click();
      await expect(
        picker.getByText('Closing Price', { exact: true }).first(),
      ).toBeVisible();
    } else {
      await expect(
        picker
          .getByText('Point-in-time closing price for the trading session.')
          .last(),
      ).toBeVisible();
    }
    await expectResponsiveLayoutBounds(page);
  });

  test(`Market chart fits at ${viewport.name} width and keeps secondary metrics collapsed`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/market');

    await expect(
      page.getByRole('heading', { name: 'Market context' }),
    ).toBeVisible();
    await expect(page.getByText('Current Session')).toBeVisible();
    const marketRange = page.getByRole('form', {
      name: 'Market history date range',
    });
    await expect(marketRange.locator('input[type="date"]')).toHaveCount(2);
    await expect(
      page.getByRole('textbox', { name: 'Inspect date' }),
    ).toBeVisible();
    await expect(page.locator('canvas').first()).toBeVisible();
    await expect(
      page.locator('details').filter({ hasText: 'Metric guide' }),
    ).not.toHaveAttribute('open', '');
    await expectResponsiveLayoutBounds(page);
  });

  test(`stock chart deep link renders the requested ticker at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    const chartResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/screens/stock-overview') &&
        url.searchParams.get('ticker') === 'JOB';
    });
    await page.goto('/en/stock/JOB/chart?as_of=2026-11-15');

    expect((await chartResponse).ok()).toBeTruthy();

    await expect(
      page.getByRole('heading', { name: 'JOB', exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId('stock-chart-engine')).toBeVisible();
    await expect(page.locator('canvas').first()).toBeVisible();
    await expect(page.getByText(/ClickHouse error/i)).toHaveCount(0);
    await expectResponsiveLayoutBounds(page);
  });

  test(`forecast chart dates do not present placeholder zeroes as traded prices at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await installApplicationMocks(page, false, [], false, false, false, undefined, false, false, true);
    await page.goto('/en/stock/JOB/chart?as_of=2026-11-16');

    const toolbar = page.getByTestId('stock-chart-toolbar');
    await expect(toolbar.getByText('Forecast · 2026-11-16')).toBeVisible();
    await expect(toolbar.getByText('No traded OHLC or volume')).toBeVisible();
    await expect(toolbar.getByText(/O: \$0\.00|H: \$0\.00|L: \$0\.00|C: \$0\.00/)).toHaveCount(0);
  });

  test(`Five-slot strategy editor renders in application shell at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(
      page,
      false,
      [],
      false,
      false,
      false,
      undefined,
      false,
      false,
      false,
      true,
    );
    await page.goto('/en/strategies');

    const slots = [
      { tab: 'Universe', content: 'Candidate stocks' },
      { tab: 'Alpha', content: 'Measures' },
      { tab: 'Portfolio construction', content: 'Book policy' },
      { tab: 'Risk management' },
      { tab: 'Execution', content: 'MOO (open of T)' },
    ];
    for (const slot of slots) {
      const tab = page.getByRole('tab', { name: slot.tab });
      await expect(tab).toBeVisible();
      await tab.click();
      await expect(tab).toHaveAttribute('aria-selected', 'true');
      if (slot.content) {
        await expect(page.getByText(slot.content, { exact: true })).toBeVisible();
      }
      if (slot.tab === 'Universe') {
        await expect(page.getByText('Candidate stocks', { exact: true })).toBeVisible();
        if (viewport.width >= 768) {
          const candidateTable = page.getByTestId('universe-candidates-table');
          await expect(candidateTable).toBeVisible();
          await expect(candidateTable.getByRole('columnheader', { name: 'Price' })).toBeVisible();
          await expect(candidateTable.getByRole('cell', { name: '$154.25' })).toBeVisible();
          await expect(candidateTable.getByRole('cell', { name: '82.0' })).toBeVisible();
          await expect(candidateTable.getByRole('cell', { name: '3.2%' })).toBeVisible();
        }
        const filtersButton = page.getByRole('button', { name: /Edit universe filters/ });
        await filtersButton.click();
        const filtersDialog = page.getByRole('dialog', { name: 'Universe filters' });
        await expect(filtersDialog).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(filtersDialog).toHaveCount(0);
      }
    }
    await expect(page.getByText('Candidate stocks', { exact: true })).not.toBeVisible();
    await page.getByRole('tab', { name: 'Risk management' }).click();
    const addRuleButton = page.getByRole('button', { name: '+ rule' }).first();
    await expect(addRuleButton).toBeVisible();
    await addRuleButton.click();
    const actionType = page.getByRole('combobox', { name: 'Action' }).last();
    await expect(actionType).toBeVisible();
    await actionType.click();
    await page.getByRole('option', { name: 'Ratchet Stop' }).click();
    await expect(actionType).toContainText('Ratchet Stop');
    const ruleTestButton = page
      .getByRole('button', { name: 'Test rules' })
      .first();
    await expect(ruleTestButton).toBeVisible();
    await expect(ruleTestButton).toBeDisabled();
    if (viewport.width < 768) {
      const operandKind = page
        .getByRole('combobox', {
          name: 'Operand kind',
        })
        .first();
      await operandKind.click();
      await page.getByRole('option', { name: 'col', exact: true }).click();
      await expect(
        page.locator('input[aria-label="column name"]').first(),
      ).toBeVisible();
    }
    await expect(
      page.getByText('Launch Baseline Backtest', { exact: true }),
    ).toBeVisible();
    await page.getByRole('tab', { name: 'Alpha' }).click();
    await expect(page.getByText('Measures', { exact: true })).toBeVisible();
    const membershipProbe = page.getByRole('button', {
      name: /Membership probe/,
    });
    await expect(membershipProbe).toBeVisible();
    await membershipProbe.click();
    await expect(membershipProbe).toHaveAttribute('aria-expanded', 'true');
    const cumulativeToggle = page.getByRole('button', {
      name: 'cumulative off',
    });
    await expect(cumulativeToggle).toBeVisible();
    await cumulativeToggle.click();
    await expect(
      page.getByRole('button', { name: 'cumulative on' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: '+ Add measure' }).click();
    await page.getByRole('button', { name: 'Expr (ORDER BY)' }).click();
    await expect(
      page.getByPlaceholder('e.g. screen_1 + screen_2 + code_33'),
    ).toBeVisible();
    const directionBinding = page.getByRole('combobox', {
      name: 'Select measure alias for Direction',
    });
    await directionBinding.click();
    await page.getByRole('option', { name: 'measure_1', exact: true }).click();
    await expect(directionBinding).toContainText('measure_1');
    await expect(
      page.getByRole('textbox', { name: 'Name', exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole('button', { name: 'Strategy settings', exact: true })
      .click();
    await expect(
      page
        .getByRole('dialog')
        .getByRole('heading', { name: 'Strategy settings' }),
    ).toBeVisible();
    await expect(
      page.getByRole('dialog').getByRole('textbox', { name: 'Name' }),
    ).toBeVisible();
    await expect(
      page.getByRole('dialog').getByRole('textbox', { name: 'Strategy ID' }),
    ).toBeVisible();
    await expect(
      page.getByRole('dialog').getByRole('checkbox', {
        name: 'Show in the strategy template library',
      }),
    ).toBeVisible();
    await page
      .getByRole('dialog')
      .getByRole('button', { name: 'Save as template' })
      .click();
    const saveTemplateDialog = page.getByRole('dialog', {
      name: 'Save as Strategy Template',
    });
    await expect(saveTemplateDialog).toBeVisible();
    await expect(
      saveTemplateDialog.getByRole('textbox', { name: 'Template title' }),
    ).toBeVisible();
    await expect(
      saveTemplateDialog.getByRole('combobox').first(),
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(saveTemplateDialog).not.toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.getByRole('button', { name: 'Strategy library' }).click();
    const strategyLibrary = page.getByRole('dialog', {
      name: 'Strategy Spec & Template Library',
    });
    await expect(strategyLibrary).toBeVisible();
    await expect(
      strategyLibrary.getByRole('tab', { name: /Templates/ }),
    ).toBeVisible();
    await expect(
      strategyLibrary.getByRole('textbox', { name: 'Search strategy specs' }),
    ).toBeVisible();
    await expect(
      strategyLibrary.getByRole('combobox', { name: 'Alpha model' }),
    ).toBeVisible();
    await strategyLibrary.getByRole('tab', { name: /Templates/ }).click();
    await strategyLibrary
      .getByRole('textbox', { name: 'Search strategy specs' })
      .fill('no matching fixture');
    await expect(
      strategyLibrary.getByText('No matching strategy specs found'),
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(strategyLibrary).toBeHidden();
    await expectResponsiveLayoutBounds(page);
  });

  test(`Backtest run history renders in application shell at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/backtests');

    await expect(
      page.getByRole('heading', { name: 'Backtest runs' }),
    ).toBeVisible();
    const additionalFilters = page.getByText(
      /^More filters(?: · \d+ active)?$/,
    );
    const minimumSharpeFilter = page.getByText('Min Sharpe', { exact: true });
    if (viewport.width < 768) {
      await expect(additionalFilters).toBeVisible();
      await expect(minimumSharpeFilter).not.toBeVisible();
      await additionalFilters.click();
      await expect(minimumSharpeFilter).toBeVisible();
    } else {
      await expect(additionalFilters).toBeHidden();
      await expect(minimumSharpeFilter).toBeVisible();
    }
    await expectResponsiveLayoutBounds(page);
  });

  test(`active backtest actions fit and open logs at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.route('**/api/backtests/jobs?*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          jobs: [
            {
              job_id: 'responsive-e2e-running',
              ir_id: 'responsive-strategy',
              status: 'running',
              start_date: '2025-01-01',
              end_date: '2025-12-31',
              progress_pct: 0.42,
              elapsed_seconds: 42,
              estimated_remaining_seconds: 58,
              last_log_line: 'Loaded 120 symbols',
            },
          ],
        }),
      }),
    );
    await page.route(
      '**/api/backtests/jobs/responsive-e2e-running/log?*',
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            job_id: 'responsive-e2e-running',
            lines: ['Starting engine', 'Loaded 120 symbols'],
            text: 'Starting engine\\nLoaded 120 symbols',
            log_path: 'results/responsive-e2e-running/lean-backtest.log',
          }),
        }),
    );
    await page.goto('/en/backtests');

    const banner = page.getByText('Active Backtest Execution (1 in progress)');
    await expect(banner).toBeVisible();
    const liveLog = page.getByRole('button', { name: /Live Log/ });
    const abort = page.getByRole('button', { name: /Abort/ });
    await expect(liveLog).toBeVisible();
    await expect(abort).toBeVisible();
    await liveLog.click();
    const logDialog = page.getByRole('dialog');
    await expect(logDialog.getByText(/Execution log/)).toBeVisible();
    await expect(logDialog.getByText('Loaded 120 symbols')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(logDialog).toHaveCount(0);
    await expectResponsiveLayoutBounds(page);
  });

  test(`Backtest run screener uses a responsive layout at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page, false, [], true, false, true);
    await page.goto('/en/backtests');

    await expect(
      page.getByRole('heading', { name: 'Backtest runs' }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Table', exact: true }).click();
    const runCard = page.getByTestId('run-card-responsive-e2e-run');
    const runTable = page.getByRole('table');
    if (viewport.width < 768) {
      await expect(runCard).toBeVisible();
      await expect(runCard.getByText('Responsive test strategy')).toBeVisible();
      await expect(runTable).toBeHidden();
    } else {
      await expect(runTable).toBeVisible();
      await expect(
        runTable.getByText('Responsive test strategy'),
      ).toBeVisible();
      await expect(runCard).toBeHidden();
    }
    if (viewport.width < 768) {
      await page.getByRole('button', { name: 'View log', exact: true }).click();
    } else {
      await page
        .getByRole('button', { name: 'View log for responsive-e2e-failed' })
        .click();
    }
    const executionLog = page.getByRole('dialog', { name: /Execution log/ });
    await expect(executionLog).toBeVisible();
    await expect(executionLog.getByText('ERROR fixture failure')).toBeVisible();
    await expect(
      executionLog.getByRole('searchbox', { name: 'Filter log output' }),
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(executionLog).toBeHidden();
    await expectResponsiveLayoutBounds(page);
  });

  test(`Backtest report navigation fits ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page, false, [], true);
    await page.goto('/en/backtests/responsive-e2e-run/trades');

    const tradeFilter = page.getByRole('searchbox', {
      name: 'Filter trades by ticker',
    });
    await expect(tradeFilter).toBeVisible();
    await tradeFilter.fill('ACM');
    if (viewport.width < 768) {
      await expect(
        page.getByTestId('trade-card-responsive-e2e-trade-closed'),
      ).toBeVisible();
      await expect(
        page.getByTestId('trade-card-responsive-e2e-trade-open'),
      ).toHaveCount(0);
    } else {
      await expect(
        page
          .getByRole('table')
          .first()
          .getByText('ACME', { exact: true })
          .first(),
      ).toBeVisible();
      await expect(
        page.getByRole('row').filter({ hasText: 'OPENX' }),
      ).toHaveCount(0);
    }
    await tradeFilter.fill('');
    if (viewport.width < 768) {
      await page.getByRole('button', { name: 'View chart' }).first().click();
    } else {
      await page.getByRole('button', { name: /view$/i }).first().click();
    }
    const tradeChartDialog = page.getByRole('dialog');
    await expect(
      tradeChartDialog.getByRole('heading', { name: 'ACME' }),
    ).toBeVisible();
    await expect(
      tradeChartDialog.getByRole('button', { name: 'Close Chart (Esc)' }),
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(tradeChartDialog).toBeHidden();
    await page.getByRole('tab', { name: /Open Trades/ }).click();
    if (viewport.width < 768) {
      await expect(
        page.getByTestId('trade-card-responsive-e2e-trade-open'),
      ).toBeVisible();
    } else {
      await expect(
        page.getByRole('row').filter({ hasText: 'OPENX' }),
      ).toBeVisible();
    }

    if (viewport.width < 768) {
      await expect(page.getByText('Execution Orders Log (1)')).toBeVisible();
      await expect(
        page.getByRole('button', { name: 'View chart' }).last(),
      ).toBeVisible();
      await expect(page.getByRole('table')).toBeHidden();
    } else {
      await expect(page.getByText('Execution Orders Log (1)')).toBeVisible();
      await expect(
        page.getByRole('row', { name: /ACME BUY 10 \$101\.25 filled/ }),
      ).toBeVisible();
    }

    if (viewport.width < 768) {
      const sectionPicker = page.getByRole('combobox', {
        name: 'Report section',
      });
      await expect(sectionPicker).toBeVisible();
      await sectionPicker.click();
      await page.getByRole('option', { name: 'Day Scrubber' }).click();
      await expect(page).toHaveURL(/responsive-e2e-run\/scrubber$/);
      await expect(
        page.getByText('No daily snapshots recorded for this run.'),
      ).toBeVisible();
    } else {
      await expect(
        page.getByRole('tab', { name: 'Attribution & Macro' }),
      ).toBeVisible();
    }
    await expectResponsiveLayoutBounds(page);
  });

  test(`Backtest candidate explorer adapts to ${viewport.name} width and keeps ticker selection`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(
      page,
      false,
      [],
      true,
      false,
      false,
      undefined,
      true,
    );
    await page.goto('/en/backtests/responsive-e2e-run/scrubber');

    await expect(
      page.getByRole('heading', { name: 'Point-in-Time Day Scrubber' }),
    ).toBeVisible();
    const candidateTable = page.getByRole('table');
    const betaTicker =
      viewport.width < 1024
        ? page.getByRole('button', { name: /BETA/ })
        : candidateTable.getByRole('button', { name: 'BETA', exact: true });
    if (viewport.width < 1024) {
      await expect(candidateTable).toBeHidden();
      await expect(betaTicker).toBeVisible();
    } else {
      await expect(candidateTable).toBeVisible();
      await expect(betaTicker).toBeVisible();
    }
    await betaTicker.click();
    await expect(betaTicker).toHaveAttribute('aria-pressed', 'true');
    await expect(
      page.getByText('No historical candles found for BETA.'),
    ).toBeVisible();
    await expectResponsiveLayoutBounds(page);
  });

  test(`Benchmark comparison uses responsive AppTension controls at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    const mocks = await installApplicationMocks(
      page,
      false,
      [],
      true,
      false,
      false,
      undefined,
      false,
      true,
    );
    await page.addInitScript(() => {
      localStorage.setItem(
        'sigmarail_custom_benchmarks',
        JSON.stringify(['XLI', 'NVDA']),
      );
    });
    await page.goto('/en/backtests/responsive-e2e-run/overview');

    await expect(
      page.getByText('Benchmark comparison & active risk'),
    ).toBeVisible();
    await expect(page.getByText('Growth of $100')).toBeVisible();
    await expect(
      page.locator('.recharts-responsive-container').first(),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'XLI', exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem(
          'sigmarail-studio.user.e2e-user.custom-benchmarks',
        ),
      ),
    ).toBe(JSON.stringify(['XLI', 'NVDA']));
    expect(
      await page.evaluate(() => localStorage.getItem('sigmarail_custom_benchmarks')),
    ).toBeNull();
    const benchmarkSelect = page.getByRole('combobox', { name: 'Benchmark' });
    await benchmarkSelect.click();
    await page.getByRole('option', { name: 'QQQ · Nasdaq 100' }).click();
    await expect(
      page.getByText(
        '$100 normalized starting value · comparing QQQ (Nasdaq 100)',
      ),
    ).toBeVisible();

    const customBenchmark = page.getByRole('textbox', {
      name: 'Custom benchmark ticker',
    });
    await customBenchmark.fill('DIA');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(
      page.getByText(
        '$100 normalized starting value · comparing DIA (Custom Ticker)',
      ),
    ).toBeVisible();
    await expect
      .poll(() => mocks.persistedBenchmarkPreferences())
      .not.toBeNull();
    expect(JSON.parse(mocks.persistedBenchmarkPreferences() || '[]')).toContain(
      'DIA',
    );
    await expectResponsiveLayoutBounds(page);
  });

  test(`Backtest comparison reads vertically at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page, false, [], true);
    await page.goto('/en/backtests?view=compare');

    const comparisonCheckboxes = page.getByRole('checkbox', {
      name: 'Select for comparison',
    });
    await expect(comparisonCheckboxes).toHaveCount(2);
    await comparisonCheckboxes.nth(0).check();
    await comparisonCheckboxes.nth(1).check();
    await page.getByRole('button', { name: 'Compare (2)' }).click();
    await expect(
      page.getByRole('heading', { name: 'Multi-Run Strategy Comparison' }),
    ).toBeVisible();
    if (viewport.width < 768) {
      await expect(
        page.getByText('Performance Scorecard Matrix'),
      ).toBeVisible();
      await expect(
        page.getByText('Run 1', { exact: true }).first(),
      ).toBeVisible();
      await expect(page.getByRole('table')).toBeHidden();
    } else {
      await expect(page.getByRole('table')).toBeVisible();
      await expect(
        page.getByRole('table').getByText('Total Return'),
      ).toBeVisible();
    }
    await expectResponsiveLayoutBounds(page);
  });

  test(`application shell account profile fits at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/profile');

    await expect(page.getByText('Profile Overview')).toBeVisible();
    await expect(
      page.getByText('responsive.e2e@example.test').first(),
    ).toBeVisible();
    await expectResponsiveLayoutBounds(page);
  });

  test(`application shell organization settings fit at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page, false, [
      'org.settings.view',
      'org.settings.edit',
    ]);
    await page.goto('/en/e2e-organization/tenant/settings/general');

    await expect(
      page.getByRole('heading', { name: 'Organization settings' }),
    ).toBeVisible();
    await expect(page.getByRole('tab', { name: 'General' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Name:' })).toBeVisible();
    await expectResponsiveLayoutBounds(page);
  });

  test(`Chart workspace renders at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/charts');

    await expect(page.getByText('UBER', { exact: true }).first()).toBeVisible();
    const chartWorkspace = page.getByTestId('charts-workspace');
    await expect(chartWorkspace).toBeVisible();
    const chartBounds = await chartWorkspace.boundingBox();
    expect(chartBounds).not.toBeNull();
    expect(chartBounds!.y + chartBounds!.height).toBeLessThanOrEqual(
      viewport.height + 1,
    );
    const chartToolbar = page.getByTestId('stock-chart-toolbar');
    await expect(chartToolbar).toBeVisible();
    const toolbarFits = await chartToolbar.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    );
    expect(
      toolbarFits,
      `chart toolbar should fit at ${viewport.width}px width`,
    ).toBe(true);
    await page.getByRole('button', { name: /Indicators/ }).click();
    await expect(page.getByRole('button', { name: '21W EMA' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByRole('button', { name: '50W SMA' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(
      page.getByRole('button', { name: '200W SMA' }),
    ).toHaveAttribute('aria-pressed', 'false');
    await expect(
      page.getByRole('button', { name: 'Earnings Line' }),
    ).toHaveAttribute('aria-pressed', 'false');
    await expect(
      page.getByRole('button', { name: 'SPX overlay' }),
    ).toHaveAttribute('aria-pressed', 'false');
    await page.getByRole('button', { name: /Indicators/ }).click();
    await expect(
      page.getByRole('combobox', { name: 'Chart range' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Replay' })).toBeVisible();
    await page.getByRole('combobox', { name: 'Chart range' }).click();
    await page.getByRole('option', { name: '1Y' }).click();
    await expect(
      page.getByRole('combobox', { name: 'Chart range' }),
    ).toContainText('1Y');
    await page.getByRole('button', { name: 'Open watchlist strip' }).click();
    await page.getByRole('button', { name: 'Paste', exact: true }).click();
    const watchlistImportDialog = page.getByRole('dialog');
    await expect(
      watchlistImportDialog.getByRole('heading', { name: 'Bulk add symbols' }),
    ).toBeVisible();
    await expect(watchlistImportDialog.getByRole('textbox')).toBeVisible();
    await watchlistImportDialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(watchlistImportDialog).toBeHidden();
    if (viewport.width < 768) {
      await expect(page.getByTestId('charts-content-flow')).toHaveCSS(
        'overflow-y',
        'auto',
      );
      await expect(page.getByTestId('charts-primary-area')).toHaveCSS(
        'overflow-y',
        'visible',
      );
      const quoteHeaderFits = await page
        .getByTestId('charts-quote-header')
        .evaluate((element) => element.scrollWidth <= element.clientWidth + 1);
      expect(quoteHeaderFits).toBe(true);
      const fundamentalsToggle = page.getByRole('button', {
        name: 'Open fundamentals rail',
      });
      await expect(fundamentalsToggle).toBeVisible();
      await fundamentalsToggle.click();
      const fundamentalsPanel = page.getByTestId('fundamentals-panel');
      await expect(fundamentalsPanel).toBeVisible();
      await expect(
        fundamentalsPanel.getByRole('tab', { name: 'Earnings' }),
      ).toBeVisible();
      const chartAreaBounds = await page
        .getByTestId('charts-primary-area')
        .boundingBox();
      const fundamentalsBounds = await fundamentalsPanel.boundingBox();
      expect(chartAreaBounds).not.toBeNull();
      expect(fundamentalsBounds).not.toBeNull();
      expect(fundamentalsBounds!.y).toBeGreaterThanOrEqual(
        chartAreaBounds!.y + chartAreaBounds!.height - 1,
      );
      await fundamentalsPanel.getByRole('tab', { name: 'Earnings' }).click();
      await expect(
        fundamentalsPanel.getByRole('tab', { name: 'Quarterly' }),
      ).toBeVisible();
      await expect(
        fundamentalsPanel.getByText('EPS actual / est.'),
      ).toBeVisible();
      await expect(fundamentalsPanel.getByText('$1.20 / $1.10')).toBeVisible();
      await fundamentalsPanel.getByRole('tab', { name: 'Annual' }).click();
      await expect(
        fundamentalsPanel.getByText('2025', { exact: true }),
      ).toBeVisible();
      await fundamentalsPanel.getByRole('tab', { name: 'Charts' }).click();
      await expect(
        fundamentalsPanel.getByTestId('earnings-estimate-chart'),
      ).toBeVisible();
      await expect(
        fundamentalsPanel.getByText('UBER Forecasts & Estimates Accuracy'),
      ).toBeVisible();
    } else {
      const fundamentalsPanel = page.getByTestId('fundamentals-panel');
      await expect(fundamentalsPanel).toBeVisible();
      const chartAreaBounds = await page
        .getByTestId('charts-primary-area')
        .boundingBox();
      const fundamentalsBounds = await fundamentalsPanel.boundingBox();
      expect(chartAreaBounds).not.toBeNull();
      expect(fundamentalsBounds).not.toBeNull();
      expect(fundamentalsBounds!.y).toBeGreaterThanOrEqual(
        chartAreaBounds!.y + chartAreaBounds!.height - 1,
      );
      await fundamentalsPanel.getByRole('tab', { name: 'Earnings' }).click();
      await expect(fundamentalsPanel.getByText('$1.20 / $1.10')).toBeVisible();
      await fundamentalsPanel.getByRole('tab', { name: 'Annual' }).click();
      await expect(
        fundamentalsPanel.getByText('2025', { exact: true }),
      ).toBeVisible();
      await fundamentalsPanel.getByRole('tab', { name: 'Charts' }).click();
      await expect(
        fundamentalsPanel.getByTestId('earnings-estimate-chart'),
      ).toBeVisible();
      await expect(
        fundamentalsPanel.getByText('UBER Forecasts & Estimates Accuracy'),
      ).toBeVisible();
    }
    await expectResponsiveLayoutBounds(page);
  });

  test(`Watchlists render at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/watchlists');

    await expect(
      page.getByRole('heading', { name: /Watchlists/ }),
    ).toBeVisible();
    if (viewport.width < 1024) {
      await expect(
        page.getByRole('combobox', { name: 'Active watchlist' }),
      ).toBeVisible();
      await expect(
        page.getByRole('button', { name: 'Open chart for UBER' }),
      ).toBeVisible();
      await page.getByRole('combobox', { name: 'Active watchlist' }).click();
      await page
        .getByRole('option', { name: /High Conviction Compounders/ })
        .click();
      await expect(
        page.getByRole('button', { name: 'Open chart for NVDA' }),
      ).toBeVisible();
      await page
        .getByRole('button', {
          name: 'Actions for High Conviction Compounders',
        })
        .click();
      await expect(
        page.getByRole('menuitem', { name: 'Rename' }),
      ).toBeVisible();
      await expect(
        page.getByRole('menuitem', { name: 'Delete' }),
      ).toBeVisible();
      await page.keyboard.press('Escape');
    } else {
      await expect(page.getByRole('table')).toBeVisible();
    }
    await page.getByRole('button', { name: 'Import symbols' }).click();
    const importDialog = page.getByRole('dialog', { name: 'Import symbols' });
    await expect(importDialog).toBeVisible();
    await importDialog
      .getByRole('textbox', { name: 'Symbols to import' })
      .fill('AAPL, MSFT');
    await expect(
      importDialog.getByRole('button', { name: 'Import symbols' }),
    ).toBeEnabled();
    await importDialog.getByRole('button', { name: 'Cancel' }).click();
    await expectResponsiveLayoutBounds(page);
  });

  test(`Deploy workflow renders at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/deploy');

    await expect(
      page.getByRole('heading', { name: 'Deploy', exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/Controls are disabled/)).toBeVisible();
    await expectResponsiveLayoutBounds(page);
  });

  test(`Monitor workflow renders at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page, false, [], false, true);
    await page.goto('/en/monitor');

    await expect(page.getByRole('heading', { name: 'Monitor' })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Deploy settings' }),
    ).toBeVisible();
    const visibleHoldings = page.getByTestId(
      viewport.name === 'phone'
        ? 'monitor-holdings-mobile'
        : 'monitor-holdings-table',
    );
    await expect(
      visibleHoldings.getByText('AAPL', { exact: true }),
    ).toBeVisible();
    await expect(
      visibleHoldings.getByText('Market value', { exact: true }).first(),
    ).toBeVisible();
    if (viewport.name === 'phone') {
      await expect(page.getByTestId('monitor-holdings-mobile')).toBeVisible();
      await expect(page.getByTestId('monitor-holdings-table')).toBeHidden();
    } else {
      await expect(page.getByTestId('monitor-holdings-table')).toBeVisible();
      await expect(page.getByTestId('monitor-holdings-mobile')).toBeHidden();
    }
    await expectResponsiveLayoutBounds(page);
  });

  test(`Optimization workflow renders at ${viewport.name} width`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await installApplicationMocks(page);
    await page.goto('/en/optimize');

    await expect(
      page.getByRole('heading', { name: 'Parameter sweeps' }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'New sweep' }).click();
    const sweepDialog = page.getByRole('dialog');
    await expect(
      sweepDialog.getByRole('heading', { name: 'Launch parameter sweep' }),
    ).toBeVisible();
    const dialogBounds = await sweepDialog.boundingBox();
    expect(dialogBounds).not.toBeNull();
    expect(dialogBounds!.x).toBeGreaterThanOrEqual(0);
    expect(dialogBounds!.x + dialogBounds!.width).toBeLessThanOrEqual(
      viewport.width,
    );
    await expectResponsiveLayoutBounds(page);
  });
}

test('saved screen picker reports catalog failures instead of showing an empty library', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/screens/templates', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        templates: [{ id: 'minervini_trend_template', label: 'Minervini Trend Template' }],
      }),
    });
  });
  await page.route('**/api/screens/saved', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Screen catalog unavailable.' }),
    });
  });
  await page.goto('/en/screens');
  await openScreenPicker(page);

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('alert')).toContainText(
    'Saved screens could not be loaded',
  );
  await expect(dialog.getByText('Minervini Trend Template')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'System (1)' })).toBeVisible();
  await expect(
    dialog.getByText(
      'No screens found matching your filter or search criteria.',
    ),
  ).toHaveCount(0);
});

test('saved screen picker keeps system templates available when shared saved screens are unavailable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/screens/templates', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        templates: [
          {
            id: 'minervini_trend_template',
            label: 'Minervini Trend Template',
            description: 'A canonical built-in universe template.',
          },
        ],
      }),
    });
  });
  await page.route('**/api/screens/templates/minervini_trend_template', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'minervini_trend_template',
        label: 'Minervini Trend Template',
        screen_ir: 'universe_query_v1',
        spec: {
          version: 1,
          from: 'daily_screener',
          select: ['ticker', 'close'],
          where: { op: 'gte', left: { field: 'rs_rating' }, right: { literal: 70 } },
        },
      }),
    });
  });
  await page.route('**/api/screens/saved', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        screens: [],
        count: 0,
        shared_catalog_available: false,
        shared_catalog_warning:
          'Legacy shared saved screens are temporarily unavailable. Your workspace screens are still available.',
      }),
    });
  });
  await page.goto('/en/screens');
  await openScreenPicker(page);

  const dialog = page.getByRole('dialog');
  await expect(
    page.getByText(/Legacy shared saved screens are unavailable/),
  ).toHaveCount(0);
  await expect(dialog.getByRole('status')).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'System (1)' })).toBeVisible();
  await expect(dialog.getByText('Minervini Trend Template')).toBeVisible();
  await expect(dialog.getByText('No screens are available yet.')).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: 'Retry catalog' })).toHaveCount(0);
  const templateDetailResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith('/api/screens/templates/minervini_trend_template'),
  );
  await dialog.getByRole('button', { name: 'Load template Minervini Trend Template' }).click();
  await templateDetailResponse;
  await expect(dialog).not.toBeVisible();
});

test('saved screen picker separates and loads the signed-in user library', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/screens/saved', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        screens: [
          {
            id: 'market-leaders',
            name: 'Market Leaders',
            is_system: true,
            spec: { version: 1, from: 'daily_screener' },
          },
          {
            id: 'user-screen-1',
            name: 'My Quality Momentum Screen',
            is_system: false,
            is_shared: false,
            spec: {
              version: 1,
              from: 'daily_screener',
              select: ['ticker', 'close'],
              where: {
                op: 'gte',
                left: { field: 'close' },
                right: { literal: 20 },
              },
            },
          },
        ],
        count: 2,
        shared_catalog_available: true,
      }),
    });
  });
  await page.goto('/en/screens');
  await openScreenPicker(page);

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: 'All (2)' })).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'System (1)' })).toBeVisible();
  await dialog.getByRole('button', { name: 'Saved (1)' }).click();
  await expect(dialog.getByText('My Quality Momentum Screen')).toBeVisible();
  await dialog.getByRole('button', { name: 'Load' }).click();
  await expect(dialog).toBeHidden();
});

test('monitor keeps service failures distinct from empty runtime and deployment states', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/live/local-runtime**', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Runtime status unavailable.' }),
    });
  });
  await page.route('**/api/live/deployments**', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Deployment registry unavailable.' }),
    });
  });
  await page.goto('/en/monitor');

  await expect(
    page.getByRole('heading', { name: 'Deployment registry is unavailable' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Runtime status is unavailable' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(2);
  await expect(page.getByText('No paper deployments registered yet.')).toHaveCount(
    0,
  );
  await expect(page.getByText(/No runtime is active/)).toHaveCount(0);
});

test('optimizer reports session loading failures instead of showing zero studies', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/backtests/optimize/sessions**', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Optimization service unavailable.' }),
    });
  });
  await page.goto('/en/optimize');

  await expect(
    page.getByRole('heading', {
      name: 'Optimization studies could not be loaded',
    }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  await expect(page.getByText('No optimization studies yet')).toHaveCount(0);
});

test('optimizer reports selected-study failures instead of showing an empty state', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/backtests/optimize/sessions**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [
          {
            session_id: 'optimizer-error-fixture',
            strategy_id: 'fixture-strategy',
            base_ir_id: 'fixture-strategy',
            title: 'Fixture study',
            objective: 'sharpe_ratio',
            param_x_name: 'ema_period',
            param_x_values: [10, 20],
            param_y_values: [],
            total_combinations: 2,
            status: 'running',
            strategy_type: 'grid',
            constraints: [],
            created_at: '2026-11-16T12:00:00Z',
            updated_at: '2026-11-16T12:00:00Z',
          },
        ],
        count: 1,
      }),
    });
  });
  await page.route(
    '**/api/backtests/optimize/sessions/optimizer-error-fixture',
    async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Sweep result unavailable.' }),
      });
    },
  );
  await page.goto('/en/optimize');

  await expect(
    page.getByRole('heading', { name: 'Sweep results could not be loaded' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  await expect(page.getByText('No optimization studies yet')).toHaveCount(0);
});

test('backtests expose run-list and job-status failures instead of empty results', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.route('**/api/backtests/jobs?*', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Backtest job service unavailable.' }),
    });
  });
  await page.route('**/api/backtests/runs?*', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Backtest runs unavailable.' }),
    });
  });
  await page.goto('/en/backtests');

  await expect(
    page.getByRole('heading', { name: 'Backtest runs are unavailable' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Job status is unavailable' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(2);
  await expect(page.getByText('No runs match filters. Adjust filters above to inspect runs.')).toHaveCount(0);
});

test('Appearance selection updates the application shell theme and profile setting', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);

  let persistedAppearance: string | undefined;
  page.on('request', (request) => {
    if (!request.url().includes('/api/graphql') || request.method() !== 'POST')
      return;
    const body = request.postDataJSON() as {
      query?: string;
      variables?: { input?: { appearance?: string } };
    };
    if (body.query?.includes('updateCurrentUser')) {
      persistedAppearance = body.variables?.input?.appearance;
    }
  });

  await page.goto('/en/screens');
  await page.getByRole('button', { name: 'Open user menu' }).click();
  await page.getByRole('menuitem', { name: 'Appearance' }).click();
  await page.getByRole('menuitem', { name: 'Dark' }).click();

  await expect
    .poll(() =>
      page
        .locator('html')
        .evaluate((element) => element.classList.contains('dark')),
    )
    .toBe(true);
  await expect.poll(() => persistedAppearance).toBe('dark');
});

test('Chart preferences persist to the signed-in application shell profile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const mocks = await installApplicationMocks(page);
  await page.goto('/en/charts');

  await expect.poll(() => mocks.persistedChartPreferences()).not.toBeNull();
  expect(JSON.parse(mocks.persistedChartPreferences() || '{}')).toMatchObject({
    lastTimeframe: '1W',
    '1D': { range: '6M' },
    '1W': { range: '2Y' },
  });
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem(
          'sigmarail-studio.user.e2e-user.chart-settings.v2',
        ),
      ),
    )
    .not.toBeNull();
  expect(
    await page.evaluate(() =>
      localStorage.getItem('sigmarail-studio.chart-settings.v2'),
    ),
  ).toBeNull();
});

test('legacy browser watchlists migrate into the signed-in application profile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const legacyLists = [
    {
      id: 'legacy-research',
      name: 'Legacy research',
      symbols: [{ ticker: 'MSFT', flag: 'blue', added_at: '2026-11-16' }],
      created_at: '2026-11-16',
      updated_at: '2026-11-16',
    },
  ];
  const mocks = await installApplicationMocks(
    page,
    false,
    [],
    false,
    false,
    false,
    legacyLists,
  );
  await page.goto('/en/watchlists');

  await expect(page.getByRole('heading', { name: /Watchlists/ })).toBeVisible();
  await expect.poll(() => mocks.persistedWatchlistPreferences()).not.toBeNull();
  expect(
    JSON.parse(mocks.persistedWatchlistPreferences() || '[]'),
  ).toMatchObject(legacyLists);
  expect(
    await page.evaluate(() =>
      JSON.parse(
        localStorage.getItem('sigmarail_studio_watchlists_v1.e2e-user') || '[]',
      ),
    ),
  ).toMatchObject(legacyLists);
  expect(
    await page.evaluate(() =>
      localStorage.getItem('sigmarail_screening_studio_watchlists_v1'),
    ),
  ).toBeNull();
});

test('table density is saved to the signed-in application profile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const mocks = await installApplicationMocks(page);
  await page.goto('/en/watchlists');

  await expect(page.getByRole('table')).toBeVisible();
  await page.getByTitle('Toggle row density').click();
  await expect.poll(() => mocks.persistedTablePreferences()).not.toBeNull();
  expect(JSON.parse(mocks.persistedTablePreferences() || '{}')).toMatchObject({
    'watchlist.tech_leaders': { density: 'comfortable' },
  });
});

test('optimizer results use the shared table and preserve row selection and comparison', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);

  const session = {
    session_id: 'optimizer-responsive-session',
    strategy_id: 'responsive-strategy',
    base_ir_id: 'responsive-strategy',
    title: 'Responsive optimizer study',
    objective: 'sharpe_ratio',
    param_x_name: 'ema_period',
    param_x_values: [10, 20],
    param_y_values: [],
    total_combinations: 2,
    status: 'completed',
    strategy_type: 'grid',
    constraints: [],
    created_at: '2026-11-16T12:00:00Z',
    updated_at: '2026-11-16T12:00:00Z',
  };
  const allPoints = [
    {
      run_id: 'optimizer-e2e-run-1',
      ir_id: 'responsive-strategy',
      total_return: 0.12,
      annual_return: 0.1,
      sharpe_ratio: 1.3,
      sortino_ratio: 1.4,
      max_drawdown: -0.08,
      win_rate: 0.6,
      profit_factor: 1.5,
      total_orders: 4,
      score: 2.1,
      parameters: { ema_period: 10 },
      stability_score: 0.85,
      passes_constraints: true,
    },
    {
      run_id: 'optimizer-e2e-run-2',
      ir_id: 'responsive-strategy',
      total_return: -0.04,
      annual_return: -0.03,
      sharpe_ratio: -0.2,
      sortino_ratio: -0.1,
      max_drawdown: -0.16,
      win_rate: 0.35,
      profit_factor: 0.8,
      total_orders: 7,
      score: -0.4,
      parameters: { ema_period: 20 },
      stability_score: 0.42,
      passes_constraints: false,
    },
  ];

  await page.route('**/api/backtests/optimize/sessions?*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [session], count: 1 }),
    }),
  );
  await page.route(
    '**/api/backtests/optimize/sessions/optimizer-responsive-session',
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session,
          completed_runs: 2,
          total_combinations: 2,
          is_done: true,
          best_run: allPoints[0],
          heatmap: {
            param_x_name: 'ema_period',
            param_x_values: [10, 20],
            param_y_values: [],
            sharpe_matrix: [[1.3, -0.2]],
            return_matrix: [[0.12, -0.04]],
            drawdown_matrix: [[-0.08, -0.16]],
            run_id_matrix: [[allPoints[0].run_id, allPoints[1].run_id]],
          },
          pareto_frontier: [allPoints[0]],
          all_points: allPoints,
        }),
      }),
  );
  await page.route('**/api/backtests/compare?*', (route) => {
    const ids =
      new URL(route.request().url()).searchParams.get('run_ids')?.split(',') ??
      [];
    const metrics = {
      total_return: 0.12,
      annual_return: 0.1,
      sharpe_ratio: 1.3,
      sortino_ratio: 1.4,
      max_drawdown: -0.08,
      win_rate: 0.6,
      profit_factor: 1.5,
      expectancy: 0.2,
      total_orders: 4,
      total_trades: 4,
      total_fees: 25,
      max_consecutive_wins: 3,
      max_consecutive_losses: 1,
    };
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        runs: ids.map((run_id, index) => ({
          run_id,
          ir_id: 'responsive-strategy',
          period_start: '2025-01-01',
          period_end: '2025-12-31',
          metrics: { ...metrics, total_return: 0.12 - index * 0.04 },
          points: [],
          point_count: 0,
        })),
        count: ids.length,
      }),
    });
  });

  await page.goto('/en/optimize');
  await expect(page.getByText('Optimization Runs Leaderboard')).toBeVisible();
  await expect(page.getByText('ema_period=10')).toBeVisible();
  await page.getByRole('tab', { name: /Matrix Heatmap/ }).click();
  await expect(
    page.getByRole('heading', { name: '2D Hyperparameter Response Heatmap' }),
  ).toBeVisible();
  await page.getByRole('tab', { name: 'Total Return' }).click();
  const heatmapCell = page.getByRole('button', { name: '12.0%' });
  await expect(heatmapCell).toBeVisible();
  await heatmapCell.click();
  await page.getByRole('tab', { name: /2D Parameter Space/ }).click();
  await page.getByRole('combobox', { name: 'Color metric' }).click();
  await page.getByRole('option', { name: 'Stability Index' }).click();
  await page
    .getByRole('checkbox', { name: 'Select optimizer-e2e-run-1' })
    .click();
  await page
    .getByRole('checkbox', { name: 'Select optimizer-e2e-run-2' })
    .click();
  await expect(
    page.getByRole('button', { name: /compare selected \(2\)/i }),
  ).toBeVisible();
  await page.getByRole('checkbox', { name: 'Passes Constraints Only' }).click();
  await expect(page.getByText('1 of 2 variants')).toBeVisible();
  await page.getByRole('button', { name: /compare selected \(2\)/i }).click();
  await expect(
    page.getByRole('heading', { name: 'Multi-Run Strategy Comparison' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Exit Comparison' }),
  ).toBeVisible();
  await expectResponsiveLayoutBounds(page);
});

test('Legacy strategy deep link and slot query mount inside the application shell', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApplicationMocks(page);
  await page.goto('/en/strategies/research-one?slot=universe');

  await expect(page.getByRole('tab', { name: 'Universe' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('Candidate stocks', { exact: true })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Execution' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'MOO (open of T)' })).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  expect(new URL(page.url()).searchParams.get('slot')).toBe('universe');
  await page.getByRole('tab', { name: 'Execution' }).click();
  await expect(page.getByRole('button', { name: 'MOO (open of T)' })).toBeVisible();
  await expect(page.getByText('Candidate stocks', { exact: true })).not.toBeVisible();
  await expect
    .poll(() => new URL(page.url()).searchParams.get('slot'))
    .toBe('execution');
  await expectResponsiveLayoutBounds(page);
});
