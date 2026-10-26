import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/public',
  testMatch: 'auth.spec.ts',
  grep: /@smoke/,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:3100',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    reducedMotion: 'reduce',
  },
});
