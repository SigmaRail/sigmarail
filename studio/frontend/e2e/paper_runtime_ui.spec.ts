import { expect, test } from '@playwright/test';

const paperRun = {
  run_id: 'paper-run-01',
  ir_id: 'paper-strategy-01',
  run_timestamp: '2026-11-01T00:00:00Z',
  total_return: 0.12,
  annual_return: 0.12,
  sharpe_ratio: 1.4,
  max_drawdown: 0.08,
};

const paperAccount = {
  id: 'e2e-paper-account',
  provider: 'alpaca',
  data_provider: 'alpaca',
  environment: 'paper' as const,
  display_name: 'E2E Alpaca paper',
  account_identifier: 'paper-test-account',
  active: true,
  credentials_configured: true,
  connection_verification_available: true,
  updated_at: '2026-11-01T00:00:00Z',
};

const paperDeployment = {
  deployment_id: 'paper-e2e-001',
  ir_id: paperRun.ir_id,
  approval_backtest_run_id: paperRun.run_id,
  project: 'VeraTradingLab',
  mode: 'paper' as const,
  brokerage: 'alpaca',
  data_provider: 'alpaca',
  account_profile_id: paperAccount.id,
  account_name: paperAccount.display_name,
  status: 'running',
};

test('paper account setup and start are driven through the Studio UI', async ({ page }) => {
  let savedProfile: typeof paperAccount | null = null;
  let savedAccountRequest: Record<string, unknown> | null = null;
  let accountActive = true;
  let runtimeActionRequest: Record<string, unknown> | null = null;
  let runtimeStarted = false;

  // Keep the browser flow deterministic and guarantee it cannot contact a real
  // broker, ClickHouse, LEAN container, or local Studio API.
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const { pathname, searchParams } = new URL(request.url());
    const method = request.method();
    if (!pathname.startsWith('/api/')) return route.continue();
    const fulfill = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (method === 'GET' && pathname === '/api/backtests/runs') {
      return fulfill({ runs: [paperRun] });
    }
    if (method === 'GET' && pathname === '/api/live/deployments') {
      return fulfill({ deployments: [] });
    }
    if (method === 'GET' && pathname === '/api/live/accounts') {
      return fulfill({ profiles: savedProfile ? [{ ...savedProfile, active: accountActive }] : [] });
    }
    if (method === 'GET' && pathname === '/api/live/brokerages') {
      return fulfill({
        brokerages: [{
          id: 'alpaca',
          label: 'Alpaca',
          cli_name: 'alpaca',
          default_data_provider: 'alpaca',
          environments: { paper: 'paper', live: 'live' },
          credentials: [
            { key: 'api_key', label: 'API key', secret: true, required: true },
            { key: 'api_secret', label: 'API secret', secret: true, required: true },
          ],
        }],
        data_providers: [{
          id: 'alpaca',
          label: 'Alpaca IEX',
          cli_name: 'alpaca',
          credentials: [],
        }],
      });
    }
    if (method === 'GET' && pathname === '/api/live/local-runtime') {
      return fulfill({
        enabled: true,
        mode: 'paper',
        project: 'VeraTradingLab',
        status: runtimeStarted ? 'running' : 'stopped',
        active_count: runtimeStarted ? 1 : 0,
        max_concurrent: 2,
        deployments: runtimeStarted ? [paperDeployment] : [],
        deployment: runtimeStarted ? paperDeployment : null,
      });
    }
    if (method === 'GET' && pathname === '/api/live/promotion-gate') {
      return fulfill({
        ok: true,
        run_id: searchParams.get('approval_backtest_run_id'),
        ir_id: searchParams.get('ir_id'),
        job_status: 'done',
        run_summary: {
          total_return: paperRun.total_return,
          annual_return: paperRun.annual_return,
          sharpe_ratio: paperRun.sharpe_ratio,
          max_drawdown: paperRun.max_drawdown,
        },
      });
    }
    if (method === 'POST' && pathname === '/api/live/accounts') {
      savedAccountRequest = await request.postDataJSON() as Record<string, unknown>;
      savedProfile = paperAccount;
      return fulfill(savedProfile);
    }
    if (method === 'POST' && pathname === `/api/live/accounts/${paperAccount.id}/verify`) {
      return fulfill({
        supported: true,
        verified: true,
        message: 'Alpaca account connection verified with a read-only request. Data-feed entitlement is not verified.',
        account_status: 'ACTIVE',
        feed_verified: false,
      });
    }
    if (method === 'PATCH' && pathname === `/api/live/accounts/${paperAccount.id}`) {
      const body = await request.postDataJSON() as { active?: boolean };
      accountActive = Boolean(body.active);
      return fulfill({ ...paperAccount, active: accountActive });
    }
    if (method === 'POST' && pathname === '/api/live/local-runtime') {
      runtimeActionRequest = await request.postDataJSON() as Record<string, unknown>;
      runtimeStarted = true;
      return fulfill({ deployment: paperDeployment });
    }

    // Unused app queries get an empty response instead of reaching a server.
    return fulfill({}, method === 'GET' ? 200 : 404);
  });

  await page.goto('/screens');
  await page.getByRole('link', { name: 'Deploy' }).click();

  await expect(page.getByRole('heading', { name: 'Local LEAN trading' })).toBeVisible();
  await page.getByRole('button', { name: 'paper-run-01' }).click();
  await page.getByLabel('LEAN brokerage').selectOption('alpaca');
  await page.getByLabel('Live data provider (separate from brokerage)').selectOption('alpaca');
  await page.getByLabel('Account environment').selectOption('paper');
  await page.getByLabel('Account label').fill(paperAccount.display_name);
  await page.getByLabel('API key').fill('E2E_FAKE_API_KEY');
  await page.getByLabel('API secret').fill('E2E_FAKE_API_SECRET');
  await page.getByRole('button', { name: 'Save account and vault credentials' }).click();

  await expect(page.getByText('Account details saved; credentials are secured in the OS vault.')).toBeVisible();
  await expect(page.getByLabel('API key')).toHaveValue('');
  await expect(page.getByLabel('API secret')).toHaveValue('');
  expect(savedAccountRequest).toMatchObject({
    provider: 'alpaca',
    data_provider: 'alpaca',
    environment: 'paper',
    display_name: paperAccount.display_name,
    credentials: { api_key: 'E2E_FAKE_API_KEY', api_secret: 'E2E_FAKE_API_SECRET' },
  });

  await page.getByRole('button', { name: 'Verify broker connection' }).click();
  await expect(page.getByText(/Alpaca account connection verified with a read-only request/i)).toBeVisible();
  await page.getByRole('button', { name: 'Disable account' }).click();
  await expect(page.getByRole('button', { name: 'Enable account' })).toBeVisible();
  await page.getByRole('button', { name: 'Enable account' }).click();
  await expect(page.getByRole('button', { name: 'Disable account' })).toBeVisible();

  const startButton = page.getByRole('button', { name: 'Start paper Alpaca deployment' });
  await expect(startButton).toBeEnabled();
  page.on('dialog', (dialog) => dialog.accept());
  await startButton.click();

  await expect(page.getByText('Paper runtime running: paper-e2e-001')).toBeVisible();
  expect(runtimeActionRequest).toMatchObject({
    action: 'start-paper',
    ir_id: paperRun.ir_id,
    approval_backtest_run_id: paperRun.run_id,
    account_profile_id: paperAccount.id,
  });
  expect(runtimeActionRequest).not.toHaveProperty('credentials');
});
