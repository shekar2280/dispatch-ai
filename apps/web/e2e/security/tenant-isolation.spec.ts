import { test, expect, ClinicActor } from '../support/fixtures';
import { apiBase, required } from '../support/environment';

test('Clinic B cannot read or mutate a real Clinic A patient/visit @security', async ({ actor, browser }) => {
  const visit = await actor.walkIn();
  const otherOrg = required('E2E_TENANT_B_ORG_ID');
  expect(otherOrg).not.toBe(actor.orgId);
  const context = await browser.newContext({ storageState: 'playwright/.auth/tenant_b.json', baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000' });
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
    const other = new ClinicActor(page, token, otherOrg, actor.doctorId, actor.timezone);
    expect((await other.json<{ id: string }>('/api/v1/org/me')).id).toBe(otherOrg);
    expect((await other.request(`/api/v1/patients/${visit.patient_id}`)).status()).toBe(404);
    expect((await other.request(`/api/v1/appointments/${visit.id}/cancel`, 'POST', { reason: 'Cross-tenant attempt' })).status()).toBe(404);
    expect((await other.request('/api/v1/appointments/', 'GET', undefined, actor.orgId)).status()).toBe(403);
    expect((await other.request(`/api/v1/team/members/${actor.orgId}`)).status()).toBe(403);
    expect((await actor.readVisit(visit.id)).status).toBe('arrived');
  } finally { await context.close(); }
});

test('clinical history is visible to clinician and redacted for receptionist @security', async ({ actor, browser }) => {
  const visit = await actor.walkIn();
  await actor.json(`/api/v1/patients/${visit.patient_id}`, 'PUT', { medical_history: { notes: ['E2E private clinical marker'] } });
  const context = await browser.newContext({ storageState: 'playwright/.auth/receptionist.json', baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000' });
  try {
    const page = await context.newPage();
    let authorization = '';
    page.on('request', request => {
      if (request.url().startsWith(`${apiBase}/api/v1/`) && request.headers().authorization) authorization = request.headers().authorization;
    });
    await page.goto('/clinic/schedule');
    await expect.poll(() => Boolean(authorization)).toBe(true);
    const response = await page.request.get(`${apiBase}/api/v1/patients/${visit.patient_id}`, {
      headers: { Authorization: authorization, 'X-Org-Id': actor.orgId },
    });
    expect(response.status()).toBe(200);
    expect(await response.text()).not.toContain('E2E private clinical marker');
    const clinician = await actor.json<{ medical_history: unknown }>(`/api/v1/patients/${visit.patient_id}`);
    expect(JSON.stringify(clinician.medical_history)).toContain('E2E private clinical marker');
  } finally { await context.close(); }
});
