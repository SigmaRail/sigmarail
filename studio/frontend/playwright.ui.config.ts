import { defineConfig, devices } from '@playwright/test';

/**
 * Opt-in, API-mocked browser smoke tests. Deliberately separate from the
 * ClickHouse-backed legacy E2E config, unit tests, and CI.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: 'paper_runtime_ui.spec.ts',
  timeout: 30_000,
  workers: 1,
  retries: 0,
  outputDir: 'test-results-ui',
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-ui-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium-ui', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5174',
    cwd: '.',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
