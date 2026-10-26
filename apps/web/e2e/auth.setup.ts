import { test as setup, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const roles = ['doctor', 'receptionist', 'admin', 'tenant_b'] as const;

for (const role of roles) {
  setup(`authenticate ${role}`, async ({ page }) => {
    const prefix = `E2E_${role.toUpperCase()}`;
    const email = process.env[`${prefix}_EMAIL`];
    const password = process.env[`${prefix}_PASSWORD`];

    if (!email || !password) {
      throw new Error(`Missing credentials for ${role}`);
    }

    await page.goto('/login');
    await page.getByLabel('Email address').fill(email);
    await page.getByLabel('Password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();

    await expect(page).toHaveURL(/\/clinic(?:\/|$)/, { timeout: 45000 });
    await expect(page.getByRole('heading', { name: /^(Clinic Schedule|Consultation Desk)$/ })).toBeVisible({ timeout: 30000 });

    mkdirSync('playwright/.auth', { recursive: true });
    await page.context().storageState({
      path: `playwright/.auth/${role}.json`,
    });
  });
}
