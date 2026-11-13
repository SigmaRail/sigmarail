import { test as base } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const studioRoot = path.resolve(here, '../..');
const python = path.join(studioRoot, '.venv/bin/python');

export const test = base.extend<{ testEnv: { testId: string } }>({
  testEnv: async ({}, use) => {
    const testId = `e2e-${Date.now()}`;
    const env = {
      ...process.env,
      PYTHONPATH: [path.resolve(studioRoot, '../src'), studioRoot, process.env.PYTHONPATH]
        .filter(Boolean)
        .join(path.delimiter),
    };
    execSync(`${python} scripts/seed_e2e_fixtures.py --test-id ${testId}`, {
      cwd: studioRoot,
      env,
      stdio: 'inherit',
    });
    await use({ testId });
    try {
      execSync(`${python} scripts/teardown_e2e_fixtures.py --test-id ${testId}`, {
        cwd: studioRoot,
        env,
        stdio: 'inherit',
      });
    } catch (err) {
      console.warn('teardown failed (leaving fixture rows):', err);
    }
  },
});
