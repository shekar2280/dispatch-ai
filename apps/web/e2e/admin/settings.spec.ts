import { test, expect } from '../support/fixtures';

for (const [tab, heading] of [['profile', 'Clinic profile'], ['staff', 'Staff access'], ['schedule', 'Appointments & hours'], ['voice', 'Voice & greeting']]) {
  test(`admin opens ${tab} settings without modifying shared configuration @smoke`, async ({ actor }) => {
    await actor.page.goto(`/clinic/settings?tab=${tab}`);
    await expect(actor.page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
  });
}

test('admin sees team directory scoped to its own organization @journey', async ({ actor }) => {
  expect((await actor.request(`/api/v1/team/members/${actor.orgId}`)).status()).toBe(200);
  await actor.page.goto('/clinic/settings?tab=staff');
  await expect(actor.page.getByRole('heading', { name: 'Staff access', exact: true })).toBeVisible();
});

test('weekly day toggles retain edits until discarded @journey', async ({ actor }) => {
  await actor.page.goto('/clinic/settings?tab=schedule');
  const toggle = actor.page.getByRole('switch', { name: 'Monday appointments', exact: true });
  const sunday = actor.page.getByRole('switch', { name: 'Sunday appointments', exact: true });
  await expect(toggle).toBeVisible();
  const originalMonday = String(await toggle.isChecked());
  const originalSunday = String(await sunday.isChecked());
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked', originalMonday === 'true' ? 'false' : 'true');
  await expect(sunday).toHaveAttribute('aria-checked', originalSunday);
  await expect(actor.page.getByText('You have unsaved changes', { exact: true })).toBeVisible();
  await actor.page.getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(toggle).toHaveAttribute('aria-checked', originalMonday);
  await expect(sunday).toHaveAttribute('aria-checked', originalSunday);
});

test('admin role does not automatically grant clinician consultation privileges @security', async ({ actor }) => {
  const visit = await actor.walkIn();
  expect((await actor.request(`/api/v1/appointments/${visit.id}/start-consultation`, 'POST')).status()).toBe(403);
  expect((await actor.readVisit(visit.id)).status).toBe('arrived');
});

test('invalid staff invite is stopped before creating a member @validation', async ({ actor }) => {
  await actor.page.goto('/clinic/settings?tab=staff');
  await actor.page.getByRole('button', { name: 'Add Member', exact: true }).click();
  await expect(actor.page.getByRole('heading', { name: 'Add Team Member', exact: true })).toBeVisible();
  await actor.page.getByPlaceholder('e.g. Pooja Sharma').fill('E2E invalid invite');
  await actor.page.getByPlaceholder('receptionist@example.com').fill('not-an-email');
  let writes = 0;
  actor.page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/api/v1/clinic/staff')) writes++; });
  const form = actor.page.locator('form').filter({ has: actor.page.getByPlaceholder('receptionist@example.com') });
  await form.getByRole('button', { name: 'Add Member', exact: true }).click();
  expect(writes).toBe(0);
  await expect(actor.page.getByRole('heading', { name: 'Add Team Member', exact: true })).toBeVisible();
});
