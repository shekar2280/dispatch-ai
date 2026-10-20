import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { apiBase } from '../support/environment';
test.describe('Public browser smoke @smoke', () => {
    test('logged-out user is redirected to sign in when accessing clinic portal', async ({ page }) => {
        await page.goto('/clinic/schedule');
        await expect(page).toHaveURL(/\/login(?:\?|$)/);
        await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible();
        await expect(page.getByLabel('Email address')).toBeVisible();
        await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
    });
    test('login page rejects submission with empty credentials', async ({ page }) => {
        await page.goto('/login');
        await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'Sign in' }).click();
        await expect(page).toHaveURL(/\/login(?:\?|$)/);
    });
    test('malformed email cannot submit an authentication request @validation', async ({ page }) => {
        await page.goto('/login');
        await page.getByLabel('Email address').fill('not-an-email');
        await page.getByLabel('Password', { exact: true }).fill('intentionally-invalid-input');
        let requests = 0;
        page.on('request', request => { if (request.url().includes('/auth/v1/token'))
            requests++; });
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        expect(requests).toBe(0);
        await expect(page).toHaveURL(/\/login(?:\?|$)/);
    });
    test('password visibility toggle changes display without changing the password @validation', async ({ page }) => {
        await page.goto('/login');
        const password = page.getByLabel('Password', { exact: true });
        await password.fill('visibility-input-only');
        await expect(password).toHaveAttribute('type', 'password');
        await page.getByRole('button', { name: 'Show password', exact: true }).click();
        await expect(password).toHaveAttribute('type', 'text');
        await expect(password).toHaveValue('visibility-input-only');
        await page.getByRole('button', { name: 'Hide password', exact: true }).click();
        await expect(password).toHaveAttribute('type', 'password');
    });
    test('signup incomplete account details cannot advance to clinic registration @validation', async ({ page }) => {
        await page.goto('/signup');
        await expect(page.getByRole('heading', { name: 'Create account', exact: true })).toBeVisible();
        await page.locator('button[type="submit"]').click();
        await expect(page.getByRole('heading', { name: 'Create account', exact: true })).toBeVisible();
        await expect(page.getByRole('heading', { name: 'Clinic details', exact: true })).toBeHidden();
    });
    test('login transport failure is visible and does not create an authenticated session @fault', async ({ page }) => {
        await page.route('**/auth/v1/token*', route => route.abort('connectionrefused'));
        await page.goto('/login');
        await page.getByLabel('Email address').fill('negative-login@example.invalid');
        await page.getByLabel('Password', { exact: true }).fill('intentionally-invalid-input');
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        await expect(page.getByRole('alert').filter({ hasText: /.+/ })).toBeVisible();
        await expect(page).toHaveURL(/\/login(?:\?|$)/);
    });
    test('landing page offers a working sign-in path', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('h1')).toBeVisible();
        const signIn = page.locator('a[href="/login"]').first();
        await expect(signIn).toBeVisible();
        if (process.env.SAVE_PUBLIC_SCREENSHOTS === '1') {
            const directory = path.resolve(__dirname, '../../../../assets/screenshots');
            await mkdir(directory, { recursive: true });
            await page.screenshot({ path: path.join(directory, 'landing.png'), fullPage: false, animations: 'disabled' });
        }
        await signIn.click();
        await expect(page).toHaveURL(/\/login$/);
    });
    test('sign-in remains usable on a mobile viewport with security headers', async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        const response = await page.goto('/login');
        expect(response?.headers()['x-content-type-options']).toBe('nosniff');
        expect(response?.headers()['x-frame-options']).toBe('DENY');
        await expect(page.getByLabel('Email address')).toBeVisible();
        await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        if (process.env.SAVE_PUBLIC_SCREENSHOTS === '1') {
            const directory = path.resolve(__dirname, '../../../../assets/screenshots');
            await mkdir(directory, { recursive: true });
            await page.screenshot({ path: path.join(directory, 'login-mobile.png'), fullPage: true });
        }
    });
});
for (const path of ['/api/v1/appointments/', '/api/v1/appointments/queue', '/api/v1/patients/',
    '/api/v1/clinic/dashboard/live', '/api/v1/calls/daily-call-logs', '/api/v1/clinic/revenue', '/api/v1/clinic/analytics', '/api/v1/org/me']) {
    test(`anonymous API request is denied: ${path} @security`, async ({ request }) => {
        expect((await request.get(`${apiBase}/health`)).status()).toBe(200);
        expect((await request.get(`${apiBase}${path}`)).status()).toBe(401);
    });
}
for (const alias of ['calls', 'voice', 'telephony']) {
    test(`anonymous ${alias} token minting is denied @security`, async ({ request }) => {
        const response = await request.post(`${apiBase}/api/v1/${alias}/token`, { data: { org_id: randomUUID() } });
        expect(response.status()).toBe(401);
    });
}
test('unsigned Twilio webhook cannot enter the telephony pipeline @security', async ({ request }) => {
    const response = await request.post(`${apiBase}/api/v1/telephony/twilio/inbound`, {
        form: { From: '+12025550123', To: '+12025550124', CallSid: 'unsigned-e2e-input' },
    });
    expect(response.status()).toBe(403);
});
test('anonymous organization WebSocket cannot join or receive data @security', async ({ page, request }) => {
    expect((await request.get(`${apiBase}/health`)).status()).toBe(200);
    await page.goto('/login');
    const result = await page.evaluate((url) => new Promise<{
        opened: boolean;
        messages: number;
    }>((resolve, reject) => {
        const socket = new WebSocket(url);
        let opened = false;
        let messages = 0;
        const timer = setTimeout(() => { socket.close(); reject(new Error('Unauthorized WebSocket did not reject its handshake')); }, 10000);
        socket.onopen = () => { opened = true; socket.close(); };
        socket.onmessage = () => messages++;
        socket.onclose = () => { clearTimeout(timer); resolve({ opened, messages }); };
    }), `${apiBase.replace(/^http/, 'ws')}/api/v1/ws/clinic/${randomUUID()}`);
    expect(result).toEqual({ opened: false, messages: 0 });
});
