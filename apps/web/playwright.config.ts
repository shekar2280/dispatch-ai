import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { existsSync } from 'node:fs';

const environmentFile = path.resolve(__dirname, '.env.e2e');
if (existsSync(environmentFile)) process.loadEnvFile(environmentFile);

const setupRoles = ['doctor', 'receptionist', 'admin', 'tenant_b'];
const setupProjects = setupRoles.map(role => ({
  name: `setup-${role}`,
  testMatch: '**/auth.setup.ts',
  grep: new RegExp(`authenticate ${role}$`),
  use: { trace: 'retain-on-failure' as const, screenshot: 'only-on-failure' as const, video: 'retain-on-failure' as const },
}));

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
    ['junit', { outputFile: 'test-results/results.xml' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'public',
      testMatch: '**/public/**/*.spec.ts',
      use: { ...devices['Desktop Chrome'] },
    },
    ...setupProjects,
    {
      name: 'doctor',
      testMatch: '**/doctor/**/*.spec.ts',
      dependencies: ['setup-doctor', 'setup-receptionist'],
      grepInvert: /@recording/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/doctor.json',
      },
    },
    {
      name: 'receptionist',
      testMatch: '**/receptionist/**/*.spec.ts',
      dependencies: ['setup-receptionist'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/receptionist.json',
      },
    },
    {
      name: 'admin',
      testMatch: '**/admin/**/*.spec.ts',
      dependencies: ['setup-admin'],
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/admin.json' },
    },
    {
      name: 'cashier', testMatch: '**/cashier/**/*.spec.ts',
      dependencies: ['setup-doctor', 'setup-receptionist'],
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/receptionist.json' },
    },
    {
      name: 'security',
      testMatch: '**/security/**/*.spec.ts',
      dependencies: ['setup-doctor', 'setup-tenant_b', 'setup-receptionist'],
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/doctor.json' },
    },
    ...(process.env.E2E_RUN_RECORDING === '1' ? [{
      name: 'recording', testMatch: '**/doctor/patients-and-calls.spec.ts', grep: /@recording/,
      dependencies: ['setup-doctor'],
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/doctor.json' },
    }] : []),
  ],
});
