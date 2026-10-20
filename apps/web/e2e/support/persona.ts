import { expect, type Browser } from '@playwright/test';
import { ClinicActor } from './fixtures';
import { apiBase } from './environment';

export async function openPersona(browser: Browser, role: string, actor: ClinicActor) {
  const context = await browser.newContext({ storageState: `playwright/.auth/${role}.json`, baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000' });
  try {
    const page = await context.newPage();
    let token = '';
    page.on('request', request => {
      if (request.url().startsWith(`${apiBase}/api/v1/`)) {
        const authorization = request.headers().authorization;
        if (authorization?.startsWith('Bearer ')) token = authorization.slice(7);
      }
    });
    await page.goto('/clinic/schedule');
    await expect(page.getByRole('heading', { name: 'Clinic Schedule', exact: true })).toBeVisible();
    await expect.poll(() => Boolean(token)).toBe(true);
    return { context, actor: new ClinicActor(page, token, actor.orgId, actor.doctorId, actor.timezone) };
  } catch (error) { await context.close(); throw error; }
}
