import { defineConfig } from '@playwright/test';

/**
 * API-mocked E2E coverage for the SigmaRail workbench in its application shell.
 * It runs the production bundle and never contacts ClickHouse,
 * production APIs, Django, PostgreSQL, LEAN, or a brokerage.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: 'workbench_responsive.spec.ts',
  timeout: 45_000,
  workers: 1,
  retries: 0,
  outputDir: 'test-results-workbench',
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4302',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  webServer: {
    command:
      '../../node_modules/.bin/vite -c vite.config.mts build && ../../node_modules/.bin/vite preview --host 127.0.0.1 --port 4302',
    cwd: '../packages/webapp',
    url: 'http://127.0.0.1:4302/en/auth/login',
    // Keep this branch's browser checks tied to its own preview build. Reusing
    // a listener left on the port can make a stale Studio UI look like this
    // worktree and give misleading route/render results.
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
