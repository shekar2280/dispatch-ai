import { test, expect } from '../support/fixtures';
import { apiBase, required } from '../support/environment';
import { prepareScheduledBooking } from '../support/booking';
for (const status of [401, 403, 429, 500, 502, 503]) {
    test(`call history reports HTTP ${status} and retry recovers @fault`, async ({ actor }) => {
        const pattern = `${apiBase}/api/v1/voice/daily-call-logs*`;
        await actor.page.route(pattern, route => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ detail: `E2E deliberate HTTP ${status}` }) }));
        await actor.page.goto('/clinic/calls');
        await expect(actor.page.getByText(`E2E deliberate HTTP ${status}`, { exact: true })).toBeVisible();
        await actor.page.unroute(pattern);
        const response = actor.page.waitForResponse(row => row.url().includes('/api/v1/voice/daily-call-logs') && row.status() === 200);
        await actor.page.getByRole('button', { name: 'Retry', exact: true }).click();
        await response;
        await expect(actor.page.getByText(`E2E deliberate HTTP ${status}`, { exact: true })).toBeHidden();
    });
}
for (const failure of ['connectionrefused', 'connectionreset', 'timedout', 'namenotresolved', 'internetdisconnected', 'addressunreachable', 'blockedbyclient', 'failed']) {
    test(`call history exposes ${failure} rather than a false empty success @fault`, async ({ actor }) => {
        const pattern = `${apiBase}/api/v1/voice/daily-call-logs*`;
        await actor.page.route(pattern, route => route.abort(failure));
        await actor.page.goto('/clinic/calls');
        await expect(actor.page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
        await expect(actor.page.getByText('No Call Records Found', { exact: true })).toBeHidden();
        await actor.page.unroute(pattern);
        await actor.page.getByRole('button', { name: 'Retry', exact: true }).click();
        await expect(actor.page.getByRole('button', { name: 'Retry', exact: true })).toBeHidden();
    });
}
for (const status of [409, 422, 429, 500, 503]) {
    test(`booking HTTP ${status} preserves input and does not claim success @fault`, async ({ actor }) => {
        const { form, patient } = await prepareScheduledBooking(actor);
        const pattern = `${apiBase}/api/v1/appointments/book`;
        await actor.page.route(pattern, route => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ detail: `E2E booking failure ${status}` }) }));
        await form.getByRole('button', { name: 'Book appointment', exact: true }).click();
        await expect(form.getByRole('alert').filter({ hasText: `E2E booking failure ${status}` })).toBeVisible();
        await expect(form.getByLabel('Patient name', { exact: true })).toHaveValue(patient.name);
        expect((await actor.json<{
            patient_name: string;
        }[]>('/api/v1/appointments/')).some(row => row.patient_name === patient.name)).toBe(false);
    });
}
test('pending booking disables repeat submission and commits only once @fault', async ({ actor }) => {
    const { form, patient } = await prepareScheduledBooking(actor);
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    let requests = 0;
    await actor.page.route(`${apiBase}/api/v1/appointments/book`, async (route) => {
        requests++;
        await gate;
        await route.continue();
    });
    try {
        await form.getByRole('button', { name: 'Book appointment', exact: true }).click();
        await expect(form.getByRole('button', { name: 'Saving…', exact: true })).toBeDisabled();
        expect(requests).toBe(1);
        const response = actor.page.waitForResponse(row => row.url().endsWith('/api/v1/appointments/book') && row.request().method() === 'POST');
        release();
        const result = await response;
        expect(result.status()).toBe(201);
        const visit = await result.json();
        actor.visits.add(visit.id);
        expect((await actor.json<{
            patient_name: string;
        }[]>('/api/v1/appointments/')).filter(row => row.patient_name === patient.name)).toHaveLength(1);
    }
    finally {
        release();
    }
});
test('malformed JSON is reported as an error, without a fabricated call history @fault', async ({ actor }) => {
    await actor.page.route(`${apiBase}/api/v1/voice/daily-call-logs*`, route => route.fulfill({ status: 200, contentType: 'application/json', body: '{broken-json' }));
    await actor.page.goto('/clinic/calls');
    await expect(actor.page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
    await expect(actor.page.getByText('No Call Records Found', { exact: true })).toBeHidden();
});
test('proxy HTML error page remains a recoverable call-history error @fault', async ({ actor }) => {
    await actor.page.route(`${apiBase}/api/v1/voice/daily-call-logs*`, route => route.fulfill({ status: 502, contentType: 'text/html', body: '<html><body>Upstream unavailable</body></html>' }));
    await actor.page.goto('/clinic/calls');
    await expect(actor.page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
    await expect(actor.page.getByText('No Call Records Found', { exact: true })).toBeHidden();
});
test('lost booking response and retry cannot duplicate a committed visit @fault', async ({ actor }) => {
    const { form, patient } = await prepareScheduledBooking(actor);
    const pattern = `${apiBase}/api/v1/appointments/book`;
    await actor.page.route(pattern, async (route) => {
        const result = await route.fetch();
        expect(result.status()).toBe(201);
        const visit = await result.json();
        actor.visits.add(visit.id);
        await route.abort('connectionreset');
    });
    await form.getByRole('button', { name: 'Book appointment', exact: true }).click();
    await expect(form.getByRole('alert')).toBeVisible();
    await actor.page.unroute(pattern);
    const retry = actor.page.waitForResponse(response => response.url().endsWith('/api/v1/appointments/book') && response.request().method() === 'POST');
    await form.getByRole('button', { name: 'Book appointment', exact: true }).click();
    expect((await retry).status()).toBe(409);
    expect((await actor.json<{
        patient_name: string;
    }[]>('/api/v1/appointments/')).filter(row => row.patient_name === patient.name)).toHaveLength(1);
});
for (const status of [401, 403, 402, 429, 500, 503]) {
    test(`simulator HTTP ${status} produces a recoverable call notice @fault`, async ({ actor }) => {
        await actor.page.getByRole('button', { name: /Voice AI Simulator|Test AI/ }).click();
        await actor.page.getByLabel('Phone number', { exact: true }).fill(required('E2E_PATIENT_PHONE'));
        await actor.page.route(`${apiBase}/api/v1/voice/simulator/start`, route => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ detail: `E2E token failure ${status}` }) }));
        await actor.page.getByRole('button', { name: 'Call Clinic Reception', exact: true }).click();
        await expect(actor.page.getByText('Call Notice', { exact: true })).toBeVisible();
        await expect(actor.page.getByRole('button', { name: 'Retry Call', exact: true })).toBeVisible();
        await expect(actor.page.locator('audio[id^="livekit-audio-"]')).toHaveCount(0);
    });
}
test('simulator prevents a call without a usable contact number @validation', async ({ actor }) => {
    await actor.page.getByRole('button', { name: /Voice AI Simulator|Test AI/ }).click();
    await actor.page.getByLabel('Phone number', { exact: true }).fill('123');
    await expect(actor.page.getByRole('button', { name: 'Call Clinic Reception', exact: true })).toBeDisabled();
});
test('simulator token connection failure does not pretend a call connected @fault', async ({ actor }) => {
    await actor.page.getByRole('button', { name: /Voice AI Simulator|Test AI/ }).click();
    await actor.page.getByLabel('Phone number', { exact: true }).fill(required('E2E_PATIENT_PHONE'));
    await actor.page.route(`${apiBase}/api/v1/voice/simulator/start`, route => route.abort('connectionrefused'));
    await actor.page.getByRole('button', { name: 'Call Clinic Reception', exact: true }).click();
    await expect(actor.page.getByText('Call Notice', { exact: true })).toBeVisible();
    await expect(actor.page.locator('audio[id^="livekit-audio-"]')).toHaveCount(0);
});
