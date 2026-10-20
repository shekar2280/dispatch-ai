import { randomUUID } from 'node:crypto';
import { test, expect } from '../support/fixtures';
import { apiBase, clinicDate, syntheticPatient, required } from '../support/environment';
import { openPersona } from '../support/persona';
test('doctor finds a real patient using name search and reload @journey', async ({ actor }) => {
    const visit = await actor.walkIn();
    await actor.page.goto('/clinic/patients');
    const search = actor.page.getByPlaceholder('Search by name, phone, or symptom...');
    await search.fill(visit.patient_name);
    await expect(actor.page.getByText(visit.patient_name, { exact: true })).toBeVisible();
    await actor.page.reload();
    await actor.page.getByPlaceholder('Search by name, phone, or symptom...').fill(visit.patient_name);
    await expect(actor.page.getByText(visit.patient_name, { exact: true })).toBeVisible();
});
test('unmatched patient search produces an empty state @journey', async ({ actor }) => {
    await actor.page.goto('/clinic/patients');
    await actor.page.getByPlaceholder('Search by name, phone, or symptom...').fill(`E2E missing ${randomUUID()}`);
    await expect(actor.page.getByText('No patients found', { exact: true })).toBeVisible();
});
test('patient service outage is visible and retry reaches the real service @fault', async ({ actor }) => {
    const pattern = `${apiBase}/api/v1/appointments/patients*`;
    await actor.page.route(pattern, route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Deliberate E2E patient outage' }) }));
    await actor.page.goto('/clinic/patients');
    await expect(actor.page.getByRole('alert').filter({ hasText: /.+/ })).toContainText('Could not load patients');
    await actor.page.unroute(pattern);
    await actor.page.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(actor.page.getByRole('alert').filter({ hasText: /.+/ })).toBeHidden();
});
test('receptionist mutation reaches doctor schedule without a manual reload @realtime', async ({ actor, browser }) => {
    const receptionist = await openPersona(browser, 'receptionist', actor);
    try {
        const visit = await receptionist.actor.walkIn();
        actor.visits.add(visit.id);
        await expect(actor.page.getByRole('link', { name: visit.patient_name, exact: true })).toBeVisible({ timeout: 30000 });
    }
    finally {
        await receptionist.context.close();
    }
});
test('action center and analytics render real clinic data @smoke', async ({ actor }) => {
    await actor.page.goto('/clinic/action-center');
    await expect(actor.page.getByRole('heading', { name: 'Action Center', exact: true })).toBeVisible();
    await actor.page.goto('/clinic/analytics');
    await expect(actor.page.getByRole('heading', { name: 'Practice Growth & Clinical Analytics', exact: true })).toBeVisible();
});
test('HTML-shaped patient names are rendered as text and cannot execute scripts @security', async ({ actor }) => {
    const person = syntheticPatient();
    const name = `${person.name} <img src=x onerror=window.__e2e_xss=1>`;
    const visit = await actor.json<{
        id: string;
        patient_name: string;
    }>('/api/v1/appointments/walkin', 'POST', {
        patient_name: name, patient_phone: person.phone, reported_age: 30, doctor_id: actor.doctorId,
        appointment_date: clinicDate(actor.timezone),
    });
    actor.visits.add(visit.id);
    await actor.page.goto('/clinic/patients');
    await actor.page.getByPlaceholder('Search by name, phone, or symptom...').fill(person.name);
    await expect(actor.page.getByText(visit.patient_name, { exact: true })).toBeVisible();
    expect(await actor.page.evaluate(() => (window as unknown as Record<string, unknown>).__e2e_xss)).toBeUndefined();
});
test('call search with no matches shows a real empty state @journey', async ({ actor }) => {
    await actor.page.goto('/clinic/calls');
    await actor.page.getByPlaceholder('Search phone, patient, notes...').fill(`E2E-no-match-${randomUUID()}`);
    await expect(actor.page.getByText('No Call Records Found', { exact: true })).toBeVisible();
});
test('missing recording and call resolution do not disclose unrelated sessions @security', async ({ actor }) => {
    expect((await actor.request(`/api/v1/calls/call-sessions/${randomUUID()}/recording`)).status()).toBe(404);
});
test('call logs reject invalid pagination and malformed dates @validation', async ({ actor }) => {
    for (const query of ['limit=0', 'limit=151', 'offset=-1', 'target_date=not-a-date', 'category=invalid']) {
        expect((await actor.request(`/api/v1/calls/daily-call-logs?${query}`)).status(), query).toBe(422);
    }
});
test('existing recorded call opens transcript and authorized waveform @recording', async ({ actor }) => {
    const callId = required('E2E_RECORDED_CALL_ID');
    const logs = await actor.json<{
        logs: {
            id: string;
            caller_phone: string;
            recording_status: string;
            full_transcript: string;
        }[];
    }>(`/api/v1/calls/daily-call-logs?limit=150&search=${encodeURIComponent(required('E2E_RECORDED_CALL_PHONE'))}`);
    const call = logs.logs.find(row => row.id === callId);
    expect(call, 'Provide a completed recorded staging call that appears within the first 150 phone-filtered rows').toBeDefined();
    expect(call!.recording_status).toBe('ready');
    expect(call!.full_transcript).toBeTruthy();
    await actor.page.goto('/clinic/calls');
    await actor.page.getByPlaceholder('Search phone, patient, notes...').fill(call!.caller_phone);
    const card = actor.page.locator('div.group').filter({ has: actor.page.locator(`button`).filter({ hasText: 'Audio' }) }).filter({ hasText: call!.caller_phone });
    expect(await card.count(), 'Use a recorded fixture with a unique caller phone on the first UI page').toBe(1);
    await card.click();
    const player = actor.page.locator('section').filter({ has: actor.page.getByRole('heading', { name: 'Recording & transcript' }) });
    const response = actor.page.waitForResponse(row => row.url().includes(`/call-sessions/${callId}/recording`));
    await player.getByRole('button', { name: 'Play recording', exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(player.getByRole('button', { name: 'Pause', exact: true })).toBeVisible();
    await player.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(player.getByRole('button', { name: 'Play recording', exact: true })).toBeVisible();
});
