import { test as base, expect, type APIResponse, type Page, type Request } from '@playwright/test';
import { apiBase, clinicDate, required, syntheticPatient } from './environment';

export interface Visit {
  id: string;
  patient_id: string;
  patient_name: string;
  patient_phone: string;
  status: string;
  doctor_notes?: string | null;
  fee: number;
  balance_due?: number;
  start_time: string;
  [key: string]: unknown;
}

export class ClinicActor {
  visits = new Set<string>();
  constructor(public page: Page, public token: string, public orgId: string, public doctorId: string, public timezone: string) {}

  async request(path: string, method = 'GET', data?: unknown, orgId = this.orgId): Promise<APIResponse> {
    return this.page.request.fetch(`${apiBase}${path}`, {
      method, data, headers: { Authorization: `Bearer ${this.token}`, 'X-Org-Id': orgId },
    });
  }

  async json<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
    const response = await this.request(path, method, data);
    expect(response.status(), `${method} ${path} returned ${response.status()}`).toBeLessThan(400);
    return response.json();
  }

  async futureSlot(excludeDate?: string): Promise<{ date: string; time: string }> {
    for (let offset = 7; offset < 28; offset++) {
      const date = clinicDate(this.timezone, offset);
      if (date === excludeDate) continue;
      const capacity = await this.json<{ available_slots: string[] }>(`/api/v1/appointments/arrival-options?target_date=${date}&doctor_id=${this.doctorId}`);
      if (capacity.available_slots.length) return { date, time: capacity.available_slots[0] };
    }
    throw new Error('Staging clinic has no available arrival window in the next 7–27 days. Configure its real schedule.');
  }

  async walkIn(): Promise<Visit> {
    const person = syntheticPatient();
    const visit = await this.json<Visit>('/api/v1/appointments/walkin', 'POST', {
      patient_name: person.name, patient_phone: person.phone, reported_age: 30, age_unit: 'years',
      appointment_date: clinicDate(this.timezone), doctor_id: this.doctorId, chief_complaint: `E2E ${person.marker}`,
    });
    this.visits.add(visit.id);
    return visit;
  }

  async scheduled(slot?: { date: string; time: string }): Promise<Visit> {
    const selected = slot || await this.futureSlot();
    const person = syntheticPatient();
    const visit = await this.json<Visit>('/api/v1/appointments/book', 'POST', {
      patient_name: person.name, patient_phone: person.phone, appointment_date: selected.date,
      appointment_time: selected.time, doctor_id: this.doctorId,
    });
    this.visits.add(visit.id);
    return visit;
  }

  async readVisit(id: string): Promise<Visit> {
    const rows = await this.json<Visit[]>('/api/v1/appointments/');
    const visit = rows.find(row => row.id === id);
    expect(visit, 'Created visit must remain readable through the real API').toBeDefined();
    return visit!;
  }
}

export const test = base.extend<{ actor: ClinicActor; runtimeAudit: void }>({
  runtimeAudit: [async ({ page }, provide, info) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await provide();
    await info.attach('browser-runtime-errors', { body: JSON.stringify(errors), contentType: 'application/json' });
    expect(errors, 'Unhandled browser exceptions are failures, including during fault injection').toEqual([]);
  }, { auto: true }],
  actor: async ({ page }, provide, info) => {
    const orgId = required('E2E_ORG_ID');
    const doctorId = required('E2E_DOCTOR_ID');
    let token = '';
    let browserOrg = '';
    const capture = (request: Request) => {
      if (request.url().startsWith(`${apiBase}/api/v1/`)) {
        const headers = request.headers();
        if (headers.authorization?.startsWith('Bearer ')) token = headers.authorization.slice(7);
        if (headers['x-org-id']) browserOrg = headers['x-org-id'];
      }
    };
    page.on('request', capture);
    await page.goto('/clinic/schedule');
    await expect(page.getByRole('heading', { name: 'Clinic Schedule', exact: true })).toBeVisible();
    await expect.poll(() => Boolean(token), { message: 'Browser must send a genuine authenticated API request' }).toBe(true);
    await expect.poll(() => browserOrg, { message: 'The UI must be operating in the selected staging clinic, not another account membership' }).toBe(orgId);
    page.off('request', capture);
    const temporary = new ClinicActor(page, token, orgId, doctorId, 'UTC');
    const org = await temporary.json<{ id: string; timezone: string }>(`/api/v1/org/${orgId}`);
    expect(org.id).toBe(orgId);
    expect(org.timezone).toBeTruthy();
    const doctors = await temporary.json<{ id: string }[]>('/api/v1/appointments/doctors');
    expect(doctors.some(doctor => doctor.id === doctorId), 'E2E_DOCTOR_ID must be an active doctor in this clinic').toBe(true);
    const actor = new ClinicActor(page, token, orgId, doctorId, org.timezone);
    await provide(actor);
    const rows = await actor.json<Visit[]>('/api/v1/appointments/');
    const retained = [];
    for (const id of Array.from(actor.visits)) {
      const visit = rows.find(row => row.id === id);
      if (visit && ['scheduled', 'arrived', 'skipped'].includes(visit.status)) {
        const result = await actor.request(`/api/v1/appointments/${id}/cancel`, 'POST', { reason: 'E2E fixture teardown' });
        expect(result.status(), `Cleanup cancellation failed for synthetic visit ${id}`).toBe(200);
      } else if (visit && !['cancelled', 'no_show'].includes(visit.status)) retained.push({ id, status: visit.status });
    }
    await info.attach('retained-synthetic-visits', { body: JSON.stringify(retained), contentType: 'application/json' });
  },
});

export { expect };
