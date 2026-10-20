import { test, expect, type ClinicActor } from '../support/fixtures';
import { randomUUID } from 'node:crypto';
test('doctor starts and completes a visit through the consultation UI @journey', async ({ actor }) => {
    const visit = await actor.walkIn();
    await actor.json(`/api/v1/appointments/${visit.id}/call`, 'POST');
    await actor.page.goto('/clinic');
    await expect(actor.page.getByRole('heading', { name: visit.patient_name, exact: true })).toBeVisible();
    await actor.page.getByRole('button', { name: 'Start Consultation', exact: true }).click();
    await expect(actor.page.getByRole('button', { name: 'End Consultation', exact: true })).toBeVisible();
    await actor.page.getByPlaceholder("Doctor's clinical notes, dosages, follow-up instructions, or diet advice...").fill('E2E note saved through the actual browser');
    await actor.page.getByRole('button', { name: 'End Consultation', exact: true }).click();
    await expect(actor.page.getByText(`Complete the consultation for ${visit.patient_name}?`, { exact: false })).toBeVisible();
    await actor.page.getByRole('button', { name: 'Complete & Call Next', exact: true }).click();
    await expect.poll(async () => (await actor.readVisit(visit.id)).status).toBe('completed');
    expect((await actor.readVisit(visit.id)).doctor_notes).toBe('E2E note saved through the actual browser');
});
test('doctor completes consultation with persistent notes and encounter timestamps @journey', async ({ actor }) => {
    const visit = await actor.walkIn();
    await actor.page.goto('/clinic');
    await expect(actor.page.getByRole('heading', { name: 'Consultation Desk', exact: true })).toBeVisible();
    await actor.json(`/api/v1/appointments/${visit.id}/call`, 'POST');
    const started = await actor.json<{
        status: string;
        consultation_started_at: string;
    }>(`/api/v1/appointments/${visit.id}/start-consultation`, 'POST');
    expect(started.status).toBe('in_progress');
    expect(started.consultation_started_at).toBeTruthy();
    await actor.json(`/api/v1/appointments/${visit.id}/notes`, 'POST', { doctor_notes: 'Synthetic E2E consultation note', recent_diagnosis: 'E2E verification' });
    const done = await actor.json<{
        status: string;
        consultation_ended_at: string;
        actual_duration_seconds: number;
    }>(`/api/v1/appointments/${visit.id}/complete`, 'POST');
    expect(done.status).toBe('completed');
    expect(done.consultation_ended_at).toBeTruthy();
    expect(done.actual_duration_seconds).toBeGreaterThanOrEqual(0);
    expect((await actor.readVisit(visit.id)).doctor_notes).toBe('Synthetic E2E consultation note');
});
test('completing an unstarted visit is rejected without altering its state @validation', async ({ actor }) => {
    const visit = await actor.walkIn();
    expect((await actor.request(`/api/v1/appointments/${visit.id}/complete`, 'POST')).status()).toBe(409);
    expect((await actor.readVisit(visit.id)).status).toBe('arrived');
});
test('completed visit cannot be billed before consultation completion @validation', async ({ actor }) => {
    const visit = await actor.walkIn();
    expect((await actor.request(`/api/v1/appointments/${visit.id}/collect-fee`, 'POST', {
        idempotency_key: `e2e-premature-${visit.id}`, payment_status: 'paid', payment_method: 'cash', amount_received: 1,
    })).status()).toBe(409);
});
for (const [path, heading] of [['/clinic/patients', 'Patients'], ['/clinic/calls', 'Call History'], ['/clinic/schedule', 'Clinic Schedule']]) {
    test(`doctor can open ${path} without runtime failures @smoke`, async ({ actor }) => {
        await actor.page.goto(path);
        await expect(actor.page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    });
}
async function completedVisit(actor: ClinicActor) {
    const visit = await actor.walkIn();
    await actor.json(`/api/v1/appointments/${visit.id}/call`, 'POST');
    await actor.json(`/api/v1/appointments/${visit.id}/start-consultation`, 'POST');
    await actor.json(`/api/v1/appointments/${visit.id}/complete`, 'POST');
    return visit;
}
test('partial cash and final UPI payments preserve receipts and cannot duplicate @journey', async ({ actor }) => {
    const visit = await completedVisit(actor);
    const amount = Number(visit.fee);
    expect(amount, 'Configure a positive staging consultation fee').toBeGreaterThan(1);
    const partial = Math.floor(amount / 2);
    const first = { idempotency_key: randomUUID(), payment_status: 'paid', payment_method: 'cash', amount_received: partial };
    await actor.json(`/api/v1/appointments/${visit.id}/collect-fee`, 'POST', first);
    await actor.json(`/api/v1/appointments/${visit.id}/collect-fee`, 'POST', first);
    const receipts = await actor.json<{
        amount: number;
    }[]>(`/api/v1/clinic/${visit.id}/payments`);
    expect(receipts).toHaveLength(1);
    expect(Number(receipts[0].amount)).toBe(partial);
    await actor.json(`/api/v1/appointments/${visit.id}/collect-fee`, 'POST', {
        idempotency_key: randomUUID(), payment_status: 'paid', payment_method: 'upi', amount_received: amount - partial,
    });
    const settled = await actor.readVisit(visit.id);
    expect(settled.payment_status).toBe('paid');
    const all = await actor.json<{
        amount: number;
    }[]>(`/api/v1/clinic/${visit.id}/payments`);
    expect(all).toHaveLength(2);
    expect(all.reduce((sum, row) => sum + Number(row.amount), 0)).toBe(amount);
    await actor.page.goto('/clinic/revenue');
    await expect(actor.page.getByPlaceholder('Search by patient, phone, date...')).toBeVisible();
});
test('overpayment and negative payment cannot create receipts @validation', async ({ actor }) => {
    const visit = await completedVisit(actor);
    for (const amount of [-1, 0, Number(visit.fee) + 1]) {
        const response = await actor.request(`/api/v1/appointments/${visit.id}/collect-fee`, 'POST', {
            idempotency_key: randomUUID(), payment_status: 'paid', payment_method: 'cash', amount_received: amount,
        });
        expect(response.status(), `Payment ${amount} must be rejected`).toBe(422);
    }
    expect(await actor.json<unknown[]>(`/api/v1/clinic/${visit.id}/payments`)).toHaveLength(0);
});
test('sign out prevents reentry into protected pages after reload @security', async ({ page }) => {
    await page.goto('/clinic/schedule');
    await expect(page.getByRole('heading', { name: 'Clinic Schedule', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Account menu', exact: true }).click();
    await page.getByRole('button', { name: /Sign out/i }).click();
    await expect(page).toHaveURL(/\/login(?:\?|$)/);
    await page.goto('/clinic/settings');
    await expect(page).toHaveURL(/\/login(?:\?|$)/);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible();
});
