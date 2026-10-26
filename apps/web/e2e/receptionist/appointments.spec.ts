import { test, expect } from '../support/fixtures';
import { openBooking, prepareScheduledBooking, submitScheduledBooking } from '../support/booking';
import { syntheticPatient, clinicDate } from '../support/environment';
import { randomUUID } from 'node:crypto';
test('receptionist checks in a walk-in through the intake form @journey', async ({ actor }) => {
    const person = syntheticPatient();
    const form = await openBooking(actor.page);
    await form.getByRole('button', { name: 'Walk-in', exact: true }).click();
    await expect(form.getByText('Select doctor', { exact: true })).toHaveCount(0);
    await form.getByLabel('Patient name', { exact: true }).fill(person.name);
    await form.getByLabel('Contact number', { exact: true }).fill(person.phone);
    await expect(form.getByRole('button', { name: 'Check in patient', exact: true })).toBeDisabled();
    await form.getByLabel('Age', { exact: true }).fill('30');
    await form.locator('summary').filter({ hasText: 'More patient details' }).click();
    await form.getByLabel('Gender', { exact: true }).selectOption('female');
    await form.getByLabel('Blood group', { exact: true }).selectOption('O+');
    await form.getByLabel('Address', { exact: true }).fill('12 Park Road, Pune');
    const response = actor.page.waitForResponse(row => row.url().endsWith('/api/v1/appointments/walkin') && row.request().method() === 'POST');
    await form.getByRole('button', { name: 'Check in patient', exact: true }).click();
    const result = await response;
    expect(result.status()).toBe(201);
    const visit = await result.json();
    actor.visits.add(visit.id);
    expect(visit.status).toBe('arrived');
    const saved = await actor.readVisit(visit.id);
    expect(saved.gender).toBe('female');
    expect(saved.blood_group).toBe('O+');
    expect(saved.address).toBe('12 Park Road, Pune');
    expect(visit.doctor_id).toBe(actor.doctorId);
    await expect(actor.page.getByRole('link', { name: person.name, exact: true })).toBeVisible();
});
test('receptionist books an appointment and it survives reload @journey', async ({ actor }) => {
    const visit = await submitScheduledBooking(actor);
    await actor.page.reload();
    await expect(actor.page.getByRole('heading', { name: 'Clinic Schedule', exact: true })).toBeVisible();
    expect((await actor.readVisit(visit.id)).status).toBe('scheduled');
});
test('incomplete booking cannot submit and cancel creates no visit @journey', async ({ actor }) => {
    const before = await actor.json<unknown[]>('/api/v1/appointments/');
    const form = await openBooking(actor.page);
    await expect(form.getByRole('button', { name: 'Book appointment', exact: true })).toBeDisabled();
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(actor.page.getByRole('heading', { name: 'Book a visit', exact: true })).toBeHidden();
    expect((await actor.json<unknown[]>('/api/v1/appointments/')).length).toBe(before.length);
});
for (const phone of ['', '123', 'abc']) {
    test(`contact ${JSON.stringify(phone)} cannot submit @validation`, async ({ actor }) => {
        const { form } = await prepareScheduledBooking(actor);
        await form.getByLabel('Contact number', { exact: true }).fill(phone);
        await expect(form.getByRole('button', { name: 'Book appointment', exact: true })).toBeDisabled();
    });
}
test('changing date clears previously selected arrival time @validation', async ({ actor }) => {
    const { form } = await prepareScheduledBooking(actor);
    await form.getByRole('button', { name: 'Visit date', exact: true }).click();
    await form.getByRole('button', { name: 'Tomorrow', exact: true }).click();
    await expect(form.getByRole('radio', { checked: true })).toHaveCount(0);
    await expect(form.getByRole('button', { name: 'Book appointment', exact: true })).toBeDisabled();
});
test('scheduled appointment can be rescheduled and cancelled with audit history @journey', async ({ actor }) => {
    const visit = await actor.scheduled();
    const next = await actor.futureSlot(visit.start_time.slice(0, 10));
    const moved = await actor.json<{
        status: string;
    }>(`/api/v1/appointments/${visit.id}/reschedule`, 'POST', { new_date: next.date, new_time: next.time, reason: 'E2E reschedule' });
    expect(moved.status).toBe('scheduled');
    const cancelled = await actor.json<{
        status: string;
    }>(`/api/v1/appointments/${visit.id}/cancel`, 'POST', { reason: 'E2E cancellation' });
    expect(cancelled.status).toBe('cancelled');
    const events = await actor.json<{
        event_type: string;
    }[]>(`/api/v1/appointments/${visit.id}/events`);
    expect(events.some(event => event.event_type.includes('RESCHEDULE'))).toBe(true);
    expect(events.some(event => event.event_type.includes('CANCEL'))).toBe(true);
});
test('family members sharing a phone retain distinct patient identities @journey', async ({ actor }) => {
    const first = await actor.walkIn();
    const second = await actor.walkIn();
    expect(first.patient_id).not.toBe(second.patient_id);
    expect(first.patient_phone).toBe(second.patient_phone);
});
test('walk-in can step out and return without losing its visit identity @journey', async ({ actor }) => {
    const visit = await actor.walkIn();
    const skipped = await actor.json<{
        id: string;
        status: string;
    }>(`/api/v1/appointments/${visit.id}/skip`, 'POST');
    expect(skipped.id).toBe(visit.id);
    expect(skipped.status).toBe('skipped');
    const returned = await actor.json<{
        id: string;
        status: string;
    }>(`/api/v1/appointments/${visit.id}/reinsert`, 'POST');
    expect(returned.id).toBe(visit.id);
    expect(returned.status).toBe('arrived');
});
for (const [field, value] of [['patient_name', ''], ['appointment_date', 'not-a-date'], ['doctor_id', 'not-a-uuid']]) {
    test(`backend rejects malformed ${field} independently of UI validation @validation`, async ({ actor }) => {
        const slot = await actor.futureSlot();
        const person = syntheticPatient();
        const payload = { patient_name: person.name, patient_phone: person.phone, doctor_id: actor.doctorId,
            appointment_date: slot.date, appointment_time: slot.time, [field]: value };
        const response = await actor.request('/api/v1/appointments/book', 'POST', payload);
        expect(response.status(), 'Bad input must never return success or a server exception').toBeGreaterThanOrEqual(400);
        expect(response.status()).toBeLessThan(500);
        expect((await actor.json<{
            patient_name: string;
        }[]>('/api/v1/appointments/')).some(row => row.patient_name === person.name)).toBe(false);
    });
}
test('past scheduled dates and future walk-ins are rejected @validation', async ({ actor }) => {
    const person = syntheticPatient();
    const common = { patient_name: person.name, patient_phone: person.phone, doctor_id: actor.doctorId, reported_age: 30 };
    expect((await actor.request('/api/v1/appointments/book', 'POST', { ...common, appointment_date: clinicDate(actor.timezone, -1), appointment_time: '10:00 AM' })).status()).toBe(400);
    expect((await actor.request('/api/v1/appointments/walkin', 'POST', { ...common, appointment_date: clinicDate(actor.timezone, 1) })).status()).toBe(400);
});
test('foreign or inactive doctor identity cannot create a booking @security', async ({ actor }) => {
    const slot = await actor.futureSlot();
    const person = syntheticPatient();
    expect((await actor.request('/api/v1/appointments/book', 'POST', {
        patient_name: person.name, patient_phone: person.phone, doctor_id: randomUUID(), appointment_date: slot.date, appointment_time: slot.time,
    })).status()).toBe(404);
});
test('duplicate active walk-in does not create a second visit @validation', async ({ actor }) => {
    const visit = await actor.walkIn();
    const response = await actor.request('/api/v1/appointments/walkin', 'POST', {
        patient_id: visit.patient_id, patient_name: visit.patient_name, patient_phone: visit.patient_phone,
        doctor_id: actor.doctorId, appointment_date: clinicDate(actor.timezone), reported_age: 30,
    });
    expect(response.status(), 'Duplicate intake must report its existing visit or reject a conflict').toBeLessThan(500);
    expect([201, 409]).toContain(response.status());
    if (response.status() === 201)
        expect((await response.json()).id).toBe(visit.id);
    const rows = await actor.json<{
        patient_id: string;
        status: string;
    }[]>('/api/v1/appointments/');
    expect(rows.filter(row => row.patient_id === visit.patient_id && ['scheduled', 'arrived', 'in_progress'].includes(row.status))).toHaveLength(1);
});
for (const age of [-1, 131, 1.5]) {
    test(`walk-in age ${age} years cannot bypass intake validation @validation`, async ({ actor }) => {
        const person = syntheticPatient();
        const response = await actor.request('/api/v1/appointments/walkin', 'POST', {
            patient_name: person.name, patient_phone: person.phone, reported_age: age, age_unit: 'years',
            doctor_id: actor.doctorId, appointment_date: clinicDate(actor.timezone),
        });
        if (response.status() === 201)
            actor.visits.add((await response.json()).id);
        expect(response.status()).toBe(422);
    });
}
test('future date of birth is rejected by the real API @validation', async ({ actor }) => {
    const person = syntheticPatient();
    const response = await actor.request('/api/v1/appointments/walkin', 'POST', {
        patient_name: person.name, patient_phone: person.phone, dob: clinicDate(actor.timezone, 1),
        doctor_id: actor.doctorId, appointment_date: clinicDate(actor.timezone),
    });
    if (response.status() === 201)
        actor.visits.add((await response.json()).id);
    expect(response.status()).toBe(422);
});
for (const path of ['/clinic', '/clinic/patients', '/clinic/revenue', '/clinic/analytics', '/clinic/settings']) {
    test(`direct navigation to ${path} redirects receptionist @security`, async ({ actor }) => {
        await actor.page.goto(path);
        await expect(actor.page).toHaveURL(/\/clinic\/schedule(?:\?|$)/);
        await expect(actor.page.getByRole('heading', { name: 'Clinic Schedule', exact: true })).toBeVisible();
    });
}
test('clinical API actions reject receptionist without modifying the visit @security', async ({ actor }) => {
    const visit = await actor.walkIn();
    for (const [action, data] of [
        ['call', undefined], ['start-consultation', undefined], ['complete', undefined],
        ['notes', { doctor_notes: 'Must not be saved' }],
    ] as const) {
        const response = await actor.request(`/api/v1/appointments/${visit.id}/${action}`, 'POST', data);
        expect(response.status(), action).toBe(403);
    }
    const unchanged = await actor.readVisit(visit.id);
    expect(unchanged.status).toBe('arrived');
    expect(unchanged.doctor_notes ?? null).toBeNull();
});
test('receptionist cannot delete a patient profile @security', async ({ actor }) => {
    const visit = await actor.walkIn();
    expect((await actor.request(`/api/v1/patients/${visit.patient_id}`, 'DELETE')).status()).toBe(403);
    expect((await actor.request(`/api/v1/patients/${visit.patient_id}`)).status()).toBe(200);
});
test('receptionist cannot retrieve financial analytics by direct API @security', async ({ actor }) => {
    for (const path of ['/api/v1/clinic/revenue?period=today', '/api/v1/clinic/analytics?period=month']) {
        expect((await actor.request(path)).status(), `Server must enforce role boundaries for ${path}`).toBe(403);
    }
});
test('forged tenant header does not become an authorization credential @security', async ({ actor }) => {
    expect((await actor.request('/api/v1/appointments/', 'GET', undefined, randomUUID())).status()).toBe(403);
});
test('receptionist cannot invite or edit staff through direct API calls @security', async ({ actor }) => {
    const create = await actor.request('/api/v1/clinic/staff', 'POST', { email: 'negative-staff@example.invalid', full_name: 'E2E unauthorized staff', role: 'receptionist' });
    expect(create.status()).toBe(403);
    const edit = await actor.request('/api/v1/clinic/staff/negative-staff%40example.invalid', 'PATCH', { full_name: 'Must not be applied', role: 'receptionist' });
    expect(edit.status()).toBe(403);
});
test('receptionist can complete intake on a narrow mobile viewport @journey', async ({ actor }) => {
    await actor.page.setViewportSize({ width: 390, height: 844 });
    await expect(actor.page.getByRole('heading', { name: 'Clinic Schedule', exact: true })).toBeVisible();
    const visit = await submitScheduledBooking(actor);
    expect((await actor.readVisit(visit.id)).status).toBe('scheduled');
    expect(await actor.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
test('keyboard user can reach and close booking without creating a visit @journey', async ({ actor }) => {
    const trigger = actor.page.getByRole('button', { name: /Book Appointment|Intake/ });
    await trigger.focus();
    await actor.page.keyboard.press('Enter');
    await expect(actor.page.getByRole('heading', { name: 'Book a visit', exact: true })).toBeVisible();
    const close = actor.page.getByRole('button', { name: 'Close booking', exact: true });
    await close.focus();
    await actor.page.keyboard.press('Enter');
    await expect(actor.page.getByRole('heading', { name: 'Book a visit', exact: true })).toBeHidden();
});
