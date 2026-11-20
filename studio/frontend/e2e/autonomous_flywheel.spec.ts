import { expect } from '@playwright/test';
import { test } from './fixtures';

test.describe('Autonomous Quant Research & Deployment Flywheel', () => {
  test('Agent Closed-Loop: Optimize -> Promote -> Deploy -> Monitor', async ({ page, testEnv }) => {
    await page.goto('/optimize');
    await expect(page.locator('text=Quant Optimization Workbench')).toBeVisible({ timeout: 20_000 });

    await page.evaluate(async (tid) => {
      const bridge = (window as any).__STUDIO_AGENT_BRIDGE__!;
      await bridge.dispatch('optimizerSelectSession', { session_id: `session-${tid}` });
      await bridge.dispatch('optimizerSelectPoint', { run_id: `run-optimal-${tid}` });
    }, testEnv.testId);

    await expect(page.locator('[data-testid="optimizer-run-inspector"]')).toBeVisible({ timeout: 15_000 });

    await page.evaluate(async () => {
      await (window as any).__STUDIO_AGENT_BRIDGE__!.dispatch('navigate', { route: 'deploy' });
    });
    await expect(page.locator('text=Promote to paper')).toBeVisible({ timeout: 15_000 });

    await page.evaluate(async (tid) => {
      await (window as any).__STUDIO_AGENT_BRIDGE__!.dispatch('deploySelectRun', { run_id: `run-optimal-${tid}` });
    }, testEnv.testId);

    await page.evaluate(async () => {
      await (window as any).__STUDIO_AGENT_BRIDGE__!.dispatch('navigate', { route: 'monitor' });
    });
    await expect(page.locator('text=Active deployments')).toBeVisible({ timeout: 15_000 });
  });
});
