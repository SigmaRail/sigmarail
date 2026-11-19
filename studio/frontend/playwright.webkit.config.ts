import { defineConfig } from '@playwright/test';
import workbenchConfig from './playwright.workbench.config';

/** WebKit viewport checks for iOS-like behavior; this is not a physical iPhone. */
export default defineConfig({
  ...workbenchConfig,
  use: {
    ...workbenchConfig.use,
    browserName: 'webkit',
  },
});
